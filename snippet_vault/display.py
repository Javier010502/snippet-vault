"""Shared Rich rendering helpers for snippet-vault.

Implements the design spec's visual language:

* Palette: terminal-green primary, dark editor bg, Monokai text, red errors,
  gold accents/tags.
* Inline semantic similarity badge ``▰▰▰▱▱ 0.87`` on every search result.
* Fuzzy tag chips ``[#python]`` rendered in the tag accent colour.
* Syntax-highlighted code blocks (first line numbered for ``view``).
"""

from __future__ import annotations

from typing import Iterable

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from snippet_vault.config import (
    COLOUR_ACCENT,
    COLOUR_BG,
    COLOUR_ERROR,
    COLOUR_PRIMARY,
    COLOUR_TEXT,
    PREVIEW_CHARS,
)

console = Console()


# ---------------------------------------------------------------------------
# Colour short-cuts (Rich style strings)
# ---------------------------------------------------------------------------
def _c(name: str) -> str:
    return f"{name} bold"


def primary(t: str) -> Text:
    return Text(t, style=COLOUR_PRIMARY)


def accent(t: str) -> Text:
    return Text(t, style=COLOUR_ACCENT)


# ---------------------------------------------------------------------------
# Tag chips
# ---------------------------------------------------------------------------
def tag_chips(tags: Iterable[str]) -> Text:
    """Render ``[#python] [#date-parsing] ...`` style chips."""
    out = Text()
    for tag in tags:
        out.append(f"[{tag}] ", style=f"bold {COLOUR_ACCENT}")
    return out


# ---------------------------------------------------------------------------
# Similarity badge
# ---------------------------------------------------------------------------
def similarity_badge(score: float, width: int = 5) -> Text:
    """Render ``▰▰▰▱▱ 0.87`` where filled bars ~ score."""
    filled = round(max(0.0, min(1.0, score)) * width)
    bars = "▰" * filled + "▱" * (width - filled)
    bar_style = COLOUR_PRIMARY if score >= 0.5 else COLOUR_ACCENT
    badge = Text()
    badge.append(bars + " ", style=bar_style)
    badge.append(f"{score:.2f}", style=f"bold {COLOUR_TEXT}")
    return badge


# ---------------------------------------------------------------------------
# Code rendering
# ---------------------------------------------------------------------------
def detect_lexer(code: str, title: str | None = None) -> str:
    """Best-effort lexer guess from filename extension or content."""
    if title:
        for ext, lex in {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".go": "go", ".rs": "rust", ".java": "java", ".c": "c",
            ".cpp": "cpp", ".sh": "bash", ".rb": "ruby", ".php": "php",
            ".sql": "sql", ".html": "html", ".css": "css", ".json": "json",
            ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
        }.items():
            if title.lower().endswith(ext):
                return lex
    if "def " in code or "import " in code or "print(" in code:
        return "python"
    if "function" in code or "const " in code or "=>" in code:
        return "javascript"
    if "func " in code or "package " in code:
        return "go"
    return "text"


def code_panel(code: str, title: str, show_line_numbers: bool = True) -> Panel:
    lexer = detect_lexer(code, title)
    syntax = Syntax(
        code,
        lexer,
        theme="monokai",
        line_numbers=show_line_numbers,
        background_color="default",
        word_wrap=True,
    )
    return Panel(
        syntax,
        title=f"[bold]{title}[/bold]",
        title_align="left",
        border_style=COLOUR_PRIMARY,
        padding=(0, 1),
    )


def preview_text(code: str, n: int = PREVIEW_CHARS) -> str:
    first_line = code.strip().splitlines()[0] if code.strip() else ""
    first_line = first_line.strip()
    if len(first_line) >= n:
        return first_line[: n - 1].rstrip() + "…"
    return first_line


# ---------------------------------------------------------------------------
# Banners / status
# ---------------------------------------------------------------------------
def banner() -> Text:
    t = Text()
    t.append("snippet", style=f"bold {COLOUR_PRIMARY}")
    t.append("-vault", style=f"bold {COLOUR_TEXT}")
    return t


def error(msg: str) -> None:
    console.print(Text(f"✗ {msg}", style=f"bold {COLOUR_ERROR}"))


def ok(msg: str) -> None:
    console.print(Text(f"✓ {msg}", style=f"bold {COLOUR_PRIMARY}"))


def warn(msg: str) -> None:
    console.print(Text(f"⚠ {msg}", style=f"bold {COLOUR_ACCENT}"))


def panel_group(*renderables) -> Group:
    return Group(*renderables)
