"""Profiles compose domain contracts without putting domain values in the engine."""

from dataclasses import replace

import pytest

from vault_engine.config import Config
from vault_engine.doctor import validate_vault
from vault_engine.schema import LABS_PROFILE, DocumentSchema, FieldSchema

DOMAIN_SCHEMA = DocumentSchema(fields={
    "category": FieldSchema(required=True, choices=frozenset({"a", "b"})),
    "renews": FieldSchema(required=True, kind="date"),
    "notice": FieldSchema(kind="integer", minimum=0, maximum=365),
    "horizon": FieldSchema(pattern=r"\d{4}(-Q[1-4])?"),
})


def test_document_schema_validates_composable_field_rules() -> None:
    assert DOMAIN_SCHEMA.validate({
        "category": "a", "renews": "2027-01-02", "notice": "90",
        "horizon": "2027-Q2",
    }) == []
    errors = DOMAIN_SCHEMA.validate({
        "category": "x", "renews": "someday", "notice": "999",
        "horizon": "soon",
    })
    assert any("category" in error and "one of" in error for error in errors)
    assert any("ISO date" in error for error in errors)
    assert any("at most 365" in error for error in errors)
    assert any("horizon" in error and "does not match" in error for error in errors)


def test_profile_contract_and_fingerprint_are_deterministic() -> None:
    profile = replace(
        LABS_PROFILE,
        document_schemas={"runbook": DOMAIN_SCHEMA},
    )
    contract = profile.contract_dict()
    assert contract["contract_version"] == 1
    assert contract["document_schemas"]["runbook"]["category"]["choices"] == ["a", "b"]
    assert profile.fingerprint() == profile.fingerprint()
    assert len(profile.fingerprint()) == 64
    assert profile.as_dict() == LABS_PROFILE.as_dict()


def test_profile_rejects_schema_for_unknown_doc_type() -> None:
    with pytest.raises(ValueError, match="unknown doc_types"):
        replace(LABS_PROFILE, document_schemas={"renewal": DOMAIN_SCHEMA})


def test_doctor_applies_profile_document_schema(tmp_path) -> None:
    docs = tmp_path / "03 Runbooks"
    docs.mkdir(parents=True)
    (docs / "bad.md").write_text(
        "---\n"
        "doc_id: rb-bad\ntitle: Bad\ndoc_type: runbook\nsystem: test\n"
        "environment: other\nstatus: active\nsensitivity: internal\n"
        "category: x\nrenews: someday\n---\n\n# Bad\n"
    )
    profile = replace(LABS_PROFILE, document_schemas={"runbook": DOMAIN_SCHEMA})
    config = Config.load(env={"SVMC_VAULT_PATH": str(tmp_path)})
    report = validate_vault(config, profile=profile)
    messages = [finding.message for finding in report.findings]
    assert any("category" in message for message in messages)
    assert any("ISO date" in message for message in messages)
