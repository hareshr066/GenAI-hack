# StudyMate — AI PDF Tutor (Streamlit)
# Works with backend:
#   POST /upload-pdf        (multipart: file)
#   POST /summarize-pdf
#   POST /ask               (json: {"question": "..."} )
#   POST /ask-voice         (multipart: file; form: speak, voice, rate, volume)
#   POST /tts               (form: text, voice, rate, volume) -> {"audio_url": "/audio/xxx.wav"}
#   GET  /files
#   DELETE /reset

import os
import io
import time
import base64
import requests
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

# Optional mic (safe fallback)
try:
    from audio_recorder_streamlit import audio_recorder
    HAS_REC = True
except Exception:
    HAS_REC = False

load_dotenv()
BACKEND_URL = os.getenv("API_BASE", "http://127.0.0.1:8000")

# ---------- Page ----------
st.set_page_config(page_title="StudyMate — AI PDF Tutor", page_icon="📚", layout="wide")

# ---------- CSS ----------
st.markdown("""
<style>
.main { background: linear-gradient(180deg,#071021, #071428); color: #E6EEF6; }
.card { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: 14px; padding: 14px; box-shadow: 0 12px 30px rgba(2,8,23,.4); }
.muted { color:#9fb0c6; font-size:13px }
.chip { display:inline-block; padding:2px 8px; border-radius:999px; background:#0b1b35; color:#9ee6b8; border:1px solid rgba(158,230,184,.25); font-size:12px }
.chat-wrap { max-height: 440px; overflow-y:auto; padding-right: 8px; }
.bubble { background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.1); padding: 10px 12px; border-radius:12px; margin:6px 0 }
.user { background: linear-gradient(90deg,#3b82f6,#06b6d4); color: white; }
.btn-cta button { background: linear-gradient(90deg,#22c55e,#16a34a); color:white; border:none; border-radius:10px }
.btn-cta button:hover { filter: brightness(1.05) }
.btn-secondary button { background: linear-gradient(90deg,#0ea5e9,#06b6d4); color:white; border:none; border-radius:10px }
.btn-danger button { background: linear-gradient(90deg,#ef4444,#dc2626); color:white; border:none; border-radius:10px }
</style>
""", unsafe_allow_html=True)

# ---------- Helpers ----------
def badge(text, tone="info"):
    colors = {
        "info": "#06b6d4",
        "ok": "#16a34a",
        "warn": "#f59e0b",
        "err": "#ef4444",
        "muted": "#9fb0c6",
    }
    c = colors.get(tone, "#06b6d4")
    return f"<span style='background:{c}; color:white; padding:2px 8px; border-radius:999px; font-size:12px'>{text}</span>"

def list_files():
    try:
        r = requests.get(f"{BACKEND_URL}/files", timeout=20)
        if r.ok:
            return r.json() or []
    except Exception:
        pass
    return []

def upload_pdf_to_backend(uploaded):
    files = {"file": (uploaded.name, uploaded.read(), "application/pdf")}
    return requests.post(f"{BACKEND_URL}/upload-pdf", files=files, timeout=600)

def summarize_backend():
    return requests.post(f"{BACKEND_URL}/summarize-pdf", timeout=300)

def ask_backend(question: str):
    return requests.post(f"{BACKEND_URL}/ask", json={"question": question}, timeout=120)

def tts_backend(text: str, voice: str, rate: int, volume: float):
    form = {"text": text, "voice": voice, "rate": str(rate), "volume": str(volume)}
    return requests.post(f"{BACKEND_URL}/tts", data=form, timeout=180)

def ask_voice_backend(file_tuple, voice: str, rate: int, volume: float, speak: bool = True):
    files = {"file": file_tuple}
    data = {"speak": "true" if speak else "false", "voice": voice, "rate": str(rate), "volume": str(volume)}
    return requests.post(f"{BACKEND_URL}/ask-voice", files=files, data=data, timeout=600)

# ---------- State ----------
if "history" not in st.session_state:
    st.session_state.history = []  # list of {"who": "user"/"agent", "text": str, "audio_url": str|None}
if "last_summary" not in st.session_state:
    st.session_state.last_summary = ""
