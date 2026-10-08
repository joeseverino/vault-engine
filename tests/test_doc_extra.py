"""Doc.extra — the lossless remainder: one parser, profile domain layers derive."""

from collections.abc import Callable
from pathlib import Path

from vault_engine.vault import VaultLoader


def test_unconsumed_keys_land_in_extra(
    tmp_path: Path, vault_loader: Callable[..., VaultLoader]
) -> None:
    loader = vault_loader()
    (tmp_path / "Notes" / "a.md").write_text(
        "---\n"
        "doc_id: note-a\ntitle: A\ndoc_type: runbook\nsystem: x\n"
        "environment: other\nstatus: active\nsensitivity: internal\n"
        "expires: 2027-05-31\nlead_days: 30\n"
        "---\n\n# A\n"
    )
    (doc,) = loader.index().docs
    assert doc.extra == {"expires": "2027-05-31", "lead_days": "30"}


def test_core_fields_never_duplicated_into_extra(
    tmp_path: Path, vault_loader: Callable[..., VaultLoader]
) -> None:
    loader = vault_loader()
    (tmp_path / "Notes" / "b.md").write_text(
        "---\ndoc_id: note-b\ntitle: B\ndoc_type: runbook\nsystem: x\n"
        "environment: other\nstatus: active\nsensitivity: internal\ntags: [t]\n"
        "---\n\n# B\n"
    )
    (doc,) = loader.index().docs
    assert doc.extra == {}
    assert doc.to_metadata()["extra"] == {}


def test_extra_rides_metadata(tmp_path: Path, vault_loader: Callable[..., VaultLoader]) -> None:
    loader = vault_loader()
    (tmp_path / "Notes" / "c.md").write_text(
        "---\ndoc_id: note-c\ntitle: C\ndoc_type: runbook\nsystem: x\n"
        "environment: other\nstatus: active\nsensitivity: internal\ncustom: v\n"
        "---\n\n# C\n"
    )
    (doc,) = loader.index().docs
    assert doc.to_metadata()["extra"] == {"custom": "v"}


def test_dot_indexes_vault_root_non_recursively(
    tmp_path: Path, vault_loader: Callable[..., VaultLoader]
) -> None:
    (tmp_path / "Hidden").mkdir()
    loader = vault_loader((".", "Notes"))

    fm = (
        "---\ndoc_id: note-{n}\ntitle: N\ndoc_type: runbook\nsystem: x\n"
        "environment: other\nstatus: active\nsensitivity: internal\n---\n\n# N\n"
    )
    (tmp_path / "Root.md").write_text(fm.format(n="root"))
    (tmp_path / "Notes" / "a.md").write_text(fm.format(n="a"))
    (tmp_path / "Hidden" / "b.md").write_text(fm.format(n="hidden"))

    idx = loader.index()
    assert "note-root" in idx.by_doc_id  # root file joins
    assert "note-a" in idx.by_doc_id  # named dir still walked
    assert "note-hidden" not in idx.by_doc_id  # unindexed subtree stays out
