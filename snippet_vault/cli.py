"""snippet-vault CLI — local-first semantic snippet manager.

Usage
-----
    snippet-vault add               interactive add
    snippet-vault search [query]     search or interactive search
    snippet-vault list [--page 1]   paginated list
    snippet-vault view <id>          view / act on a snippet
    snippet-vault tag [--cloud]      tag cloud & management
"""

from __future__ import annotations

import typer
from rich.console import Console

from snippet_vault.config import COLOUR_PRIMARY

app = typer.Typer(
    name="snippet-vault",
    help=__doc__,
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"allow_interspersed_args": False},
)
console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Commands — defined inline with @app.command()
# ---------------------------------------------------------------------------

@app.command(help="Add a new snippet interactively")
def add(
    title: str | None = typer.Option(None, "--title", "-t", help="Snippet title"),
    tags: list[str] | None = typer.Option(None, "--tag", help="Tag (repeatable)"),
    description: str | None = typer.Option(None, "--desc", help="Short description"),
    non_interactive: bool = typer.Option(False, "--yes", "-y", help="Skip confirm"),
) -> None:
    from snippet_vault.commands.add import run as add_run
    add_run(title, tags, description, non_interactive)


@app.command(help="Semantic search — find snippets by meaning")
def search(
    query: str = typer.Argument("", help="Search query (omit for interactive mode)"),
    top_k: int = typer.Option(20, "--top", "-n", help="Max results"),
    tag_filter: str | None = typer.Option(None, "--tag", help="Filter by tag"),
) -> None:
    from snippet_vault.commands.search import run as search_run
    search_run(query, top_k, tag_filter)


@app.command(name="list", help="List snippets with pagination, sorting, and tag filtering")
def list_cmd(
    page: int = typer.Option(1, "--page", "-p", help="Page number (1-based)"),
    sort: str = typer.Option("u", "--sort", "-s", help="u=updated, c=created, t=title, n=uses"),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Loop pages"),
) -> None:
    from snippet_vault.commands.list import run as list_run
    list_run(page, sort, tag, interactive)


@app.command(help="View & manage a snippet")
def view(
    snippet_id: int = typer.Argument(..., help="Snippet id to view"),
    no_actions: bool = typer.Option(False, "--no-actions", help="Read-only view"),
) -> None:
    from snippet_vault.commands.view import run as view_run
    view_run(snippet_id, no_actions)


@app.command(help="Tag cloud & management")
def tag(
    cloud: bool = typer.Option(True, "--cloud/--no-cloud", help="Show tag cloud"),
    rename: str | None = typer.Option(None, "--rename", help="Rename <old> to <new> (prompts)"),
    merge: str | None = typer.Option(None, "--merge", help="Merge <old> into <new>"),
    delete: str | None = typer.Option(None, "--delete", help="Delete tag"),
) -> None:
    from snippet_vault.commands.tag import run as tag_run
    tag_run(cloud, rename, merge, delete)


# ---------------------------------------------------------------------------
# Global options
# ---------------------------------------------------------------------------
@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version"),
) -> None:
    if version:
        from snippet_vault import __version__

        console.print(f"snippet-vault [bold {COLOUR_PRIMARY}]{__version__}[/]")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


# ---------------------------------------------------------------------------
# Entry point guard
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app()