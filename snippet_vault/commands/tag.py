"""``snippet-vault tag`` — tag cloud with frequency sizing + rename/merge/delete."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.text import Text

from snippet_vault.config import COLOUR_ACCENT, COLOUR_PRIMARY
from snippet_vault.display import error, ok
from snippet_vault.storage import Storage

app = typer.Typer(help="Browse & manage tags")
console = Console(highlight=False)


@app.command(name="")
def run(
    cloud: bool = typer.Option(True, "--cloud/--no-cloud", help="Show tag cloud"),
    rename: str | None = typer.Option(None, "--rename", help="Rename <old> to <new> (prompts)"),
    merge: str | None = typer.Option(None, "--merge", help="Merge <old> into <new>"),
    delete: str | None = typer.Option(None, "--delete", help="Delete tag"),
) -> None:
    """Show the tag cloud; optionally rename/merge/delete a tag."""
    storage = Storage()

    tags = storage.all_tags()  # [(name, count), ...]
    if not tags:
        console.print("[dim]No tags yet. Add snippets with tags first.[/dim]")
        return

    if cloud:
        _render_cloud(tags)

    if rename is not None:
        _rename(storage, rename)
    elif merge is not None:
        _merge(storage, merge)
    elif delete is not None:
        _delete(storage, delete)
    else:
        _manage_loop(storage)


# ---------------------------------------------------------------------------
# Cloud rendering
# ---------------------------------------------------------------------------
def _render_cloud(tags: list[tuple[str, int]]) -> None:
    if not tags:
        return
    max_count = max(c for _, c in tags)
    min_count = min(c for _, c in tags)
    span = max(1, max_count - min_count)

    # size buckets 0..4 → style weight
    def size_for(count: int) -> int:
        norm = (count - min_count) / span
        return int(norm * 4)

    sizes = {
        0: ("dim", ""),
        1: (COLOUR_ACCENT, ""),
        2: (COLOUR_ACCENT, "bold"),
        3: (COLOUR_PRIMARY, "bold"),
        4: (COLOUR_PRIMARY, "bold underline"),
    }

    cloud = Text()
    cloud.append("Tag cloud  ", style=f"bold {COLOUR_PRIMARY}")
    cloud.append("(size ∝ usage)\n\n", style="dim")
    for name, count in tags:
        sz = size_for(count)
        color, weight = sizes[sz]
        style = f"{color} {weight}".strip()
        cloud.append(f"  [{name}]:{count}  ", style=style)
    console.print(cloud)
    console.print()


# ---------------------------------------------------------------------------
# Management
# ---------------------------------------------------------------------------
def _manage_loop(storage: Storage) -> None:
    while True:
        console.print(
            "\n[bold #00D9A5]rename[/] <old>  ·  "
            "[bold #00D9A5]merge[/] <old>→<new>  ·  "
            "[bold #00D9A5]delete[/] <name>  ·  "
            "[bold #00D9A5]q[/] quit"
        )
        raw = Prompt.ask("[bold #00D9A5]tag>[/bold #00D9A5]", default="q").strip()
        if raw in ("q", "quit", ""):
            break
        parts = raw.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "rename" and arg:
            _rename(storage, arg)
        elif cmd == "merge" and "→" in arg:
            old, new = arg.split("→", 1)
            _rename(storage, old.strip(), new.strip())
        elif cmd == "delete" and arg:
            _delete(storage, arg)
        else:
            error("Unknown command. Try: rename <old>, merge <old>→<new>, delete <name>")


def _rename(storage: Storage, old: str, new: str | None = None) -> None:
    if new is None:
        new = Prompt.ask(f"Rename [{old}] to")
    if not new.strip():
        error("New name required.")
        return
    changed = storage.rename_tag(old, new)
    if changed:
        ok(f"Renamed [{old}] → [{new}]")
    else:
        error(f"Tag [{old}] not found or merge failed.")


def _delete(storage: Storage, name: str) -> None:
    removed = storage.delete_tag(name)
    if removed:
        ok(f"Deleted tag [{name}]")
    else:
        error(f"Tag [{name}] not found.")


def _merge(storage: Storage, spec: str) -> None:
    """Merge ``<old>→<new>`` or just ``<old>`` (prompts for target)."""
    if "→" in spec:
        old, new = spec.split("→", 1)
        old, new = old.strip(), new.strip()
    else:
        old = spec.strip()
        new = Prompt.ask(f"Merge [{old}] into").strip()
    if not old or not new or old == new:
        error("Need two different tag names.")
        return
    changed = storage.rename_tag(old, new)
    if changed:
        ok(f"Merged [{old}] → [{new}]")
    else:
        error(f"Tag [{old}] not found.")
