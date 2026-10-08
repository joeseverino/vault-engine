"""Markdown table row parsing, shared by every table reader.

Quick Index routing and the tech-groups catalog split cells the same way.
"""


def split_row(line: str) -> list[str]:
    """Split one markdown table row into trimmed cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    """True if `cells` is a markdown header separator row (`---`, `:--:`)."""
    return bool(cells) and all(set(cell.replace(" ", "")) <= {"-", ":"} for cell in cells if cell)
