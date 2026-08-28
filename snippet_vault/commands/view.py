"""``snippet-vault view`` — render a snippet with full code + metadata + actions."""

from __future__ import annotations

import datetime
import readchar

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from snippet_vault.config import COLOUR_ACCENT, COLOUR_PRIMARY, COLOUR_TEXT
from snippet_vault.display import banner, error, ok, tag_chips
from snippet_vault.search import SemanticSearch
from snippet_vault.storage import Snippet, Storage

app = typer.Typer(help="View & manage a snippet")
console = Console(highlight=False)


@app.command(name="")
def run(
    snippet_id: int = typer.Argument(..., help="Snippet id to view"),
    no_actions: bool = typer.Option(False, "--no-actions", help="Read-only view"),
) -> None:
    """View a snippet and perform actions on it."""
    storage = Storage()
    snip = storage.get_snippet(snippet_id)
    if snip is None:
        error(f"No snippet with id={snippet_id}")
        raise typer.Exit(1)

    if no_actions:
        console.print(_render(snip))
        return
    action = _interact(snip, storage)
    if action == "edit":
        _edit(snip, storage)
    elif action == "delete":
        _delete(snip, storage)
    elif action == "tag":
        _manage_tags(snip, storage)
    elif action == "copy":
        _copy(snip)


def view_snippet(snip: Snippet, storage: Storage) -> None:
    """Render a snippet nicely (used by search / list). Returns chosen action."""
    action = _interact(snip, storage)
    if action == "edit":
        _edit(snip, storage)
    elif action == "delete":
        _delete(snip, storage)
    elif action == "tag":
        _manage_tags(snip, storage)
    elif action == "copy":
        _copy(snip)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _render(snip: Snippet) -> Panel:
    meta = _metadata_line(snip)
    syntax = Syntax(
        snip.code.strip(),
        _detect_lexer(snip.code, snip.title),
        theme="monokai",
        line_numbers=True,
        word_wrap=True,
    )
    return Panel(
        syntax,
        title=f"[bold]{snip.title}[/bold]",
        subtitle=meta,
        border_style=COLOUR_PRIMARY,
        padding=(0, 1),
    )


def _metadata_line(snip: Snippet) -> str:
    parts = []
    if snip.tags:
        parts.append("Tags: " + " ".join(f"⟦{t}⟧" for t in snip.tags))
    parts.append(f"Uses: {snip.use_count}")
    parts.append(f"Created: {_fmt(snip.created_at)}")
    parts.append(f"Updated: {_fmt(snip.updated_at)}")
    if snip.description:
        parts.append(f"Desc: {snip.description}")
    return "  ·  ".join(parts)


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------
def _interact(snip: Snippet, storage: Storage) -> str | None:
    storage.increment_uses(snip.id)
    while True:
        console.print(_render(snip))
        console.print(
            "\n[bold #00D9A5]e[/] edit  ·  "
            "[bold #00D9A5]d[/] delete  ·  "
            "[bold #00D9A5]t[/] tag  ·  "
            "[bold #00D9A5]c[/] copy  ·  "
            "[bold #00D9A5]q[/] quit"
        )
        key = readchar.readkey().lower()
        if key in ("q", readchar.key.CTRL_C, readchar.key.ENTER):
            return None
        if key == "e":
            return "edit"
        if key == "d":
            return "delete"
        if key == "t":
            return "tag"
        if key == "c":
            return "copy"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def _edit(snip: Snippet, storage: Storage) -> None:
    from rich.prompt import Prompt

    title = Prompt.ask("Title", default=snip.title)
    desc = Prompt.ask("Description", default=snip.description)
    new_code = _open_editor(snip.title, snip.code)
    if not new_code.strip():
        error("Code cannot be empty.")
        return
    storage.update_snippet(snip.id, title=title, code=new_code, description=desc)
    # reindex
    try:
        from snippet_vault.config import get_embedder

        embedder = get_embedder()
        SemanticSearch(storage, embedder).refresh(snip)
    except Exception as exc:
        console.print(f"[dim]Reindex failed: {exc}[/dim]")
    ok(f"Snippet {snip.id} updated.")


def _delete(snip: Snippet, storage: Storage) -> None:
    if Confirm.ask(f"[bold #FF6B6B]Delete '{snip.title}'?[/bold #FF6B6B]", default=False):
        storage.delete_snippet(snip.id)
        storage.delete_embedding(snip.id)
        ok(f"Snippet {snip.id} deleted.")
    else:
        console.print("[dim]Kept.[/dim]")


def _manage_tags(snip: Snippet, storage: Storage) -> None:
    console.print(f"Current tags: {tag_chips(snip.tags)}")
    console.print(
        "[dim]+name to add, -name to remove  (e.g. '+async' or '-legacy')[/dim]"
    )
    raw = console.input("[bold #00D9A5]tag> [/bold #00D9A5]").strip()
    if not raw:
        return
    tags = list(snip.tags)
    for token in raw.split():
        if token.startswith("+"):
            name = token[1:].strip().lower()
            if name and name not in tags:
                tags.append(name)
        elif token.startswith("-"):
            name = token[1:].strip().lower()
            tags = [t for t in tags if t != name]
    storage.set_snippet_tags(snip.id, tags)
    ok("Tags updated.")


def _copy(snip: Snippet) -> None:
    try:
        import pyperclip

        pyperclip.copy(snip.code)
        ok("Copied to clipboard.")
    except Exception as exc:
        console.print(f"[dim]Clipboard unavailable: {exc}[/dim]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _open_editor(title: str, code: str) -> str:
    import os
    import subprocess
    import tempfile
    from pathlib import Path

    editor = os.environ.get("EDITOR", "nano" if _has_nano() else "vi")
    ext = ".py" if "def " in code or "import " in code else ".txt"
    with tempfile.NamedTemporaryFile(mode="w+", suffix=ext, delete=False, encoding="utf-8") as tf:
        tf.write(code)
        tf.flush()
        path = tf.name
    try:
        subprocess.run([editor, path], check=True)
        return Path(path).read_text(encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        error(f"Editor exited with {exc.returncode}")
        return code
    finally:
        Path(path).unlink(missing_ok=True)


def _has_nano() -> bool:
    import shutil

    return shutil.which("nano") is not None


def _detect_lexer(code: str, title: str) -> str:
    if title:
        exts = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".go": "go", ".rs": "rust", ".java": "java",
        }
        for ext, lex in exts.items():
            if title.lower().endswith(ext):
                return lex
    if "def " in code or "import " in code:
        return "python"
    if "function" in code or "const " in code:
        return "javascript"
    if "func " in code:
        return "go"
    return "text"


def _fmt(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
