"""
StudyMate Backend (FastAPI)
Endpoints:
  POST   /upload-pdf        -> upload & index a PDF
  GET    /files             -> list indexed PDFs with metadata
  POST   /summarize-pdf     -> summarize last uploaded (or latest) PDF
  POST   /ask               -> Q&A over latest PDF (json: {"question": "..."} )
  POST   /ask-voice         -> speech-to-text -> Q&A -> (optional TTS)
  POST   /tts               -> text-to-speech; returns {"audio_url": "/audio/xxx.wav"}
  DELETE /reset             -> delete all uploads & index
  GET    /health            -> liveness

Storage:
  ./storage/pdfs    (original PDFs)
  ./storage/texts   (extracted text .txt)
  ./storage/audio   (generated audio files)
  ./storage/index.json

Notes:
  - Uses PyMuPDF (fitz) for PDF extraction
  - Simple summarizer (first N sentences/paragraphs heuristic)
  - Simple keyword-based QA
  - TTS via pyttsx3 -> WAV files on disk returned via /audio static mount
  - STT via SpeechRecognition (recognize_google). If not installed, /ask-voice returns 501.
"""

import os
import io
import re
import json
import time
import shutil
import string
from datetime import datetime
from typing import List, Optional, Dict, Any

import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Optional imports (kept graceful)
try:
    import pyttsx3
    HAS_TTS = True
except Exception:
    HAS_TTS = False

try:
    import speech_recognition as sr
    HAS_STT = True
except Exception:
    HAS_STT = False

# -------- Paths --------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
PDF_DIR = os.path.join(STORAGE_DIR, "pdfs")
TEXT_DIR = os.path.join(STORAGE_DIR, "texts")
AUDIO_DIR = os.path.join(STORAGE_DIR, "audio")
INDEX_PATH = os.path.join(STORAGE_DIR, "index.json")

for d in (STORAGE_DIR, PDF_DIR, TEXT_DIR, AUDIO_DIR):
    os.makedirs(d, exist_ok=True)

# -------- App --------
app = FastAPI(title="StudyMate Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # loosen for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# serve audio files
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")


# -------- Helpers --------
def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _load_index() -> Dict[str, Any]:
    if not os.path.exists(INDEX_PATH):
        return {"files": []}
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"files": []}

def _save_index(idx: Dict[str, Any]) -> None:
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

def _normalize_filename(name: str) -> str:
    # keep only safe chars
    keep = f"-_.() {string.ascii_letters}{string.digits}"
    return "".join(c for c in name if c in keep).strip() or f"file_{int(time.time())}.pdf"

def _extract_text_from_pdf(pdf_path: str) -> str:
    text = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text.append(page.get_text())
    return "\n".join(text).strip()

