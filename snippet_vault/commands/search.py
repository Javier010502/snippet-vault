"""``snippet-vault search`` — interactive semantic search with live preview."""

from __future__ import annotations

import datetime
from typing import Iterable

import readchar
import typer
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from snippet_vault.config import (
    COLOUR_ACCENT,
    COLOUR_PRIMARY,
    COLOUR_TEXT,
    DEFAULT_TOP_K,
    MIN_SIMILARITY,
)
from snippet_vault.display import (
    code_panel,
    preview_text,
    similarity_badge,
    tag_chips,
)
from snippet_vault.search import SemanticSearch
from snippet_vault.storage import SearchHit, Storage

app = typer.Typer(help="Semantic search — find snippets by meaning, not keywords")
console = Console(highlight=False)


@app.command(name="")
def run(
    query: str = typer.Argument("", help="Search query (omit for interactive mode)"),
    top_k: int = typer.Option(DEFAULT_TOP_K, "--top", "-n", help="Max results"),
    tag_filter: str | None = typer.Option(None, "--tag", help="Filter by tag"),
) -> None:
    if query:
        _run_one_shot(query, top_k, tag_filter)
    else:
        _run_interactive(top_k)


# ---------------------------------------------------------------------------
# One-shot (non-interactive)
# ---------------------------------------------------------------------------
def _run_one_shot(query: str, top_k: int, tag_filter: str | None) -> None:
    storage = Storage()
    try:
        from snippet_vault.config import get_embedder

        embedder = get_embedder()
    except Exception as exc:
        console.print(f"[#FF6B6B]Embedding model unavailable: {exc}[/]")
        raise typer.Exit(1)

    searcher = SemanticSearch(storage, embedder)
    result = searcher.search(query, top_k=top_k, min_score=MIN_SIMILARITY, tag_filter=tag_filter)

    if not result.hits:
        console.print("[dim]No results.[/dim]")
        return

    console.print(Text(f"{len(result.hits)} result(s) in {result.query_time_ms:.1f}ms", style="dim"))
    console.print()
    for hit in result.hits:
        _print_hit(hit)


