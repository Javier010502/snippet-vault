"""``snippet-vault list`` — paginated, sortable, filterable table of snippets."""

from __future__ import annotations

import datetime

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from snippet_vault.config import COLOUR_ACCENT, COLOUR_PRIMARY, COLOUR_TEXT, LIST_PAGE_SIZE
from snippet_vault.display import error, tag_chips
from snippet_vault.storage import Storage

app = typer.Typer(help="List all snippets")
console = Console(highlight=False)


@app.command(name="")
def run(
    page: int = typer.Option(1, "--page", "-p", help="Page number (1-based)"),
    sort: str = typer.Option("u", "--sort", "-s", help="u=updated, c=created, t=title, n=uses"),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Loop pages"),
) -> None:
    """List snippets with pagination, sorting, and tag filtering."""
    storage = Storage()

    sort_map = {"u": "updated", "c": "created", "t": "title", "n": "uses"}
    sort_key = sort_map.get(sort, "updated")

    total = storage.count_snippets(tag=tag)
    pages = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)

    if interactive:
        cur = page
        while True:
            _render_page(storage, cur, pages, sort_key, tag)
            ans = Prompt.ask(
                "\n[dim](n=next p=prev <num>=jump q=quit)[/dim]",
                default="n",
                show_default=False,
            ).strip().lower()
            if ans in ("q", "quit", readchar_key()):
                break
            elif ans in ("n", "next", ""):
                cur = min(pages, cur + 1)
            elif ans in ("p", "prev"):
                cur = max(1, cur - 1)
            elif ans.isdigit():
                cur = max(1, min(pages, int(ans)))
    else:
        _render_page(storage, page, pages, sort_key, tag)


def _render_page(storage: Storage, page: int, pages: int, sort: str, tag: str | None) -> None:
    offset = (page - 1) * LIST_PAGE_SIZE
    snippets = storage.list_snippets(
        limit=LIST_PAGE_SIZE, offset=offset, sort=sort, tag=tag
    )

    table = Table(
        title=f"snippet-vault  ·  page {page}/{pages}  ·  {storage.count_snippets(tag=tag)} total",
        title_style=f"bold {COLOUR_PRIMARY}",
        header_style=f"bold {COLOUR_TEXT}",
        border_style="#1E1E2E",
        expand=True,
    )
    table.add_column("#", justify="right", style="dim", width=5)
    table.add_column("title", style=COLOUR_TEXT, no_wrap=False)
    table.add_column("tags", no_wrap=False)
    table.add_column("created", justify="center", style="dim")
    table.add_column("updated", justify="center", style="dim")

    for snip in snippets:
        tags_str = " ".join(f"⟦{t}⟧" for t in snip.tags) if snip.tags else "—"
        table.add_row(
            str(snip.id),
            snip.title,
            tags_str,
            _fmt(snip.created_at),
            _fmt(snip.updated_at),
        )

    console.print(table)

    if not snippets:
        console.print("[dim]No snippets found.[/dim]")


def _fmt(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def readchar_key() -> str:
    return "quit"
