"""Governance plans and mutation receipts are deterministic adapter contracts."""

import pytest

from vault_engine.contracts import (
    GovernancePlan,
    MutationReceipt,
    StalePlanError,
    canonical_fingerprint,
)


def test_fingerprint_is_order_independent_for_mappings() -> None:
    assert canonical_fingerprint({"b": 2, "a": 1}) == canonical_fingerprint({"a": 1, "b": 2})


def test_plan_is_deterministic_and_rejects_stale_source() -> None:
    source = {"items": [{"id": "a", "value": 1}]}
    plan = GovernancePlan(
        operation="example.reconcile",
        effect="local_write",
        source_fingerprint=canonical_fingerprint(source),
        actions=({"action": "create", "id": "a"},),
    )
    assert plan.as_dict()["plan_id"] == plan.plan_id
    plan.require_current(source)
    with pytest.raises(StalePlanError, match="source changed"):
        plan.require_current({"items": []})


def test_receipt_is_stable_sorted_and_body_free() -> None:
    receipt = MutationReceipt(
        operation="task.create",
        entity_type="task",
        entity_id="task-example",
        changed_fields=("status", "title"),
        after_fingerprint=canonical_fingerprint({"status": "open", "title": "Example"}),
        affected_projections=("brief", "task_board"),
        metadata={"relative_path": "07 Backlog/task-example.md"},
    ).as_dict()
    assert receipt["entity"] == {"type": "task", "id": "task-example"}
    assert receipt["changed_fields"] == ["status", "title"]
    assert len(receipt["idempotency_key"]) == 64
    assert "body" not in str(receipt).lower()

