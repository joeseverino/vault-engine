# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `update_document_link`, an exact-match, schema-indexed Markdown link writer that refuses restricted documents and arbitrary body replacement.
- `GovernanceContext`, the transport-independent runtime shared by CLI, MCP,
  automation, and tests. `ServerContext` remains a compatible subclass.
- `Config.load(config_path, env=...)` for deterministic instance composition
  without process-global environment mutation; `Config.from_env()` is unchanged.
- `atomic_create_text`, an atomic create-if-absent primitive that cannot replace
  an existing file even under concurrent writers. Task creation now uses it.
- Generic `DocumentSchema` / `FieldSchema` profile extensions. The doctor applies
  domain-supplied requiredness, type, choice, pattern, date, and integer-bound
  rules without importing domain vocabulary into the engine.
- Versioned complete schema contracts and stable SHA-256 profile fingerprints;
  the legacy HQ-facing `SchemaProfile.as_dict()` remains unchanged.
- `GovernancePlan`, `MutationReceipt`, `canonical_fingerprint`, and stale-plan
  rejection contracts. Task creation is the first additive receipt producer.

## [0.2.0] - 2026-07-06

### Added
- `Doc.extra`: the index carries every frontmatter key the engine doesn't
  consume, values as parsed, and `to_metadata()` includes it — one parser,
  profile domain layers derive their fields from the index instead of
  re-reading files.
- `indexed_dirs` accepts `"."`: the vault root itself, non-recursive — 
  top-level docs join the index without dragging in unindexed subtrees.
- The doctor is profile-parameterized: `validate_vault(config,
  profile=<SchemaProfile>)` / `run_doctor(...)` validate any vault's
  contract, not just the built-in default (which remains the default).

## [0.1.3] - 2026-06-28

### Fixed
- README install command pointed at the wrong distribution
  (`pip install vault-engine`, an unrelated package); corrected to
  `severino-vault-engine`.

### Added
- `LICENSE` (MIT), `SECURITY.md`, `CHANGELOG.md`, and `AGENTS.md` (a recipe for
  building a conformant MCP on the engine).
- Continuous-integration workflow (ruff + pytest) on push and pull request.
- Dependabot for GitHub Actions and pip ecosystems.

### Changed
- Packaging metadata: PEP 639 `license-files`, expanded project URLs, dropped
  the deprecated license classifier.
- GitHub Actions pinned to commit SHAs and bumped to current majors (clears the
  Node 20 deprecation).

## [0.1.2] - 2026-06-28

### Added
- PyPI Trusted Publishing (OIDC) release workflow with PEP 740 attestations.

## [0.1.1] - 2026-06-27

### Changed
- `cordon-emit` made an optional `describe` extra rather than a hard dependency.

## [0.1.0] - 2026-06-27

### Added
- Initial release: `SchemaProfile`, lenient index, ranked section search, task
  ledger, atomic/transactional writes, sensitivity gate, and `register_core`.

[Unreleased]: https://github.com/joeseverino/vault-engine/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/joeseverino/vault-engine/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/joeseverino/vault-engine/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/joeseverino/vault-engine/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/joeseverino/vault-engine/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/joeseverino/vault-engine/releases/tag/v0.1.0
