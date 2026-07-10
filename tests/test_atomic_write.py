"""The write substrate is durable, atomic, and explicit about create vs replace."""

import pytest

from vault_engine.atomic_write import atomic_create_text


def test_atomic_create_writes_a_new_file(tmp_path) -> None:
    path = tmp_path / "new.md"
    atomic_create_text(path, "complete\n")
    assert path.read_text() == "complete\n"
    assert not list(tmp_path.glob(".new.md.svmc-create-*"))


def test_atomic_create_never_replaces_existing_content(tmp_path) -> None:
    path = tmp_path / "existing.md"
    path.write_text("original\n")
    with pytest.raises(FileExistsError):
        atomic_create_text(path, "replacement\n")
    assert path.read_text() == "original\n"
    assert not list(tmp_path.glob(".existing.md.svmc-create-*"))
