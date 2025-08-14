# backend/controllers/summary_controller.py
import re
from typing import List

# You already have text extraction stored after upload. If you store per-file text somewhere,
# import it here. Otherwise, call your existing "pdf_controller.get_files()" to collect text.
try:
    from .pdf_controller import get_files
except ImportError:
    # fallback stub if your symbol differs
    def get_files():
        return []

def _clean_text(t: str) -> str:
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def _chunk(text: str, size: int = 1200, overlap: int = 150) -> List[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(' '.join(words[i:i+size]))
        i += size - overlap
    return chunks

def generate_summary(full_text: str, target_len=350) -> str:
    """
    Lightweight, dependency-free summarization (extractive):
    - scores sentences by length + simple tf weight
    - returns a clean, sectioned bullet summary
    """
    # split into sentences
    sents = re.split(r'(?<=[\.\!\?])\s+', full_text)
    sents = [s for s in sents if len(s.split()) > 6]
    if not sents:
        return "Could not generate summary."

    # crude TF scoring
    freq = {}
    words = re.findall(r'\w+', full_text.lower())
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    def score(sent):
        sw = re.findall(r'\w+', sent.lower())
        if not sw: return 0
        return sum(freq.get(w, 0) for w in sw) / len(sw)

    ranked = sorted(sents, key=score, reverse=True)
    keep = []
    total_len = 0
    for s in ranked:
        keep.append(s)
        total_len += len(s)
        if total_len >= target_len:
            break

    # format nicely
    bullets = '\n'.join([f"- {s}" for s in keep[:12]])
    return (
        "## Summary\n\n"
        + bullets
        + "\n\n---\n"
        "### Key Takeaways\n"
        + '\n'.join([f"• {s}" for s in keep[:6]])
    )

def summarize_all_files():
    files = get_files()
    body = "\n\n".join(_clean_text(f.get("text","")) for f in files if f.get("text"))
    if not body.strip():
        return {"summary": "No PDF content found. Please upload a PDF first."}
    # If you have a true LLM summarizer, call it here instead of generate_summary
    summary = generate_summary(body, target_len=900)
    return {"summary": summary}
