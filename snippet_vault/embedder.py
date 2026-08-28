"""Offline semantic embeddings via sentence-transformers.

A small, fast, fully-offline model is used by default so nothing ever
leaves the machine.  The model is downloaded once (requires network on
first run) and cached under the data directory.
"""

from __future__ import annotations

import functools
import os
from typing import Iterable

import numpy as np

from snippet_vault.config import EMBEDDINGS_DIR

# Compact, well-balanced all-rounder. 384-dim, ~80MB download, runs on CPU.
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingError(Exception):
    """Raised when the embedding model cannot be loaded or run."""


def _embedding_text(title: str, description: str, code: str, tags: Iterable[str]) -> str:
    """Build the text we embed. Includes intent-bearing fields, not just code."""
    parts = [f"Title: {title}"]
    if description:
        parts.append(f"Description: {description}")
    tag_list = list(tags)
    if tag_list:
        parts.append("Tags: " + ", ".join(tag_list))
    parts.append(code)
    return "\n".join(parts)


class EmbeddingModel:
    """Wraps a sentence-transformers model and exposes ``encode``."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        # Keep model weights on disk next to the vault.
        os.environ.setdefault(
            "SENTENCE_TRANSFORMERS_HOME", str(EMBEDDINGS_DIR / "models")
        )

    @functools.cached_property
    def model(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment error
            raise EmbeddingError(
                "sentence-transformers is not installed. Run: pip install snippet-vault[all]"
            ) from exc
        try:
            return SentenceTransformer(self.model_name)
        except Exception as exc:  # pragma: no cover - network/model error
            raise EmbeddingError(
                f"Failed to load embedding model '{self.model_name}': {exc}"
            ) from exc

    def encode(self, texts: Iterable[str], normalize: bool = True) -> np.ndarray:
        """Return a 2-D float32 array of L2-normalised vectors."""
        text_list = [t if isinstance(t, str) else str(t) for t in texts]
        if not text_list:
            return np.empty((0, 0), dtype=np.float32)
        vectors = self.model.encode(
            text_list,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed(self, title: str, description: str, code: str, tags: Iterable[str]) -> np.ndarray:
        return self.encode([_embedding_text(title, description, code, tags)])[0]


def cosine_similarity(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a single query vector and a matrix.

    Both inputs are assumed L2-normalised, so this is just a dot product.
    """
    if matrix.size == 0:
        return np.empty((0,), dtype=np.float32)
    return matrix @ query_vec