if "voice" not in st.session_state:
    st.session_state.voice = "default"
if "rate" not in st.session_state:
    st.session_state.rate = 170
if "volume" not in st.session_state:
    st.session_state.volume = 1.0
if "rec_bytes" not in st.session_state:
    st.session_state.rec_bytes = None

# ---------- Header ----------
colA, colB = st.columns([1, 3])
with colA:
    st.markdown('<div class="card" style="text-align:center">', unsafe_allow_html=True)
    st.markdown("""
      <svg width="140" height="140" viewBox="0 0 200 200" aria-hidden="true">
        <defs>
            <linearGradient id="g1" x1="0" x2="1">
              <stop offset="0" stop-color="#9EE6B8"/>
              <stop offset="1" stop-color="#60a5fa"/>
            </linearGradient>
        </defs>
        <circle cx="100" cy="60" r="28" fill="url(#g1)">
          <animate attributeName="r" values="26;30;26" dur="3s" repeatCount="indefinite" />
        </circle>
        <rect x="60" y="95" rx="12" ry="12" width="80" height="72" fill="#0b1224" />
      </svg>
    """, unsafe_allow_html=True)
    st.markdown('<div class="chip">StudyMate — Your Tutor</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with colB:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""
      <h2 style="margin:0 0 6px 0">Learn faster with your PDFs</h2>
      <div class="muted">Upload a PDF → create a clean summary → ask questions by typing or speaking. StudyMate can also speak answers aloud.</div>
    """, unsafe_allow_html=True)
    st.markdown(f"{badge('Frontend ready','ok')} &nbsp; {badge('Backend: ' + BACKEND_URL,'muted')}", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ---------- Layout ----------
left, mid, right = st.columns([1, 2, 1])

# ---- LEFT: Voice & Tips ----
with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🎤 Voice & Preferences")
    st.session_state.voice = st.selectbox("Voice", ["default","female","male"], index=["default","female","male"].index(st.session_state.voice))
    st.session_state.rate = st.slider("Rate (words/min)", 80, 260, int(st.session_state.rate))
    st.session_state.volume = st.slider("Volume", 0.1, 1.0, float(st.session_state.volume), step=0.1)
    st.caption("Tip: Summarize the PDF before asking questions for best results.")
    st.markdown("</div>", unsafe_allow_html=True)

# ---- RIGHT: Controls & Files ----
with right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("⚙ Controls")

    uploaded = st.file_uploader("📄 Upload PDF", type=["pdf"], key="pdf_uploader")

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬆ Process PDF", use_container_width=True):
            if not uploaded:
                st.warning("Please select a PDF first.")
            else:
                try:
                    with st.spinner("Uploading & processing..."):
                        resp = upload_pdf_to_backend(uploaded)
                        resp.raise_for_status()
                        info = resp.json()
                        st.success(f"Processed: {info.get('filename', uploaded.name)}")
                        st.session_state.last_summary = ""
                except Exception as e:
                    st.error(f"Upload failed: {e}")
    with c2:
        if st.button("📝 Summarize PDF", use_container_width=True):
            try:
                with st.spinner("Generating summary..."):
                    r = summarize_backend()
                    r.raise_for_status()
                    data = r.json()
                    st.session_state.last_summary = data.get("summary", "No summary.")
                    st.success("Summary created.")
            except Exception as e:
                st.error(f"Summarization failed: {e}")

    c3, c4 = st.columns([1, 1])
    with c3:
        if st.button("🔊 Read Summary", use_container_width=True):
            if not st.session_state.last_summary:
                st.warning("No summary available.")
            else:
                try:
                    rr = tts_backend(st.session_state.last_summary, st.session_state.voice, int(st.session_state.rate), float(st.session_state.volume))
                    rr.raise_for_status()
                    audio_url = rr.json().get("audio_url")
                    if audio_url:
                        st.audio(f"{BACKEND_URL}{audio_url}")
                    else:
                        st.warning("TTS did not return audio.")
                except Exception as e:
                    st.error(f"TTS failed: {e}")

    with c4:
        if st.button("🗑 Reset All", use_container_width=True):
            try:
                rr = requests.delete(f"{BACKEND_URL}/reset", timeout=60)
                rr.raise_for_status()
                st.session_state.clear()
                st.success("Server state cleared.")
            except Exception as e:
                st.error(f"Reset failed: {e}")

    st.markdown("---")
    st.caption("📂 Stored PDFs")
    files = list_files()
    if not files:
        st.markdown('<div class="muted">No PDFs uploaded yet.</div>', unsafe_allow_html=True)
    else:
        for f in files:
            fname = f.get("filename", "unknown.pdf")
            date = f.get("created_at", "")[:19].replace("T", " ")
            chars = f.get("chars", 0)
            st.markdown(f"- **{fname}** &nbsp; <span class='chip'>{date}</span> &nbsp; <span class='muted'>{chars} chars</span>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ---- MID: Summary + Chat ----
with mid:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    tabs = st.tabs(["📚 Summary", "💬 Chat"])

    # Summary Tab
    with tabs[0]:
        if st.session_state.last_summary:
            st.markdown(f"<div class='bubble'>{st.session_state.last_summary}</div>", unsafe_allow_html=True)
        else:
            st.info("No summary yet. Upload a PDF and click **Summarize PDF**.")

    # Chat Tab
    with tabs[1]:
        st.markdown('<div class="chat-wrap">', unsafe_allow_html=True)
        for msg in st.session_state.history:
            if msg["who"] == "user":
                st.markdown(f"<div class='bubble user'><b>You</b><br>{msg['text']}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='bubble'><b>StudyMate</b><br>{msg['text']}</div>", unsafe_allow_html=True)
                if msg.get("audio_url"):
                    st.audio(f"{BACKEND_URL}{msg['audio_url']}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        ctext, cmic, cbtns = st.columns([6, 2, 2])

        with ctext:
            user_q = st.text_input("Ask a question about your PDFs...")

        with cmic:
            if HAS_REC:
                audio_bytes = audio_recorder(text="🎙️ Tap to record / stop", recording_color="#ef4444", neutral_color="#0ea5e9")
                if audio_bytes:
                    st.session_state.rec_bytes = audio_bytes
                    st.success("Recording captured.")
            else:
                st.caption("Optional mic component not installed.")
        with cbtns:
            if st.button("Ask (text)", use_container_width=True):
                if not user_q.strip():
                    st.warning("Please type a question.")
                else:
                    try:
                        st.session_state.history.append({"who": "user", "text": user_q})
                        r = ask_backend(user_q)
                        r.raise_for_status()
                        ans = r.json().get("answer", "No answer.")
                        # Optional: TTS answer
                        audio_url = None
                        try:
                            tts_r = tts_backend(ans, st.session_state.voice, int(st.session_state.rate), float(st.session_state.volume))
                            if tts_r.ok:
                                audio_url = tts_r.json().get("audio_url")
                        except Exception:
                            audio_url = None
                        st.session_state.history.append({"who": "agent", "text": ans, "audio_url": audio_url})
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Ask failed: {e}")

            if st.button("Ask (voice)", use_container_width=True):
                file_tuple = None
                if HAS_REC and st.session_state.rec_bytes:
                    filename = f"voice_{int(time.time())}.wav"
                    file_tuple = (filename, io.BytesIO(st.session_state.rec_bytes), "audio/wav")
                if not file_tuple:
                    st.warning("No recording found. Use the recorder above.")
                else:
                    try:
                        r = ask_voice_backend(file_tuple, st.session_state.voice, int(st.session_state.rate), float(st.session_state.volume), speak=True)
                        r.raise_for_status()
                        data = r.json()
                        q = data.get("question", "")
                        a = data.get("answer", "")
                        au = data.get("audio_url")
                        if q:
                            st.session_state.history.append({"who": "user", "text": q})
                        st.session_state.history.append({"who": "agent", "text": a, "audio_url": au})
                        st.session_state.rec_bytes = None
                        st.success("Voice Q&A done.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Voice Q&A failed: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='text-align:center' class='muted'>StudyMate • Upload PDFs • Clean summaries • Text/Voice Q&A • Speech answers</div>", unsafe_allow_html=True)
