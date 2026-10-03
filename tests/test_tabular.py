"""Tests for markdown table row parsing."""

from __future__ import annotations

from vault_engine import tabular


def test_split_row_trims_cells() -> None:
    assert tabular.split_row("| a | b c |  d|") == ["a", "b c", "d"]


def test_is_separator() -> None:
    assert tabular.is_separator(["---", ":--:", "--:"])
    assert not tabular.is_separator(["---", "x"])
    assert not tabular.is_separator([])
