# backend/controllers/asr_controller.py
import os
import io
import requests
from dotenv import load_dotenv

load_dotenv()
HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
HF_ASR_MODEL = os.getenv("HF_ASR_MODEL", "openai/whisper-base")
HF_API = "https://api-inference.huggingface.co/models"

# Optional faster local fallback (not implemented here)
# Make sure ffmpeg is installed for pydub resampling
try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except Exception:
    HAS_PYDUB = False


def _resample_audio_bytes_to_wav16mono(input_bytes: bytes) -> bytes:
    """Return WAV (16kHz, mono, 16-bit) bytes ready for ASR"""
    if not HAS_PYDUB:
        # If pydub not available, return raw bytes (HF may accept some formats)
        return input_bytes
    buf_in = io.BytesIO(input_bytes)
    # let pydub figure out format from header
    audio = AudioSegment.from_file(buf_in)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    out = io.BytesIO()
    audio.export(out, format="wav")
    out.seek(0)
    return out.read()


def transcribe_audio(file_path_or_bytes) -> str:
    """
    Accept either a filesystem path (str) or raw bytes.
    Returns transcription string.
    """
    try:
        if isinstance(file_path_or_bytes, str):
            with open(file_path_or_bytes, "rb") as f:
                raw = f.read()
        else:
            # bytes-like
            raw = file_path_or_bytes

        wav_bytes = _resample_audio_bytes_to_wav16mono(raw)
        headers = {
            "Authorization": f"Bearer {HF_TOKEN}",
            "Content-Type": "audio/wav",
        }
        url = f"{HF_API}/{HF_ASR_MODEL}"
        resp = requests.post(url, headers=headers, data=wav_bytes, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        # HF whisper returns {"text": "..."}
        if isinstance(data, dict) and "text" in data:
            return data["text"].strip()
        # fallback: return full json text
        return str(data)
    except requests.HTTPError as e:
        # bubble HTTP errors for visibility
        raise RuntimeError(f"ASR request failed: {e} / {getattr(e, 'response', '')}")
    except Exception as e:
        raise RuntimeError(f"ASR error: {e}")
