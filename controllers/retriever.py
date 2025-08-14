# backend/controllers/retriever.py
from typing import List, Tuple
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_embedder = SentenceTransformer(EMBED_MODEL)


def embed_texts(texts: List[str]) -> np.ndarray:
    """Encode list[str] -> float32 numpy array"""
    vecs = _embedder.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return np.asarray(vecs, dtype="float32")


def build_index(embeddings: np.ndarray) -> faiss.IndexFlatL2:
    if embeddings is None or embeddings.size == 0:
        raise ValueError("No embeddings provided")
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    return index


def search(index: faiss.IndexFlatL2, query: str, texts: List[str], k: int = 4) -> Tuple[List[int], List[str]]:
    qvec = _embedder.encode([query], convert_to_numpy=True)
    qvec = np.asarray(qvec, dtype="float32")
    D, I = index.search(qvec, k)
    idxs = [int(i) for i in I[0] if i != -1]
    hits = [texts[i] for i in idxs]
    return idxs, hits
