"""Deterministic governance contracts shared by CLI, MCP, and domain layers.

These values carry no vault or domain policy. They standardize how governed
services identify inputs, present reviewable plans, reject stale applications,
and report completed mutations across any adapter.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


def canonical_fingerprint(value: Any) -> str:
    """Return a stable SHA-256 identity for JSON-compatible structured data."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class StalePlanError(RuntimeError):
    """Raised when authoritative inputs changed after a plan was reviewed."""


@dataclass(frozen=True)
class GovernancePlan:
    """A deterministic, reviewable plan over one authoritative source state."""

    operation: str
    effect: str
    source_fingerprint: str
    actions: Sequence[Mapping[str, Any]]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "actions",
            tuple(MappingProxyType(dict(action)) for action in self.actions),
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))

    @property
    def plan_id(self) -> str:
        return canonical_fingerprint(self._content())

    def _content(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "effect": self.effect,
            "source_fingerprint": self.source_fingerprint,
            "actions": [dict(action) for action in self.actions],
            "warnings": list(self.warnings),
        }

    def as_dict(self) -> dict[str, Any]:
        return {"plan_version": 1, "plan_id": self.plan_id, **self._content()}

    def require_current(self, current_source: Any) -> None:
        current = canonical_fingerprint(current_source)
        if current != self.source_fingerprint:
            raise StalePlanError(
                "authoritative source changed after this plan was created; "
                "generate and review a new plan"
            )


@dataclass(frozen=True)
class MutationReceipt:
    """Standard receipt for a completed governed mutation.

    Receipts are evidence, never a second source of truth. Consumers may use
    them for audit, projection invalidation, or UI output; authoritative state
    remains rebuildable without them.
    """

    operation: str
    entity_type: str
    entity_id: str
    changed_fields: tuple[str, ...] = ()
    before_fingerprint: str | None = None
    after_fingerprint: str | None = None
    affected_projections: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_fields", tuple(sorted(self.changed_fields)))
        object.__setattr__(
            self, "affected_projections", tuple(sorted(self.affected_projections))
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def idempotency_key(self) -> str:
        return canonical_fingerprint({
            "operation": self.operation,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "after_fingerprint": self.after_fingerprint,
            "changed_fields": list(self.changed_fields),
        })

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "receipt_version": 1,
            "operation": self.operation,
            "entity": {"type": self.entity_type, "id": self.entity_id},
            "changed_fields": list(self.changed_fields),
            "affected_projections": list(self.affected_projections),
            "idempotency_key": self.idempotency_key,
            "metadata": dict(self.metadata),
        }
        if self.before_fingerprint is not None:
            data["before_fingerprint"] = self.before_fingerprint
        if self.after_fingerprint is not None:
            data["after_fingerprint"] = self.after_fingerprint
        return data

