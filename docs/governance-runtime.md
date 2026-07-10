# Governance runtime

The engine is the policy and application layer beneath every interface. MCP,
CLI, TUI, automation, and tests are adapters; none calls another transport and
none reimplements indexing, schema validation, sensitivity, paths, or writes.

```text
adapter -> GovernanceContext -> application service -> governed store
```

## Composition

`GovernanceContext` carries one immutable `Config`, one `SchemaProfile`, and a
lazy shared `VaultLoader`. `GovernanceContext.load()` accepts an explicit config
path and environment mapping. `Config.from_env()` and `ServerContext` remain
compatible entry points for existing servers.

Domain servers compose private policy rather than fork the engine. The CLI
receives the same context and calls the same domain services directly.

## Schema extension

`SchemaProfile.document_schemas` maps a `doc_type` to a `DocumentSchema`. Each
field uses a dependency-free `FieldSchema`: requiredness, scalar kind, choices,
regex, and integer bounds. The engine owns validation mechanics; the domain owns
all vocabulary.

`SchemaProfile.as_dict()` is the frozen legacy schema surface. New consumers use
`contract_dict()` and `fingerprint()`, which include per-document rules under an
explicit contract version.

## Writes and reconciliation

- `atomic_create_text` creates only when absent, even with concurrent writers.
- `atomic_write_text` replaces one existing projection or document atomically.
- `transactional_replace` applies a checked multi-file set with rollback.
- `GovernancePlan` binds reviewed actions to a source fingerprint and rejects a
  stale apply.
- `MutationReceipt` reports what changed without becoming another store of
  truth. Receipts are suitable for audit and projection invalidation and must not
  contain document bodies or secrets.

This division keeps emit-once/derive-everywhere recoverable: authoritative stores
can always rebuild projections even if plans, receipts, or caches disappear.
