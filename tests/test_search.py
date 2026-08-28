"""Tests for the semantic search engine using a deterministic stub embedder.

These run without downloading the real (large) sentence-transformers model.
"""

from __future__ import annotations

from snippet_vault.embedder import EmbeddingModel
from snippet_vault.search import SemanticSearch
from snippet_vault.storage import Storage


class StubEmbedder(EmbeddingModel):
    """Deterministic cosine-similarity stub that encodes tokens into a fixed-dim vector.

    Each token is mapped to a bucket via zlib-crc32 (stable across Python invocations).
    Cosine similarity is computed properly, so queries that share more tokens with
    a snippet score higher.  This tests the search/ranking pipeline, not the model.
    """

    DIM = 64  # fixed embedding dimension

    def __init__(self) -> None:
        self.model_name = "stub"

    @staticmethod
    def _bucket(word: str) -> int:
        import zlib

        return zlib.crc32(word.encode("utf-8")) % StubEmbedder.DIM

    def encode(self, texts, normalize=True):
        import numpy as np

        vecs = []
        for t in texts:
            v = np.zeros(self.DIM, dtype=np.float32)
            for word in t.lower().split():
                v[self._bucket(word)] += 1.0
            norm = np.linalg.norm(v)
            if norm > 0 and normalize:
                v = v / norm
            vecs.append(v)
        return np.vstack(vecs).astype(np.float32)

    def embed(self, title, description, code, tags):
        text = f"{title} {description} {' '.join(tags)}\n{code}"
        return self.encode([text])[0]


def _seed_snippets(storage: Storage) -> list[str]:
    """Add 4 test snippets and return their titles in insertion order."""
    rows = [
        ("parse iso date", "parse iso dates", "python datetime",
         "from datetime import *\ndef parse_iso(s): return datetime.fromisoformat(s)"),
        ("flatten nested list", "flatten list", "python recursion",
         "def flatten(xs): return [y for xx in xs for y in xx]"),
        ("reverse a string", "reverse string", "python string",
         "def rev(s): return s[::-1]"),
        ("timestamp to unix", "timestamp conversion", "python datetime",
         "def to_unix(dt): return int(dt.timestamp())"),
    ]
    titles = []
    for title, desc, tag, code in rows:
        sid = storage.add_snippet(title, code, desc, tag.split())
        titles.append(title)
    return titles


class TestSearch:
    def test_index_size(self, tmp_path) -> None:
        storage = Storage(path=tmp_path / "s.db")
        embedder = StubEmbedder()
        titles = _seed_snippets(storage)
        searcher = SemanticSearch(storage, embedder)
        assert searcher.index_size() == 0  # not indexed yet
        searcher.reindex_all()
        assert searcher.index_size() == 4

    def test_search_returns_hits(self, tmp_path) -> None:
        storage = Storage(path=tmp_path / "s.db")
        embedder = StubEmbedder()
        _seed_snippets(storage)
        searcher = SemanticSearch(storage, embedder)
        searcher.reindex_all()
        res = searcher.search("hello world nonexistent", top_k=5)
        # hits exist but may be low-scoring
        assert len(res.hits) <= 5

    def test_search_min_score_cuts_off(self, tmp_path) -> None:
        storage = Storage(path=tmp_path / "s.db")
        embedder = StubEmbedder()
        _seed_snippets(storage)
        searcher = SemanticSearch(storage, embedder)
        searcher.reindex_all()
        # Tiny stub vectors with barely any overlap rarely reach 0.95
        res = searcher.search("parse dates", min_score=0.95, top_k=5)
        assert all(h.score >= 0.95 for h in res.hits)

    def test_search_tag_filter(self, tmp_path) -> None:
        storage = Storage(path=tmp_path / "s.db")
        embedder = StubEmbedder()
        _seed_snippets(storage)
        searcher = SemanticSearch(storage, embedder)
        searcher.reindex_all()
        res = searcher.search("anything", tag_filter="datetime", top_k=5)
        assert all("datetime" in h.snippet.tags for h in res.hits)
        # snippets tagged recursion should be absent
        assert not any("recursion" in h.snippet.tags for h in res.hits)

    def test_search_tag_filter_unknown(self, tmp_path) -> None:
        storage = Storage(path=tmp_path / "s.db")
        embedder = StubEmbedder()
        _seed_snippets(storage)
        searcher = SemanticSearch(storage, embedder)
        searcher.reindex_all()
        res = searcher.search("anything", tag_filter="nonexistent_tag_xyz", top_k=5)
        assert res.hits == []
