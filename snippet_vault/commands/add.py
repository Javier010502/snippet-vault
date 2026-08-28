"""``snippet-vault add`` — interactive snippet creation."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import readchar
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from snippet_vault.config import COLOUR_PRIMARY, COLOUR_TEXT, PREVIEW_CHARS
from snippet_vault.display import banner, error, ok, preview_text, tag_chips
from snippet_vault.search import SemanticSearch
from snippet_vault.storage import Storage

app = typer.Typer(help="Add a new snippet to the vault")
console = Console()


@app.command(name="")
def run(
    title: str | None = typer.Option(None, "--title", "-t", help="Snippet title"),
    tags: list[str] | None = typer.Option(None, "--tag", help="Tag (repeatable)"),
    description: str | None = typer.Option(None, "--desc", help="Short description"),
    non_interactive: bool = typer.Option(False, "--yes", "-y", help="Skip confirm"),
) -> None:
    """Create a new snippet interactively."""
    storage = Storage()

    # ── Title ──────────────────────────────────────────────────────────────
    if not title:
        title = Prompt.ask(
            "[bold #00D9A5]Snippet title[/bold #00D9A5]",
            default="",
        ).strip()

    if not title:
        error("Title is required.")
        raise typer.Exit(1)

    # ── Code via $EDITOR ────────────────────────────────────────────────────
    code = _edit_in_editor(title)

    if not code.strip():
        error("Code cannot be empty.")
        raise typer.Exit(1)

    # ── Description ───────────────────────────────────────────────────────
    if not description:
        description = (
            Prompt.ask(
                "[bold #00D9A5]Description[/bold #00D9A5]  (optional, Enter to skip)",
                default="",
            ).strip()
        )

    # ── Tags ───────────────────────────────────────────────────────────────
    chosen_tags = list(tags or [])
    if not tags:
        chosen_tags = _pick_tags_interactive(storage, chosen_tags)

    # ── Preview & confirm ─────────────────────────────────────────────────
    _show_preview(title, description or "", code, chosen_tags)

    if not non_interactive and not Confirm.ask(
        "[bold #00D9A5]Save snippet?[/bold #00D9A5]", default=True
    ):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    sid = storage.add_snippet(title, code, description or "", chosen_tags)

    # index for semantic search
    try:
        from snippet_vault.config import get_embedder

        embedder = get_embedder()
        searcher = SemanticSearch(storage, embedder)
        snip = storage.get_snippet(sid)
        if snip:
            searcher.index_snippet(snip)
    except Exception as exc:
        console.print(f"[dim]Warning: could not index embedding — {exc}[/dim]")

    ok(f"Snippet saved (id={sid})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _edit_in_editor(title: str) -> str:
    """Open $EDITOR with a temporary file pre-seeded from title."""
    editor = os.environ.get("EDITOR", "nano" if _has_nano() else "vi")
    ext_map = {"python": ".py", "javascript": ".js", "typescript": ".ts", "go": ".go"}
    ext = ""
    for kw, e in ext_map.items():
        if kw in title.lower():
            ext = e
            break
    suffix = ext or ".txt"

    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=suffix, delete=False, encoding="utf-8"
    ) as tf:
        tf.write(f"# {title}\n")
        tf.flush()
        path = tf.name

    try:
        subprocess.run(
            [editor, path],
            check=True,
            env={**os.environ, "VISUAL": editor, "EDITOR": editor},
        )
        return Path(path).read_text(encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        error(f"Editor exited with {exc.returncode}")
        return ""
    finally:
        Path(path).unlink(missing_ok=True)


def _has_nano() -> bool:
    import shutil

    return shutil.which("nano") is not None


def _pick_tags_interactive(
    storage: Storage, initial: list[str]
) -> list[str]:
    """Present existing tags as selectable chips; let user type new ones."""
    chosen = list(initial)
    console.print(
        "\n[bold #00D9A5]Tags[/bold #00D9A5]  — arrow keys to navigate, "
        "[bold]Enter[/bold] to toggle, [bold]Space[/bold] to confirm\n"
        "[dim](type a name and press Enter to create a new tag)[/dim]"
    )

    all_tags = [name for name, _ in storage.all_tags()]
    selected_idx: set[int] = {
        i for i, t in enumerate(all_tags) if t in {c.lower() for c in chosen}
    }

    while True:
        rows = []
        for i, tag in enumerate(all_tags):
            marker = "[#00D9A5]●[/]" if i in selected_idx else "[dim]○[/]"
            rows.append(f"  {marker} [{tag}]")
        if rows:
            console.print(Panel("\n".join(rows), title="Existing tags", border_style="#00D9A5"))
        console.print(
            "[dim]↑↓ navigate  ·  Enter: toggle  ·  Space/done: confirm[/dim]"
        )
        key = readchar.readkey()
        if key == readchar.key.UP:
            idxs = sorted(selected_idx)
            if idxs:
                cur = idxs[-1]
                selected_idx = set(idxs[:-1])
                if cur > 0 and (cur - 1) not in selected_idx:
                    selected_idx.add(cur - 1)
        elif key == readchar.key.DOWN:
            if not selected_idx:
                selected_idx.add(0)
            else:
                cur = max(selected_idx)
                if cur < len(all_tags) - 1:
                    selected_idx.add(cur + 1)
        elif key == readchar.key.ENTER:
            if selected_idx:
                cur = max(selected_idx)
                if cur in selected_idx:
                    selected_idx.discard(cur)
                else:
                    selected_idx.add(cur)
        elif key == " ":
            break
        elif key == readchar.key.CTRL_C:
            raise KeyboardInterrupt()
        elif key.isalnum() or key in "-_":
            # type a custom tag
            new_tag = key
            while True:
                k = readchar.readkey()
                if k == readchar.key.ENTER:
                    break
                if k == readchar.key.CTRL_C:
                    raise KeyboardInterrupt()
                if k == readchar.key.BACKSPACE:
                    new_tag = new_tag[:-1]
                else:
                    new_tag += k
            new_tag = new_tag.strip().lower()
            if new_tag and new_tag not in {all_tags[i] for i in selected_idx}:
                chosen.append(new_tag)
                console.print(f"[#FFD700]+ added tag: {new_tag}[/]")
        if all_tags:
            console.print("\033[F\033[K", end="")

    return chosen


def _show_preview(title: str, description: str, code: str, tags: list[str]) -> None:
    lexer = "python"
    if "def " in code or "import " in code:
        lexer = "python"
    elif "function" in code or "const " in code:
        lexer = "javascript"
    elif "func " in code:
        lexer = "go"

    syntax = Syntax(code.strip(), lexer, theme="monokai", line_numbers=True)
    meta = []
    if tags:
        meta.append(f"Tags: {tag_chips(tags)}")
    if description:
        meta.append(f"Description: {description}")

    panel = Panel(
        syntax,
        title=f"[bold]{title}[/bold]",
        subtitle=" | ".join(meta) if meta else None,
        border_style=COLOUR_PRIMARY,
        padding=(0, 1),
    )
    console.print(panel)
