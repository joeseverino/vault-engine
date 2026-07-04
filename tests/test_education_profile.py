"""The second schema profile — proof the engine governs a non-ops vault.

EDUCATION_PROFILE is a SchemaProfile with its own doc-types, statuses, and id
prefixes. The same write path validates against whichever profile it's handed,
so a Labs server and an Education server differ only by the profile their context
carries — the whole point of the engine extraction.
"""

from __future__ import annotations

from vault_engine import schema
from vault_engine.config import Config
from vault_engine.schema import EDUCATION_PROFILE, LABS_PROFILE
from vault_engine.vault import VaultLoader
from vault_engine.vault_write_service import add_frontmatter


def test_education_profile_is_a_distinct_coherent_contract() -> None:
    edu = EDUCATION_PROFILE.as_dict()
    assert EDUCATION_PROFILE.name == "education"
    assert edu["doc_types"] == [
        "assignment", "course", "course_note", "resource", "task",
    ]
    assert edu["doc_id_prefixes"] == ["course-", "cnote-", "asg-", "res-", "task-"]
    # A different contract from Labs — different doc-types and prefixes.
    labs = LABS_PROFILE.as_dict()
    assert edu["doc_types"] != labs["doc_types"]
    assert set(edu["doc_id_prefixes"]) != set(labs["doc_id_prefixes"])
    # The universal task lifecycle is shared verbatim — a task is a task.
    assert edu["task_statuses"] == labs["task_statuses"]


def test_hq_schema_emit_still_the_labs_profile() -> None:
    # The contract HQ commits and validates against is unchanged by a 2nd profile.
    assert schema.as_dict() == LABS_PROFILE.as_dict()


def test_write_path_validates_against_the_handed_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SVMC_VAULT_PATH", str(tmp_path))
    runbooks = tmp_path / "03 Runbooks"
    runbooks.mkdir()
    (runbooks / "cs6250.md").write_text("# CS6250\n", encoding="utf-8")
    loader = VaultLoader(Config.from_env())

    common = dict(
        relative_path="03 Runbooks/cs6250.md",
        doc_id="course-cs6250",
        title="CS6250",
        doc_type="course",
        system="gt",
        environment="gatech",
        status="active",
        sensitivity="internal",
    )

    # Default (Labs) profile rejects an education doc_type / prefix / environment.
    rejected = add_frontmatter(loader, **common)
    assert rejected["ok"] is False
    assert "doc_type" in rejected["error"]

    # The Education profile accepts the same doc through the same code path.
    accepted = add_frontmatter(loader, profile=EDUCATION_PROFILE, **common)
    assert accepted["ok"] is True


def test_add_frontmatter_task_retrofit_rides_the_task_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SVMC_VAULT_PATH", str(tmp_path))
    backlog = tmp_path / "07 Backlog"
    backlog.mkdir()
    (backlog / "loose-todo.md").write_text("# Loose todo\n", encoding="utf-8")
    loader = VaultLoader(Config.from_env())

    # A task retrofit validates against the task lifecycle, not the doc enums —
    # this exact call used to be rejected on status.
    result = add_frontmatter(
        loader,
        relative_path="07 Backlog/loose-todo.md",
        doc_id="task-loose-todo",
        title="Loose todo",
        doc_type="task",
        system="",
        status="open",
    )
    assert result["ok"] is True
    text = (backlog / "loose-todo.md").read_text()
    assert "doc_type: task" in text
    assert "status: open" in text
    assert "effort: S" in text
    assert "priority: med" in text
    # Doc-only fields stay off the task shape.
    assert "environment:" not in text
    assert "sensitivity:" not in text

    # A doc status on a task is still rejected — per-doc-type both ways.
    (backlog / "bad.md").write_text("# Bad\n", encoding="utf-8")
    rejected = add_frontmatter(
        loader,
        relative_path="07 Backlog/bad.md",
        doc_id="task-bad",
        title="Bad",
        doc_type="task",
        system="",
        status="deprecated",
    )
    assert rejected["ok"] is False
    assert "task lifecycle" in rejected["error"]
