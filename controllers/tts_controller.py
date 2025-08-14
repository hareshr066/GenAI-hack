# backend/controllers/tts_controller.py
import os
import uuid
from gtts import gTTS

STATIC_AUDIO_DIR = os.path.join(os.getcwd(), "static", "audio")
os.makedirs(STATIC_AUDIO_DIR, exist_ok=True)

def text_to_speech(text: str, voice: str = "default", rate: int = 180, volume: float = 1.0) -> str:
    """
    Simple TTS using gTTS; returns path like '/static/audio/<filename>.mp3'.
    If you want different voices or higher control, swap to another TTS provider.
    """
    filename = f"{uuid.uuid4()}.mp3"
    filepath = os.path.join(STATIC_AUDIO_DIR, filename)
    tts = gTTS(text)
    tts.save(filepath)
    return f"/static/audio/{filename}"
