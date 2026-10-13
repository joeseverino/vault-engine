"""Tests for markdown table row parsing."""

import pytest

from vault_engine import tabular


def test_split_row_trims_cells() -> None:
    assert tabular.split_row("| a | b c |  d|") == ["a", "b c", "d"]


@pytest.mark.parametrize(
    ("cells", "expected"),
    [
        (["---", ":--:", "--:"], True),
        (["---", "x"], False),
        ([], False),
    ],
)
def test_is_separator(cells: list[str], expected: bool) -> None:
    assert tabular.is_separator(cells) is expected
