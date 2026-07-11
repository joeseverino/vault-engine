from pathlib import Path

from vault_engine.config import Config
from vault_engine.vault import VaultLoader
from vault_engine.vault_write_service import update_document_link


def _loader(tmp_path: Path, monkeypatch, *, sensitivity: str = "internal") -> tuple[VaultLoader, Path]:
    monkeypatch.setenv("SVMC_VAULT_PATH", str(tmp_path))
    path = tmp_path / "02 Infrastructure" / "doc.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\n"
        "doc_id: report-link-test\n"
        "title: Link Test\n"
        "doc_type: architecture_note\n"
        "system: test\n"
        "environment: other\n"
        "status: active\n"
        f"sensitivity: {sensitivity}\n"
        "last_reviewed: 2026-01-01\n"
        "---\n\n"
        "Open [Dashboard](https://old.example \"legacy note\").\n",
        encoding="utf-8",
    )
    return VaultLoader(Config.from_env()), path


def test_update_document_link_replaces_one_exact_link_atomically(tmp_path, monkeypatch) -> None:
    loader, path = _loader(tmp_path, monkeypatch)
    result = update_document_link(
        loader,
        "report-link-test",
        "Dashboard",
        "https://old.example",
        "https://github.com/example/dashboard",
    )
    assert result["ok"] is True
    assert result["old_href"] == "https://old.example"
    text = path.read_text(encoding="utf-8")
    assert "[Dashboard](https://github.com/example/dashboard)" in text
    assert "legacy note" not in text


def test_update_document_link_fails_closed_on_no_match(tmp_path, monkeypatch) -> None:
    loader, path = _loader(tmp_path, monkeypatch)
    before = path.read_text(encoding="utf-8")
    result = update_document_link(
        loader, "report-link-test", "Other", "https://old.example", "https://new.example"
    )
    assert result == {"ok": False, "error": "expected exactly one matching link; found 0"}
    assert path.read_text(encoding="utf-8") == before


def test_update_document_link_refuses_restricted_bodies(tmp_path, monkeypatch) -> None:
    loader, path = _loader(tmp_path, monkeypatch, sensitivity="restricted")
    before = path.read_text(encoding="utf-8")
    result = update_document_link(
        loader, "report-link-test", "Dashboard", "https://old.example", "https://new.example"
    )
    assert result == {"ok": False, "error": "restricted document bodies cannot be mutated"}
    assert path.read_text(encoding="utf-8") == before
