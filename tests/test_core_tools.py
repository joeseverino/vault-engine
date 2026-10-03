"""register_core: one registration per tool, routed per vault.

A recorder stands in for FastMCP (the engine has no mcp dependency); it keeps
the decorated callables so each test drives the real registered function.
"""

from __future__ import annotations

import shutil
import typing
from pathlib import Path

import pytest

from vault_engine.config import Config
from vault_engine.context import GovernanceContext
from vault_engine.core_tools import register_core
from vault_engine.schema import EDUCATION_PROFILE, LABS_PROFILE


class Recorder:
    def __init__(self) -> None:
        self.tools: dict[str, typing.Callable] = {}
        self.resources: dict[str, typing.Callable] = {}

    def tool(self):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorate

    def resource(self, uri, **_kwargs):
        def decorate(fn):
            self.resources[uri] = fn
            return fn

        return decorate


def _doc(path: Path, front: str, body: str = "## Goal\n\nDo the thing.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front.strip()}\n---\n\n{body}", encoding="utf-8")


def _context(root: Path, profile, tmp_path: Path) -> GovernanceContext:
    env = {
        "SVMC_CONFIG": str(tmp_path / "absent.toml"),
        "SVMC_VAULT_PATH": str(root),
        "SVMC_ALLOW_RESTRICTED_UNLOCK": "0",
        "SVMC_RESTRICTED_UNLOCK_AUDIT_LOG": str(tmp_path / f"{root.name}-audit.log"),
    }
    return GovernanceContext(Config.load(env=env), profile=profile)


@pytest.fixture
def server(tmp_path: Path) -> Recorder:
    labs = tmp_path / "labs"
    _doc(
        labs / "03 Runbooks" / "Add Proxy Host.md",
        """
doc_id: rb-add-proxy-host
title: Add Proxy Host
doc_type: runbook
system: Nginx Proxy Manager
environment: homelab
status: active
sensitivity: internal
last_reviewed: 2026-01-01
related_projects: [homelab-apps]
tags: [nginx]
""",
        "## Goal\n\nExpose a service through the proxy.\n",
    )
    (labs / "01 Projects" / "homelab-apps").mkdir(parents=True)
    (labs / "03 Runbooks" / "Untagged.md").write_text("# Untagged\n", encoding="utf-8")

    edu = tmp_path / "edu"
    _doc(
        edu / "01 Projects" / "CS6250" / "index.md",
        """
doc_id: course-cs6250
title: Computer Networks
doc_type: course
system: Georgia Tech
environment: gatech
status: active
sensitivity: internal
last_reviewed: 2026-01-01
""",
        "## Site\n\n- Routing and BGP.\n",
    )
    _doc(
        edu / "03 Runbooks" / "Exam Answers.md",
        """
doc_id: res-exam-answers
title: Exam Answers
doc_type: resource
system: Georgia Tech
environment: gatech
status: active
sensitivity: restricted
last_reviewed: 2026-01-01
""",
        "## Answers\n\nsecret body\n",
    )
    (edu / "03 Runbooks" / "Lecture.md").write_text("# Lecture\n", encoding="utf-8")

    mcp = Recorder()
    register_core(
        mcp,
        {
            "labs": _context(labs, LABS_PROFILE, tmp_path),
            "edu": _context(edu, EDUCATION_PROFILE, tmp_path),
        },
        default="labs",
    )
    return mcp


def test_registers_eight_tools_and_two_templates(server: Recorder) -> None:
    assert sorted(server.tools) == [
        "daily_progress",
        "find",
        "read_doc",
        "recent_changes",
        "set_frontmatter",
        "task_board",
        "task_write",
        "update_link",
    ]
    assert sorted(server.resources) == ["vault://{vault}/doc/{doc_id}", "vault://{vault}/quick-index"]


def test_vault_argument_is_a_literal_of_configured_names(server: Recorder) -> None:
    for name, fn in server.tools.items():
        annotation = fn.__annotations__["vault"]
        assert typing.get_origin(annotation) is typing.Literal, name
        assert typing.get_args(annotation) == ("labs", "edu"), name


def test_default_vault_must_be_configured(tmp_path: Path) -> None:
    ctx = _context(tmp_path, LABS_PROFILE, tmp_path)
    with pytest.raises(ValueError, match="default vault"):
        register_core(Recorder(), {"labs": ctx}, default="edu")
    with pytest.raises(ValueError, match="at least one vault"):
        register_core(Recorder(), {})


def test_unknown_vault_is_refused(server: Recorder) -> None:
    with pytest.raises(ValueError, match="unknown vault 'life'"):
        server.tools["find"]("proxy", vault="life")


def test_find_routes_to_the_named_vault(server: Recorder) -> None:
    find = server.tools["find"]
    labs = find("proxy host")
    assert labs["vault"] == "labs" and labs["mode"] == "relevance" and labs["match_count"] == 1
    assert [h["doc_id"] for h in labs["hits"]] == ["rb-add-proxy-host"]
    assert find("proxy host", vault="edu")["hits"] == []
    assert [h["doc_id"] for h in find("networks", vault="edu")["hits"]] == ["course-cs6250"]