def _write_text_cache(pdf_name: str, text: str) -> str:
    base = os.path.splitext(pdf_name)[0]
    txt_path = os.path.join(TEXT_DIR, f"{base}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    return txt_path

def _read_text_cache(txt_path: str) -> str:
    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

def _latest_file_entry(idx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    files = idx.get("files") or []
    if not files:
        return None
    # latest by created_at
    return sorted(files, key=lambda x: x.get("created_at", ""), reverse=True)[0]

def _sentences(text: str) -> List[str]:
    # naive sentence splitter
    # split on '.', '!' or '?' keeping text
    candidates = re.split(r"(?<=[\.\!\?])\s+", text)
    # cleanup
    out = []
    for s in candidates:
        ss = s.strip()
        if len(ss) > 0:
            out.append(ss)
    return out

def _summarize(text: str, max_sentences: int = 6) -> str:
    if not text.strip():
        return "No content extracted from the PDF."
    sents = _sentences(text)
    if len(sents) <= max_sentences:
        return " ".join(sents)
    # take first N sentences, with a bit of paragraph preference
    # (this keeps it deterministic & robust without heavy libs)
    return " ".join(sents[:max_sentences])

def _tokenize(s: str) -> List[str]:
    s = s.lower()
    s = s.translate(str.maketrans("", "", string.punctuation))
    return [t for t in s.split() if t]

def _keyword_answer(text: str, question: str, top_k: int = 3) -> str:
    if not text.strip():
        return "No content available yet. Please upload and process a PDF."
    q_tokens = set(_tokenize(question))
    if not q_tokens:
        return "Please provide a valid question."
    sents = _sentences(text)
    scored = []
    for s in sents:
        s_tokens = set(_tokenize(s))
        score = len(q_tokens.intersection(s_tokens))
        if score > 0:
            scored.append((score, s))
    if not scored:
        return "Sorry, I couldn’t find an answer in the PDF."
    scored.sort(key=lambda x: x[0], reverse=True)
    best = [s for _, s in scored[:top_k]]
    return " ".join(best)

def _tts_to_wav(text: str, voice: str = "default", rate: int = 170, volume: float = 1.0) -> Optional[str]:
    if not HAS_TTS:
        return None
    engine = pyttsx3.init()
    # voices (optional simple mapping)
    try:
        voices = engine.getProperty("voices")
        if voice == "female" and len(voices) > 1:
            engine.setProperty("voice", voices[1].id)
        elif voice == "male" and len(voices) > 0:
            engine.setProperty("voice", voices[0].id)
    except Exception:
        pass
    try:
        engine.setProperty("rate", int(rate))
    except Exception:
        pass
    try:
        engine.setProperty("volume", float(volume))
    except Exception:
        pass
    fname = f"tts_{int(time.time()*1000)}.wav"
    out_path = os.path.join(AUDIO_DIR, fname)
    engine.save_to_file(text, out_path)
    engine.runAndWait()
    return f"/audio/{fname}"

def _stt_from_file(wav_path: str) -> Optional[str]:
    if not HAS_STT:
        return None
    recog = sr.Recognizer()
    with sr.AudioFile(wav_path) as src:
        audio = recog.record(src)
    try:
        # uses Google Web Speech API; needs internet
        return recog.recognize_google(audio)
    except Exception:
        return None


# -------- API --------
@app.get("/health")
async def health():
    return {"ok": True, "time": _now_iso()}

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Accepts a PDF, stores it, extracts text, updates index."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        return JSONResponse(status_code=415, content={"error": "Please upload a PDF."})

    safe_name = _normalize_filename(file.filename or f"uploaded_{int(time.time())}.pdf")
    pdf_path = os.path.join(PDF_DIR, safe_name)

    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Extract & cache
    try:
        text = _extract_text_from_pdf(pdf_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"PDF parse failed: {e}"})

    txt_path = _write_text_cache(safe_name, text)

    idx = _load_index()
    # remove previous identical name entry (idempotent)
    idx["files"] = [x for x in idx.get("files", []) if x.get("filename") != safe_name]
    idx["files"].append({
        "filename": safe_name,
        "pdf_path": pdf_path,
        "txt_path": txt_path,
        "created_at": _now_iso(),
        "chars": len(text),
    })
    _save_index(idx)

    return {"message": "uploaded", "filename": safe_name, "chars": len(text)}

@app.get("/files")
async def files():
    idx = _load_index()
    return idx.get("files", [])

@app.delete("/reset")
async def reset():
    try:
        # wipe storage
        for d in (PDF_DIR, TEXT_DIR, AUDIO_DIR):
            for name in os.listdir(d):
                try:
                    os.remove(os.path.join(d, name))
                except Exception:
                    pass
        if os.path.exists(INDEX_PATH):
            os.remove(INDEX_PATH)
        return {"message": "reset-complete"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/summarize-pdf")
async def summarize_pdf():
    """Summarize the latest uploaded PDF (no body required)."""
    idx = _load_index()
    entry = _latest_file_entry(idx)
    if not entry:
        return JSONResponse(status_code=404, content={"error": "No PDF uploaded yet."})
    text = _read_text_cache(entry.get("txt_path", ""))
    if not text:
        return JSONResponse(status_code=500, content={"error": "Stored text missing. Try re-uploading the PDF."})

    summary = _summarize(text, max_sentences=8)
    return {"summary": summary, "filename": entry["filename"]}

@app.post("/ask")
async def ask(payload: Dict[str, Any]):
    """Answer a question using the latest PDF context."""
    question = (payload or {}).get("question", "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "Missing 'question'."})

    idx = _load_index()
    entry = _latest_file_entry(idx)
    if not entry:
        return JSONResponse(status_code=404, content={"error": "No PDF uploaded yet."})
    text = _read_text_cache(entry.get("txt_path", ""))

    answer = _keyword_answer(text, question, top_k=3)
    return {"answer": answer, "filename": entry["filename"]}

@app.post("/tts")
async def tts(text: str = Form(...),
              voice: str = Form("default"),
              rate: int = Form(170),
              volume: float = Form(1.0)):
    if not text.strip():
        return JSONResponse(status_code=400, content={"error": "No text provided."})
    if not HAS_TTS:
        return JSONResponse(status_code=501, content={"error": "TTS engine not available on server."})
    audio_url = _tts_to_wav(text, voice=voice, rate=rate, volume=volume)
    if not audio_url:
        return JSONResponse(status_code=500, content={"error": "TTS failed."})
    return {"audio_url": audio_url}

@app.post("/ask-voice")
async def ask_voice(file: UploadFile = File(...),
                    speak: str = Form("false"),
                    voice: str = Form("default"),
                    rate: int = Form(170),
                    volume: float = Form(1.0)):
    """STT -> Ask -> (optional TTS). Accepts wav/mp3/m4a; best with wav."""
    if not HAS_STT:
        return JSONResponse(status_code=501, content={"error": "SpeechRecognition not installed on server."})

    # Save temp wav (if mp3/m4a uploaded, SpeechRecognition can still read via ffmpeg in some setups;
    # for reliability, expect wav)
    tmp_name = f"rec_{int(time.time()*1000)}_{file.filename or 'audio.wav'}"
    tmp_path = os.path.join(AUDIO_DIR, tmp_name)
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Recognize
    q_text = _stt_from_file(tmp_path) or ""

    if not q_text:
        return JSONResponse(status_code=400, content={"error": "Could not transcribe audio."})

    # Answer
    idx = _load_index()
    entry = _latest_file_entry(idx)
    if not entry:
        return JSONResponse(status_code=404, content={"error": "No PDF uploaded yet."})
    text = _read_text_cache(entry.get("txt_path", ""))

    answer = _keyword_answer(text, q_text, top_k=3)

    res = {"question": q_text, "answer": answer, "filename": entry["filename"]}

    # Optional TTS
    if str(speak).lower() == "true" and HAS_TTS:
        audio_url = _tts_to_wav(answer, voice=voice, rate=rate, volume=volume)
        if audio_url:
            res["audio_url"] = audio_url

    return res


# For `python main.py` local run
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
