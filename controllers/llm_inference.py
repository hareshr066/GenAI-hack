# backend/controllers/llm_inference.py
import os
import requests
from dotenv import load_dotenv
from typing import List

load_dotenv()
HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
HF_TEXT_MODEL = os.getenv("HF_TEXT_MODEL", "mistralai/Mixtral-8x7B-Instruct-v0.1")
HF_API = "https://api-inference.huggingface.co/models"


def _hf_headers():
    return {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}


def generate_answer(context_chunks: List[str], question: str, max_new_tokens: int = 300, temperature: float = 0.1) -> str:
    """
    Context-aware answer generation. We pass explicit chunk markers to the model.
    """
    system = (
        "You are StudyMate, a highly accurate tutor. Answer using ONLY the provided context chunks below. "
        "If the answer cannot be found in the context, say 'I don't know'. Cite chunk numbers like [#2]."
    )
    # combine with explicit chunk numbering
    context = "\n\n".join(f"[#{i}] {c}" for i, c in enumerate(context_chunks))
    prompt = f"[SYSTEM]\n{system}\n[/SYSTEM]\n[CONTEXT]\n{context}\n[/CONTEXT]\n[QUESTION]\n{question}\n[/QUESTION]\n[ANSWER]"

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "return_full_text": False
        },
        "options": {"wait_for_model": True}
    }

    r = requests.post(f"{HF_API}/{HF_TEXT_MODEL}", headers=_hf_headers(), json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    # HF returns list or dict
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"].strip()
    if isinstance(data, dict) and "generated_text" in data:
        return data["generated_text"].strip()
    # fallback
    return str(data)


def summarize_chunks(chunks: List[str], max_new_tokens: int = 350) -> str:
    """
    Multi-stage abstractive summarization:
    - Summarize groups of chunks
    - Merge sub-summaries into final summary
    """
    if not chunks:
        return "No content to summarize."

    # Step 1: group chunks into batches of ~8 and summarize each
    batch_size = 8
    sub_summaries = []
    for i in range(0, len(chunks), batch_size):
        group = chunks[i : i + batch_size]
        prompt = (
            "Summarize the following material for a student concisely. Highlight key points, formulas, and structure.\n\n"
            + "\n\n".join(group)
            + "\n\nSummary:"
        )
        payload = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": max_new_tokens, "temperature": 0.2, "return_full_text": False},
            "options": {"wait_for_model": True}
        }
        r = requests.post(f"{HF_API}/{HF_TEXT_MODEL}", headers=_hf_headers(), json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        s = ""
        if isinstance(data, list) and data and "generated_text" in data[0]:
            s = data[0]["generated_text"].strip()
        elif isinstance(data, dict) and "generated_text" in data:
            s = data["generated_text"].strip()
        else:
            s = str(data)
        sub_summaries.append(s)

    # Step 2: combine sub-summaries into final summary
    combined = "\n\n".join(sub_summaries)
    final_prompt = (
        "You are an expert teacher. Combine and rewrite the following intermediate summaries into a single clear, structured summary "
        "suitable for a student. Use headings, bullet points, and short explanations.\n\n"
        + combined
        + "\n\nFinal Summary:"
    )
    payload = {
        "inputs": final_prompt,
        "parameters": {"max_new_tokens": 500, "temperature": 0.2, "return_full_text": False},
        "options": {"wait_for_model": True}
    }
    r = requests.post(f"{HF_API}/{HF_TEXT_MODEL}", headers=_hf_headers(), json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"].strip()
    if isinstance(data, dict) and "generated_text" in data:
        return data["generated_text"].strip()
    return str(data)