def test_find_system_and_project_modes(server: Recorder) -> None:
    find = server.tools["find"]
    by_system = find("nginx", by="system")
    assert by_system["match_count"] == 1 and by_system["hits"][0]["doc_id"] == "rb-add-proxy-host"
    by_project = find("homelab-apps", by="project")
    assert [h["doc_id"] for h in by_project["hits"]] == ["rb-add-proxy-host"]
    assert find("homelab-apps", by="project", vault="edu")["match_count"] == 0


@pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep not installed")
def test_find_text_never_searches_restricted_bodies(server: Recorder) -> None:
    find = server.tools["find"]
    assert find("secret body", by="text", vault="edu")["match_count"] == 0
    hits = find("routing and bgp", by="text", vault="edu")
    assert hits["match_count"] == 1
    assert [h["doc_id"] for h in hits["hits"]] == ["course-cs6250"]
    assert hits["hits"][0]["snippets"]


def test_read_doc_is_scoped_to_its_vault(server: Recorder) -> None:
    read = server.tools["read_doc"]
    found = read("rb-add-proxy-host")
    assert found["found"] and found["body_released"] and "Expose a service" in found["body"]
    assert read("rb-add-proxy-host", vault="edu")["found"] is False


def test_restricted_body_stays_gated_per_vault(server: Recorder) -> None:
    read = server.tools["read_doc"]
    withheld = read("res-exam-answers", vault="edu")
    assert withheld["body_released"] is False and "body" not in withheld
    assert withheld["unlock"]["result"] == "not_requested"
    requested = read("res-exam-answers", vault="edu", include_restricted=True)
    assert requested["body_released"] is False and "body" not in requested
    assert requested["unlock"]["result"] == "disabled"


def test_resources_render_per_vault(server: Recorder) -> None:
    doc = server.resources["vault://{vault}/doc/{doc_id}"]
    assert "Routing and BGP" in doc("edu", "course-cs6250")
    assert "Not Found" in doc("labs", "course-cs6250")
    assert "secret body" not in doc("edu", "res-exam-answers")


def test_set_frontmatter_validates_against_each_vaults_profile(server: Recorder) -> None:
    write = server.tools["set_frontmatter"]
    fields = dict(doc_id="course-cs6200", title="Lecture", doc_type="course", system="Georgia Tech", environment="gatech")
    rejected = write("03 Runbooks/Untagged.md", **fields)
    assert rejected["ok"] is False and "doc_type" in rejected["error"]
    created = write("03 Runbooks/Lecture.md", vault="edu", **fields)
    assert created["ok"] is True
    assert server.tools["read_doc"]("course-cs6200", vault="edu")["found"] is True


def test_set_frontmatter_create_needs_identity_fields(server: Recorder) -> None:
    result = server.tools["set_frontmatter"]("03 Runbooks/Untagged.md", title="Untagged")
    assert result["ok"] is False
    assert "doc_id" in result["error"] and "doc_type" in result["error"]


def test_set_frontmatter_create_merges_add_lists(server: Recorder) -> None:
    result = server.tools["set_frontmatter"](
        "03 Runbooks/Untagged.md",
        doc_id="rb-untagged",
        title="Untagged",
        doc_type="runbook",
        system="misc",
        tags=["one"],
        add_tags=["two"],
    )
    assert result["ok"] is True
    hit = server.tools["find"]("untagged", by="system")["hits"][0]
    assert hit["tags"] == ["one", "two"]


def test_set_frontmatter_updates_in_place_and_keeps_doc_id(server: Recorder) -> None:
    write = server.tools["set_frontmatter"]
    renamed = write("03 Runbooks/Add Proxy Host.md", doc_id="rb-other")
    assert renamed["ok"] is False and "immutable" in renamed["error"]
    updated = write("03 Runbooks/Add Proxy Host.md", add_tags=["proxy"], status="deprecated")
    assert updated["ok"] is True and updated["changed_fields"] == ["status", "tags"]


def test_task_write_validates_per_action(server: Recorder) -> None:
    task_write = server.tools["task_write"]
    assert "requires title" in task_write("add")["error"]
    assert "requires doc_id, status" in task_write("status")["error"]
    assert "requires note_path" in task_write("promote", title="x")["error"]
    assert "unknown action" in task_write("archive")["error"]


def test_tasks_stay_in_their_vault(server: Recorder) -> None:
    task_write, board = server.tools["task_write"], server.tools["task_board"]
    added = task_write("add", vault="edu", title="Finish the BGP lab")
    assert added["ok"] is True
    doc_id = added["doc_id"]
    assert [t["doc_id"] for t in board(vault="edu")["tasks"]] == [doc_id]
    assert board()["tasks"] == []
    assert task_write("status", vault="edu", doc_id=doc_id, status="done")["ok"] is True
    assert board(vault="edu")["tasks"] == []


def test_task_board_lists_the_projects_tasks_can_go_in(server: Recorder) -> None:
    projects = server.tools["task_board"]()["projects"]
    assert [p["slug"] for p in projects] == ["homelab-apps"]
