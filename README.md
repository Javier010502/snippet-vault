# snippet-vault

Local-first, **semantic** command-line snippet manager. Save, tag, and rediscover
your reusable code by *meaning* — not exact keywords — using a small, fully
offline embedding model. Nothing ever leaves your machine.

```
┌─ snippet-vault search ──────────────────────────────────────────────┐
│  SEARCH  parse iso date                             12.3ms          │
│  ▰▰▰▰▱ 0.92  parse_iso_dates.py       [#python] [#datetime]          │
│  ▰▰▰▱▱ 0.87  datetime_helpers.py      [#python] [#parsing]           │
│  ▰▰▱▱▱ 0.71  date_utils.js            [#js] [#dates]                 │
│  ▰▱▱▱▱ 0.45  legacy_parser.go         [#go] [#legacy]               │
│  ─────────────────────────────────────────────────────────────────  │
│  ↑↓ navigate  ·  Enter: view  ·  /: refine  ·  a: add  ·  q: quit   │
└─────────────────────────────────────────────────────────────────────┘
```

## Why

Plain-text greps fail the moment you forget the exact variable or library name
you used. `snippet-vault` embeds every snippet into a vector and ranks results
by **semantic similarity**, so a query like "parse ISO dates" surfaces
`datetime.fromisoformat(...)` even though the words never match literally.

## Features

- **Offline semantic search** — `sentence-transformers/all-MiniLM-L6-v2`
  (384-dim, ~80 MB, CPU-friendly) runs entirely on your machine.
- **Inline similarity badge** `▰▰▰▱▱ 0.87` next to every result.
- **Fuzzy tag chips** `[#python]` that you can filter by.
- **Interactive `add`** — `$EDITOR` code entry, live preview, tag multi-select.
- **`view`** — full syntax-highlighted code with line numbers, copy to clipboard,
  inline edit / delete / tag actions.
- **`list`** — paginated (20/page), sortable (`-s u|c|t|n`), filterable by tag.
- **`tag`** — frequency-sized tag cloud; rename / merge / delete.
- **Zero cloud** — SQLite + local model cache. Fully private.

## Tech stack

| Layer        | Tool |
|--------------|------|
| CLI          | [Typer](https://typer.tiangolo.com/) |
| Storage      | SQLite (stdlib `sqlite3`) + NumPy blobs |
| Embeddings   | [sentence-transformers](https://www.sbert.net/) (offline) |
| TUI / render | [Rich](https://rich.readthedocs.io/) + `readchar` |

## Install

Requires Python ≥ 3.11.

```bash
git clone https://github.com/Javier010502/snippet-vault
cd snippet-vault
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

> The first `search`/`add` downloads the embedding model (~80 MB) once and caches
> it under `~/.config/snippet-vault/data/embeddings/models`. After that,
> everything runs offline.

## Run

```bash
# Interactive semantic search
snippet-vault search

# One-shot search
snippet-vault search "parse iso dates"

# Add a snippet (opens $EDITOR for code)
snippet-vault add

# List, sorted by updated (default), filtered by tag
snippet-vault list --sort u --tag python
snippet-vault list --interactive

# View / edit / copy / delete a snippet by id
snippet-vault view 3

# Tag cloud + rename / merge / delete
snippet-vault tag
snippet-vault tag --delete legacy
snippet-vault tag --merge old→new
```

## Usage examples

```bash
# Add a Python snippet non-interactively
snippet-vault add --title "debounce decorator" \
  --tag python --tag async \
  --desc "throttle rapid calls"

# Semantic search that ignores exact wording
snippet-vault search "remove duplicate items from list"
# → surfaces snippets tagged [#dedupe], [#python], [#set] etc.
```

## Project structure

```
snippet-vault/
├── pyproject.toml          # build + deps + tool config
├── snippet_vault/
│   ├── cli.py              # root Typer app, lazy sub-commands
│   ├── config.py           # paths, palette, thresholds
│   ├── storage.py          # SQLite + embedding persistence
│   ├── embedder.py         # offline sentence-transformers wrapper
│   ├── search.py           # SemanticSearch engine
│   ├── display.py          # Rich helpers: badges, chips, code panels
│   └── commands/
│       ├── add.py          # interactive add flow
│       ├── search.py       # interactive + one-shot search
│       ├── list.py         # paginated / sortable listing
│       ├── view.py         # snippet viewer + actions
│       └── tag.py          # tag cloud + management
└── tests/
    └── test_core.py        # storage / embedder / display tests
```

## Data & privacy

All data lives under `~/.config/snippet-vault/` (override with `SNIPPET_VAULT_DIR`):

- `data/vault.db` — snippets, tags, embeddings.
- `data/embeddings/models/` — cached model weights.

No network calls after first model download. No telemetry.

## Development

```bash
pip install -e ".[dev]"
pytest                 # core logic tests (no model required)
ruff check .           # lint
```

## License

MIT
