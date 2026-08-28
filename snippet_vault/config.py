"""Application-wide configuration — paths, colours, thresholds."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
APP_DIR: Path = Path(
    os.environ.get("SNIPPET_VAULT_DIR", Path.home() / ".config" / "snippet-vault")
)
DATA_DIR: Path = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH: Path = DATA_DIR / "vault.db"
EMBEDDINGS_DIR: Path = DATA_DIR / "embeddings"
EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Colour palette  (design spec)
# ---------------------------------------------------------------------------
COLOUR_PRIMARY  = "#00D9A5"   # terminal green / trust
COLOUR_BG        = "#1E1E2E"   # dark code editor
COLOUR_TEXT      = "#F8F8F2"   # Monokai default
COLOUR_ERROR     = "#FF6B6B"   # error / warning
COLOUR_ACCENT    = "#FFD700"   # highlights / tags

# ---------------------------------------------------------------------------
# Semantic-search settings
# ---------------------------------------------------------------------------
DEFAULT_TOP_K: int = 20          # results returned per search
MIN_SIMILARITY: float = 0.25     # filter threshold

# ---------------------------------------------------------------------------
# UI settings
# ---------------------------------------------------------------------------
LIST_PAGE_SIZE: int = 20
PREVIEW_CHARS: int = 60          # snippet preview in search results
SEARCH_DEBOUNCE_MS: int = 150

# ---------------------------------------------------------------------------
# Embedding model (cached at startup)
# ---------------------------------------------------------------------------
_EMBEDDER: Optional["EmbeddingModel"] = None


def get_embedder() -> "EmbeddingModel":
    """Lazy-load the embedding model (imports torch / sentence-transformers)."""
    global _EMBEDDER
    if _EMBEDDER is None:
        from snippet_vault.embedder import EmbeddingModel
        _EMBEDDER = EmbeddingModel()
    return _EMBEDDER


def clear_embedder() -> None:
    """Reset embedder (used by tests)."""
    global _EMBEDDER
    _EMBEDDER = None