def _print_hit(hit: SearchHit) -> None:
    snip = hit.snippet
    score_badge = similarity_badge(hit.score)
    tags = tag_chips(snip.tags) if snip.tags else Text("—", style="dim")
    preview = preview_text(snip.code)
    title_display = snip.title if len(snip.title) <= 50 else snip.title[:47] + "…"
    console.print(f"{score_badge}  [bold {COLOUR_TEXT}]{title_display}[/]  {tags}")
    if preview:
        console.print(f"    [dim]{preview}[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# Interactive TUI
# ---------------------------------------------------------------------------
def _run_interactive(top_k: int) -> None:
    storage = Storage()
    try:
        from snippet_vault.config import get_embedder

        embedder = get_embedder()
    except Exception as exc:
        console.print(f"[#FF6B6B]Embedding model unavailable: {exc}[/]")
        raise typer.Exit(1)

    searcher = SemanticSearch(storage, embedder)

    query = ""
    results: list[SearchHit] = []
    cursor = 0

    layout = Layout()
    layout.split(
        Layout(name="input", size=3),
        Layout(name="results"),
        Layout(name="preview", size=12),
    )

    live = Live(layout, console=console, refresh_per_second=30, transient=False)
    live.start()
    try:
        while True:
            # run search for current query
            result = searcher.search(query, top_k=top_k, min_score=MIN_SIMILARITY)
            results = result.hits
            if cursor >= len(results):
                cursor = max(0, len(results) - 1)
            selected = results[cursor] if results else None

            _update_layout(layout, query, results, result.query_time_ms, cursor, selected)
            live.refresh()

            key = readchar.readkey()

            if key in (readchar.key.UP, "k"):
                cursor = max(0, cursor - 1)
            elif key in (readchar.key.DOWN, "j"):
                cursor = min(len(results) - 1, cursor + 1) if results else 0
            elif key in (readchar.key.ENTER, "\n", " ") and selected:
                live.stop()
                _view_snippet(selected.snippet, storage)
                live.start()
            elif key == "/":
                live.stop()
                new_q = console.input("[bold #00D9A5]Refine query:[/bold #00D9A5] ")
                live.start()
                if new_q or new_q == "":
                    query = new_q
                    cursor = 0
            elif key in ("a", "A"):
                live.stop()
                from snippet_vault.commands.add import run as add_main

                try:
                    add_main()
                except SystemExit:
                    pass
                live.start()
            elif key in ("q", "Q", readchar.key.CTRL_C, readchar.key.CTRL_D):
                break
            elif key == readchar.key.BACKSPACE:
                query = query[:-1]
                cursor = 0
            elif key.isprintable() and not key.startswith("\x1b"):
                query += key
                cursor = 0
    finally:
        live.stop()

    console.print("[dim]Goodbye.[/dim]")


# ---------------------------------------------------------------------------
# Layout renderer
# ---------------------------------------------------------------------------
def _update_layout(
    layout: Layout,
    query: str,
    results: list[SearchHit],
    query_time_ms: float,
    cursor: int,
    selected: SearchHit | None,
) -> None:
    time_str = f"[dim]{query_time_ms:.1f}ms[/]" if query else ""
    input_text = (
        f"[bold #00D9A5]SEARCH[/]  {query}[#00D9A5]▏[/]{time_str}"
        if query
        else "[bold #00D9A5]SEARCH[/]  [dim]<type to search>[/]"
    )
    layout["input"].update(
        Panel(input_text, border_style="#00D9A5", padding=(0, 1))
    )

    if not results:
        layout["results"].update(
            Panel(
                "[dim]No results — type a query above[/dim]",
                border_style="#1E1E2E",
                padding=(1, 2),
            )
        )
    else:
        table = Table(
            show_header=True,
            header_style=f"bold {COLOUR_TEXT}",
            border_style="#1E1E2E",
            pad_edge=False,
            expand=True,
        )
        table.add_column("score", width=8, no_wrap=True)
        table.add_column("title", width=40, no_wrap=False)
        table.add_column("tags", max_width=30, no_wrap=False)
        table.add_column("preview", max_width=35, no_wrap=False)

        for i, hit in enumerate(results):
            snip = hit.snippet
            badge = similarity_badge(hit.score)
            tags_str = " ".join(f"⟦{t}⟧" for t in snip.tags) if snip.tags else ""
            preview = preview_text(snip.code, 40)
            title_txt = f"[bold]{snip.title}[/]" if i == cursor else snip.title
            preview_txt = f"[dim]{preview}[/dim]" if i != cursor else preview
            table.add_row(str(badge), title_txt, tags_str, preview_txt)

        layout["results"].update(Panel(table, border_style="#1E1E2E", padding=(0, 0)))

    if selected:
        snip = selected.snippet
        tags_str = f"Tags: {tag_chips(snip.tags)}" if snip.tags else ""
        meta = f"[dim]Uses: {snip.use_count}  ·  Created: {_fmt_time(snip.created_at)}[/]"
        syntax = Syntax(
            snip.code.strip(),
            _detect_lexer(snip.code, snip.title),
            theme="monokai",
            line_numbers=True,
        )
        preview_pane = Panel(
            syntax,
            title=f"[bold]{snip.title}[/bold]  {tags_str}  {meta}",
            border_style="#FFD700",
            padding=(0, 1),
        )
    else:
        preview_pane = Panel(
            "[dim]↑↓ to navigate and preview[/dim]",
            border_style="#1E1E2E",
            padding=(0, 1),
        )
    layout["preview"].update(preview_pane)


# ---------------------------------------------------------------------------
# View snippet (called from search)
# ---------------------------------------------------------------------------
def _view_snippet(snip, storage: Storage) -> None:
    from snippet_vault.commands.view import view_snippet

    view_snippet(snip, storage)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


def _fmt_time(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
