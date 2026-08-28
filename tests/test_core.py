"""Tests for snippet_vault."""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest

from snippet_vault.storage import Snippet, Storage


@pytest.fixture
def tmp_storage(tmp_path: Path) -> Storage:
    return Storage(path=tmp_path / "test.db")


class TestStorage:
    def test_add_snippet(self, tmp_storage: Storage) -> None:
        sid = tmp_storage.add_snippet(
            "hello",
            "print('hello world')",
            description="basic test",
            tags=["python", "demo"],
        )
        assert sid > 0

        snip = tmp_storage.get_snippet(sid)
        assert snip is not None
        assert snip.title == "hello"
        assert snip.code == "print('hello world')"
        assert snip.description == "basic test"
        assert "python" in snip.tags
        assert "demo" in snip.tags

    def test_update_snippet(self, tmp_storage: Storage) -> None:
        sid = tmp_storage.add_snippet("orig", "x = 1")
        tmp_storage.update_snippet(sid, title="updated", code="x = 2")
        snip = tmp_storage.get_snippet(sid)
        assert snip is not None
        assert snip.title == "updated"
        assert snip.code == "x = 2"

    def test_delete_snippet(self, tmp_storage: Storage) -> None:
        sid = tmp_storage.add_snippet("to-delete", "pass")
        assert tmp_storage.get_snippet(sid) is not None
        tmp_storage.delete_snippet(sid)
        assert tmp_storage.get_snippet(sid) is None

    def test_list_snippets_pagination(self, tmp_storage: Storage) -> None:
        for i in range(25):
            tmp_storage.add_snippet(f"snip-{i}", f"# {i}")
        assert len(tmp_storage.list_snippets(limit=10)) == 10
        assert len(tmp_storage.list_snippets(limit=10, offset=10)) == 10
        assert len(tmp_storage.list_snippets(limit=10, offset=20)) == 5

    def test_list_snippets_by_tag(self, tmp_storage: Storage) -> None:
        tmp_storage.add_snippet("a", "a", tags=["python"])
        tmp_storage.add_snippet("b", "b", tags=["python"])
        tmp_storage.add_snippet("c", "c", tags=["go"])
        assert len(tmp_storage.list_snippets(tag="python")) == 2
        assert len(tmp_storage.list_snippets(tag="go")) == 1
        assert len(tmp_storage.list_snippets(tag="rust")) == 0

    def test_tag_rename(self, tmp_storage: Storage) -> None:
        sid = tmp_storage.add_snippet("x", "x", tags=["old"])
        assert "old" in tmp_storage.get_snippet(sid).tags
        tmp_storage.rename_tag("old", "new")
        snip = tmp_storage.get_snippet(sid)
        assert snip is not None
        assert "new" in snip.tags
        assert "old" not in snip.tags

    def test_tag_merge(self, tmp_storage: Storage) -> None:
        sid1 = tmp_storage.add_snippet("a", "a", tags=["python"])
        sid2 = tmp_storage.add_snippet("b", "b", tags=["py"])
        tmp_storage.rename_tag("py", "python")
        snip2 = tmp_storage.get_snippet(sid2)
        assert snip2 is not None
        assert "python" in snip2.tags
        # sid1 still has python, sid2 also → deduplication removes dup
        count = tmp_storage.count_snippets(tag="python")
        assert count == 2

    def test_tag_delete(self, tmp_storage: Storage) -> None:
        sid = tmp_storage.add_snippet("x", "x", tags=["temp"])
        assert "temp" in tmp_storage.get_snippet(sid).tags
        tmp_storage.delete_tag("temp")
        snip = tmp_storage.get_snippet(sid)
        assert snip is not None
        assert "temp" not in snip.tags

    def test_all_tags(self, tmp_storage: Storage) -> None:
        tmp_storage.add_snippet("a", "a", tags=["python", "web"])
        tmp_storage.add_snippet("b", "b", tags=["python", "cli"])
        tags = tmp_storage.all_tags()
        names = {n for n, _ in tags}
        assert "python" in names
        assert "web" in names
        assert "cli" in names
        counts = dict(tags)
        assert counts["python"] == 2
        assert counts["web"] == 1
        assert counts["cli"] == 1

    def test_use_count(self, tmp_storage: Storage) -> None:
        sid = tmp_storage.add_snippet("x", "x")
        assert tmp_storage.get_snippet(sid).use_count == 0
        tmp_storage.increment_uses(sid)
        assert tmp_storage.get_snippet(sid).use_count == 1

    def test_embedding_save_load(self, tmp_storage: Storage) -> None:
        import numpy as np

        sid = tmp_storage.add_snippet("e", "e")
        vec = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        tmp_storage.save_embedding(sid, vec, "test-model")
        matrix, ids, model = tmp_storage.all_embeddings()
        assert model == "test-model"
        assert len(ids) == 1
        assert ids[0] == sid
        np.testing.assert_allclose(matrix[0], vec, atol=1e-5)


class TestEmbedder:
    def test_embedding_text(self) -> None:
        from snippet_vault.embedder import _embedding_text

        text = _embedding_text(
            "parse ISO date",
            "handles fractional seconds",
            "datetime.fromisoformat(...)",
            ["python", "datetime"],
        )
        assert "parse ISO date" in text
        assert "handles fractional seconds" in text
        assert "datetime.fromisoformat(...)" in text
        assert "python" in text
        assert "datetime" in text

    def test_cosine_similarity(self) -> None:
        import numpy as np

        from snippet_vault.embedder import cosine_similarity

        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([1.0, 0.0], dtype=np.float32)
        c = np.array([0.0, 1.0], dtype=np.float32)
        matrix = np.vstack([b, c]).astype(np.float32)
        assert abs(cosine_similarity(a, matrix)[0] - 1.0) < 1e-6
        assert abs(cosine_similarity(a, matrix)[1]) < 1e-6


class TestDisplay:
    def test_similarity_badge(self) -> None:
        from snippet_vault.display import similarity_badge

        badge = similarity_badge(0.87)
        assert "▰▰▰▰▱" in str(badge)
        assert "0.87" in str(badge)

    def test_tag_chips(self) -> None:
        from snippet_vault.display import tag_chips

        chips = tag_chips(["python", "date-parsing"])
        assert "[python]" in str(chips)
        assert "[date-parsing]" in str(chips)

    def test_preview_text(self) -> None:
        from snippet_vault.display import preview_text

        code = "def foo():\n    pass\n# extra lines"
        assert preview_text(code, 30) == "def foo():"
        assert preview_text(code, 10) == "def foo()…"

    def test_detect_lexer(self) -> None:
        from snippet_vault.display import detect_lexer

        assert detect_lexer("def foo():", "test.py") == "python"
        assert detect_lexer("const x = 1", "test.js") == "javascript"
        assert detect_lexer("func main() {}", "main.go") == "go"
