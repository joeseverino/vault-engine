"""Canonical frontmatter schema — the profile framework plus the Labs profile.

A :class:`SchemaProfile` is the engine-generic unit: a named bundle of the enum
sets and id prefixes that decide what counts as a valid indexed doc, with the
logic to emit itself as JSON and to check a human schema doc against itself. The
framework carries no domain knowledge — a second vault (Education) registers its
own profile with different doc-types and statuses; only the values differ.

``LABS_PROFILE`` is the canonical Severino Labs ops profile. The MCP validates
writes against it, and Severino HQ consumes ``LABS_PROFILE.as_dict()`` (emitted by
``severino-vault-mcp schema --json``, committed to HQ and checked against this
module) so the two systems cannot drift on what ``hq sync`` will accept.

The module-level names (``DOC_TYPES``, ``as_dict``, ``check_doc_enums`` …) are the
Labs profile's fields and methods, kept as backward-compatible aliases so existing
imports keep working as the engine is extracted. Edit the Labs values here and
nowhere else.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class FieldSchema:
    """One domain-supplied frontmatter field rule.

    The engine owns these generic mechanics; profiles own every domain value.
    Rules intentionally describe the constrained YAML values the engine already
    parses, keeping validation deterministic and dependency-free.
    """

    required: bool = False
    kind: str = "string"
    choices: frozenset[str] = frozenset()
    pattern: str | None = None
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"string", "integer", "boolean", "list", "date"}:
            raise ValueError(f"unknown field kind: {self.kind!r}")
        if self.pattern is not None:
            re.compile(self.pattern)
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("field minimum cannot exceed maximum")

    def validate(self, name: str, value: Any) -> list[str]:
        if value in (None, "", []):
            return [f"missing required field: {name}"] if self.required else []

        errors: list[str] = []
        parsed_integer: int | None = None
        if self.kind == "integer":
            try:
                if isinstance(value, bool):
                    raise ValueError
                parsed_integer = int(str(value))
            except ValueError:
                errors.append(f"{name} must be an integer")
        elif self.kind == "boolean" and not isinstance(value, bool):
            errors.append(f"{name} must be a boolean")
        elif self.kind == "list" and not isinstance(value, list):
            errors.append(f"{name} must be a list")
        elif self.kind == "date":
            try:
                date.fromisoformat(str(value))
            except ValueError:
                errors.append(f"{name} must be an ISO date (YYYY-MM-DD)")
        elif self.kind == "string" and not isinstance(value, str):
            errors.append(f"{name} must be a string")

        text = str(value)
        if self.choices and text not in self.choices:
            errors.append(f"{name}={value!r} must be one of: {', '.join(sorted(self.choices))}")
        if self.pattern and re.fullmatch(self.pattern, text) is None:
            errors.append(f"{name}={value!r} does not match {self.pattern!r}")
        if parsed_integer is not None:
            if self.minimum is not None and parsed_integer < self.minimum:
                errors.append(f"{name} must be at least {self.minimum}")
            if self.maximum is not None and parsed_integer > self.maximum:
                errors.append(f"{name} must be at most {self.maximum}")
        return errors

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind, "required": self.required}
        if self.choices:
            data["choices"] = sorted(self.choices)
        if self.pattern is not None:
            data["pattern"] = self.pattern
        if self.minimum is not None:
            data["minimum"] = self.minimum
        if self.maximum is not None:
            data["maximum"] = self.maximum
        return data


@dataclass(frozen=True)
class DocumentSchema:
    """Composable field contract for one ``doc_type``."""

    fields: Mapping[str, FieldSchema]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def validate(self, data: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        for name, rule in self.fields.items():
            errors.extend(rule.validate(name, data.get(name)))
        return errors

    def as_dict(self) -> dict[str, Any]:
        return {name: self.fields[name].as_dict() for name in sorted(self.fields)}


@dataclass(frozen=True)
class SchemaProfile:
    """One vault's frontmatter contract: its enum sets, prefixes, and task lifecycle.

    Tasks are a second schema profile *within* a vault, not just another doc_type:
    a task carries its own lifecycle vocabulary (a runbook can never be "parked")
    and a slimmer required-field set. The write path branches on doc_type to
    validate against the right one; everything else (the lenient index, search, the
    graph) treats a task like any other doc.
    """

    name: str
    doc_types: frozenset[str]
    environments: frozenset[str]
    statuses: frozenset[str]
    sensitivities: frozenset[str]
    doc_id_prefixes: tuple[str, ...]
    required_fields: tuple[str, ...]
    task_statuses: frozenset[str]
    task_required_fields: tuple[str, ...]
    # The fields the task write path manages beyond the shared ones: a task closes
    # the loop with `closed:` (kept, not deleted) and associates to its project(s)
    # through the relation registry (related_projects), not a parallel id.
    task_fields: tuple[str, ...]
    document_schemas: Mapping[str, DocumentSchema] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.document_schemas) - set(self.doc_types)
        if unknown:
            raise ValueError(
                f"document schemas reference unknown doc_types: {sorted(unknown)}"
            )
        object.__setattr__(
            self,
            "document_schemas",
            MappingProxyType(dict(self.document_schemas)),
        )

    def as_dict(self) -> dict[str, list[str]]:
        """Return the profile as a deterministic, JSON-serializable dict.

        Set-valued fields are sorted so the emitted JSON is byte-stable across
        runs; ordered fields (prefixes, required fields) keep their declared
        order. For the Labs profile this is the exact shape HQ commits and
        validates against.
        """
        return {
            "doc_types": sorted(self.doc_types),
            "environments": sorted(self.environments),
            "statuses": sorted(self.statuses),
            "sensitivities": sorted(self.sensitivities),
            "doc_id_prefixes": list(self.doc_id_prefixes),
            "required_fields": list(self.required_fields),
            "task_statuses": sorted(self.task_statuses),
            "task_required_fields": list(self.task_required_fields),
        }

    def _enum_fields(self) -> dict[str, frozenset[str]]:
        return {
            "doc_type": self.doc_types,
            "environment": self.environments,
            "status": self.statuses,
            "sensitivity": self.sensitivities,
        }

    def validate_document(self, data: Mapping[str, Any]) -> list[str]:
        """Validate the domain fields for the document's declared type."""
        doc_type = str(data.get("doc_type") or "")
        contract = self.document_schemas.get(doc_type)
        return contract.validate(data) if contract is not None else []

    def contract_dict(self) -> dict[str, Any]:
        """Emit the complete, versioned profile contract deterministically.

        ``as_dict`` remains the legacy HQ wire shape. New consumers should use
        this representation, whose explicit version permits additive evolution.
        """
        return {
            "contract_version": 1,
            "name": self.name,
            **self.as_dict(),
            "task_fields": list(self.task_fields),
            "document_schemas": {
                name: self.document_schemas[name].as_dict()
                for name in sorted(self.document_schemas)
            },
        }

    def fingerprint(self) -> str:
        """Return a stable SHA-256 identity for the complete profile contract."""
        encoded = json.dumps(
            self.contract_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def check_doc_enums(self, text: str) -> list[str]:
        """Compare a human schema doc's enum lines to this profile's sets.

        A schema doc documents each enum as a pipe-separated line
        (``doc_type: a | b | c``). This finds the first such list per field and
        reports any divergence from the canonical sets, so the human doc cannot
        silently drift from the profile. Returns human-readable mismatches; empty
        means the doc is current.
        """
        pattern = re.compile(
            r"^\s*(doc_type|environment|status|sensitivity)\s*:\s*(.+?)\s*$"
        )
        found: dict[str, set[str]] = {}
        for line in text.splitlines():
            match = pattern.match(line)
            if not match:
                continue
            field, rhs = match.group(1), match.group(2)
            rhs = rhs.split("#", 1)[0]  # strip trailing comment
            tokens = {token.strip() for token in rhs.split("|") if token.strip()}
            if len(tokens) <= 1:
                continue  # a single example value, not the enum list
            # The schema doc also documents the task lifecycle on its own `status:`
            # line; it is validated as the task profile, not the standard one, so
            # skip it here regardless of where it appears (order-independent).
            if field == "status" and tokens == set(self.task_statuses):
                continue
            found.setdefault(field, tokens)

        mismatches: list[str] = []
        for field, canonical in self._enum_fields().items():
            documented = found.get(field)
            if documented is None:
                mismatches.append(f"{field}: no enum list found in the doc")
                continue
            if documented != set(canonical):
                parts = []
                if extra := sorted(documented - set(canonical)):
                    parts.append(f"doc lists unknown {extra}")
                if missing := sorted(set(canonical) - documented):
                    parts.append(f"doc is missing {missing}")
                mismatches.append(f"{field}: " + "; ".join(parts))
        return mismatches


# The canonical Severino Labs ops profile. Edit these values, nowhere else.
LABS_PROFILE = SchemaProfile(
    name="labs",
    doc_types=frozenset({
        "runbook", "architecture_note", "deployment_guide",
        "troubleshooting_guide", "recovery_procedure",
        "public_article_draft", "decision_record",
        "task",
    }),
    environments=frozenset({
        "homelab", "vps", "wordpress", "cloudflare", "tailscale",
        "adguard", "unifi", "local_mac", "other",
    }),
    statuses=frozenset({"draft", "active", "deprecated", "archived"}),
    sensitivities=frozenset({"public", "internal", "sensitive", "restricted"}),
    doc_id_prefixes=("rb-", "infra-", "report-", "project-", "note-", "task-"),
    required_fields=(
        "doc_id", "title", "doc_type", "system", "environment", "status",
        "sensitivity",
    ),
    task_statuses=frozenset({"open", "active", "parked", "done", "wontfix"}),
    task_required_fields=("doc_id", "title", "doc_type", "status"),
    task_fields=(
        "status", "related_projects", "effort", "priority", "created", "closed",
    ),
)

# A second profile, proving the framework parameterizes a non-ops vault: the
# Georgia Tech / education vault. Courses, course notes, and assignments instead
# of runbooks; a course lifecycle instead of doc statuses; a lighter required-field
# set (no system / environment / sensitivity). The universal task lifecycle is
# reused verbatim — a task is a task in any vault.
EDUCATION_PROFILE = SchemaProfile(
    name="education",
    doc_types=frozenset({
        "course", "course_note", "assignment", "resource", "task",
    }),
    environments=frozenset({"gatech", "cert", "other"}),
    statuses=frozenset({
        "upcoming", "active", "completed", "dropped", "draft", "archived",
    }),
    sensitivities=frozenset({"public", "internal"}),
    doc_id_prefixes=("course-", "cnote-", "asg-", "res-", "task-"),
    required_fields=("doc_id", "title", "doc_type", "status"),
    task_statuses=frozenset({"open", "active", "parked", "done", "wontfix"}),
    task_required_fields=("doc_id", "title", "doc_type", "status"),
    task_fields=(
        "status", "related_projects", "effort", "priority", "created", "closed",
    ),
)


# Backward-compatible module-level names: the Labs profile is the default vault
# contract, so these aliases keep existing `from .schema import DOC_TYPES`-style
# imports working unchanged through the engine extraction.
DOC_TYPES = LABS_PROFILE.doc_types
ENVIRONMENTS = LABS_PROFILE.environments
STATUSES = LABS_PROFILE.statuses
SENSITIVITIES = LABS_PROFILE.sensitivities
DOC_ID_PREFIXES = LABS_PROFILE.doc_id_prefixes
REQUIRED_FIELDS = LABS_PROFILE.required_fields
TASK_STATUSES = LABS_PROFILE.task_statuses
TASK_REQUIRED_FIELDS = LABS_PROFILE.task_required_fields
TASK_FIELDS = LABS_PROFILE.task_fields


def as_dict() -> dict[str, list[str]]:
    """Emit the canonical Labs schema (the shape HQ commits and validates)."""
    return LABS_PROFILE.as_dict()


def check_doc_enums(text: str) -> list[str]:
    """Check a human schema doc against the canonical Labs profile."""
    return LABS_PROFILE.check_doc_enums(text)
