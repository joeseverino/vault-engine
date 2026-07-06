"""The doctor validates frontmatter per doc-type, exactly as the importer and
set_task_status do — so a valid task (its own status lifecycle and slimmer
required-field set) is not flagged with false errors."""

from __future__ import annotations

from pathlib import Path

from vault_engine.doctor import DoctorReport, _validate_frontmatter


def _errors(fm: dict) -> list[str]:
    report = DoctorReport(vault_path=Path("/vault"))
    _validate_frontmatter(report, "x.md", fm)
    return [f.message for f in report.findings if f.severity == "error"]


def test_valid_task_has_no_findings():
    # A task as add_task writes it: status=open, no system/environment/sensitivity.
    fm = {
        "doc_id": "task-ship-the-thing",
        "title": "Ship the thing",
        "doc_type": "task",
        "status": "open",
    }
    assert _errors(fm) == []


def test_task_status_lifecycle_is_enforced_not_the_flat_set():
    # "deprecated" is a standard-doc status, never a task status.
    errs = _errors({"doc_id": "task-x", "title": "x", "doc_type": "task", "status": "deprecated"})
    assert any("status=" in e for e in errs)


def test_standard_doc_still_requires_the_full_field_set():
    # A runbook missing system/environment/sensitivity is still flagged.
    errs = _errors({"doc_id": "rb-x", "title": "x", "doc_type": "runbook", "status": "active"})
    assert any("missing required field" in e for e in errs)


def test_standard_doc_rejects_a_task_status():
    errs = _errors({
        "doc_id": "rb-x", "title": "x", "doc_type": "runbook",
        "system": "s", "environment": "homelab", "sensitivity": "internal",
        "status": "parked",
    })
    assert any("status=" in e for e in errs)


def test_validate_frontmatter_honors_a_custom_profile():
    # The doctor is profile-parameterized: a doc valid under one profile is
    # invalid under another, from the same call site.
    from vault_engine.schema import SchemaProfile

    research = SchemaProfile(
        name="research",
        doc_types=frozenset({"paper", "task"}),
        environments=frozenset({"lab"}),
        statuses=frozenset({"draft", "active"}),
        sensitivities=frozenset({"public", "internal", "restricted"}),
        doc_id_prefixes=("paper-", "task-"),
        required_fields=("doc_id", "title", "doc_type", "status"),
        task_statuses=frozenset({"open", "done"}),
        task_required_fields=("doc_id", "title", "doc_type", "status"),
        task_fields=("status", "created"),
    )
    fm = {"doc_id": "paper-x", "title": "X", "doc_type": "paper", "status": "active"}

    report = DoctorReport(vault_path=Path("/vault"))
    _validate_frontmatter(report, "x.md", fm, research)
    assert [f.message for f in report.findings] == []

    # The same doc under the default Labs profile is a foreign domain.
    assert any("doc_type=" in e for e in _errors(fm))
