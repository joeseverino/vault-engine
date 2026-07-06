"""Doc.extra — the lossless remainder: one parser, profile domain layers derive."""

from __future__ import annotations

from vault_engine.config import Config
from vault_engine.vault import VaultLoader


def _loader(tmp_path, monkeypatch):
    (tmp_path / "Notes").mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[vault]\npath = "{tmp_path}"\nindexed_dirs = ["Notes"]\n')
    monkeypatch.setenv("SVMC_CONFIG", str(cfg))
    monkeypatch.delenv("SVMC_VAULT_PATH", raising=False)
    return VaultLoader(Config.from_env())


def test_unconsumed_keys_land_in_extra(tmp_path, monkeypatch):
    loader = _loader(tmp_path, monkeypatch)
    (tmp_path / "Notes" / "a.md").write_text(
        "---\n"
        "doc_id: note-a\ntitle: A\ndoc_type: runbook\nsystem: x\n"
        "environment: other\nstatus: active\nsensitivity: internal\n"
        "expires: 2027-05-31\nlead_days: 30\n"
        "---\n\n# A\n"
    )
    (doc,) = loader.index().docs
    assert doc.extra == {"expires": "2027-05-31", "lead_days": "30"}


def test_core_fields_never_duplicated_into_extra(tmp_path, monkeypatch):
    loader = _loader(tmp_path, monkeypatch)
    (tmp_path / "Notes" / "b.md").write_text(
        "---\ndoc_id: note-b\ntitle: B\ndoc_type: runbook\nsystem: x\n"
        "environment: other\nstatus: active\nsensitivity: internal\ntags: [t]\n"
        "---\n\n# B\n"
    )
    (doc,) = loader.index().docs
    assert doc.extra == {}
    assert doc.to_metadata()["extra"] == {}


def test_extra_rides_metadata(tmp_path, monkeypatch):
    loader = _loader(tmp_path, monkeypatch)
    (tmp_path / "Notes" / "c.md").write_text(
        "---\ndoc_id: note-c\ntitle: C\ndoc_type: runbook\nsystem: x\n"
        "environment: other\nstatus: active\nsensitivity: internal\ncustom: v\n"
        "---\n\n# C\n"
    )
    (doc,) = loader.index().docs
    assert doc.to_metadata()["extra"] == {"custom": "v"}
