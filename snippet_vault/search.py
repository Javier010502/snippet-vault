"""Semantic search over the snippet vault, fully offline."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from snippet_vault.config import DEFAULT_TOP_K, MIN_SIMILARITY
from snippet_vault.embedder import EmbeddingModel, cosine_similarity
from snippet_vault.storage import SearchHit, Snippet, Storage


@dataclass
class SearchResult:
    hits: list[SearchHit]
    query_time_ms: float


class SemanticSearch:
    """Indexes snippet embeddings from storage and runs live queries."""

    def __init__(self, storage: Storage, embedder: EmbeddingModel) -> None:
        self.storage = storage
        self.embedder = embedder
        self._cache: dict[int, np.ndarray] = {}
        self._model_name = ""

    def index_size(self) -> int:
        self._load_matrix()
        return len(self._cache)

    # -- internals --------------------------------------------------------
    def _load_matrix(self, force: bool = False):
        if force or not self._cache:
            matrix, ids, model = self.storage.all_embeddings()
            self._cache = {sid: matrix[i] for i, sid in enumerate(ids)}
            self._model_name = model
        return self._cache

    def _ensure_indexed(self, snippet: Snippet) -> None:
        """Make sure a freshly added / edited snippet has an embedding."""
        cache = self._load_matrix()
        if snippet.id in cache:
            return
        vec = self.embedder.embed(
            snippet.title, snippet.description, snippet.code, snippet.tags
        )
        self.storage.save_embedding(snippet.id, vec, self.embedder.model_name)
        cache[snippet.id] = vec

    def refresh(self, snippet: Snippet) -> None:
        """Recompute & store embedding after an edit (or delete if removed)."""
        self._load_matrix(force=True)
        if self.storage.get_snippet(snippet.id) is None:
            self.storage.delete_embedding(snippet.id)
            self._cache.pop(snippet.id, None)
            return
        vec = self.embedder.embed(
            snippet.title, snippet.description, snippet.code, snippet.tags
        )
        self.storage.save_embedding(snippet.id, vec, self.embedder.model_name)
        self._cache[snippet.id] = vec

    # -- public API -------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_SIMILARITY,
        tag_filter: str | None = None,
    ) -> SearchResult:
        import time

        t0 = time.perf_counter()
        cache = self._load_matrix()
        if not cache:
            return SearchResult(hits=[], query_time_ms=0.0)

        q_vec = self.embedder.encode([query])[0]
        ids = list(cache.keys())
        matrix = np.vstack([cache[i] for i in ids])
        scores = cosine_similarity(q_vec, matrix)

        order = np.argsort(-scores)
        hits: list[SearchHit] = []
        for idx in order[: top_k * 3]:
            i = int(idx)
            score = float(scores[i])
            if score < min_score:
                continue
            sid = ids[i]
            snip = self.storage.get_snippet(sid)
            if snip is None:
                self.storage.delete_embedding(sid)
                self._cache.pop(sid, None)
                continue
            if tag_filter and tag_filter.lower() not in {t.lower() for t in snip.tags}:
                continue
            hits.append(SearchHit(snippet=snip, score=score))
            if len(hits) >= top_k:
                break

        elapsed = (time.perf_counter() - t0) * 1000.0
        return SearchResult(hits=hits, query_time_ms=elapsed)

    def index_snippet(self, snippet: Snippet) -> None:
        self._ensure_indexed(snippet)

    def reindex_all(self) -> int:
        """Embed every snippet that does not yet have a vector. Returns count."""
        cache = self._load_matrix(force=True)
        count = 0
        for snip in self.storage.list_snippets(limit=10_000, sort="created"):
            if snip.id not in cache:
                self._ensure_indexed(snip)
                count += 1
        return count
