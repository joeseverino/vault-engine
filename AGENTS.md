# AGENTS.md — build a conformant MCP on severino-vault-engine

You are an AI coding agent. A human has installed `severino-vault-engine` and
wants a Model Context Protocol (MCP) server that exposes *their* vault. This file
is your spec. Follow it top-to-bottom; it is designed to be deterministic — the
same prompt should produce the same server. Do not improvise an architecture;
compose the engine.

## What the engine gives you (don't rebuild these)

The engine is domain-agnostic. It owns: a lenient frontmatter **index**, ranked
**section search**, a **task ledger**, **atomic/transactional writes** (one
serializer, one durability rule), a **sensitivity gate** on document bodies, and
a composable **MCP tool surface**. You own only: the vault's *schema profile* and
any *domain-specific* tools.

CLI and MCP are peer adapters over `GovernanceContext`; the CLI never shells
through MCP and neither face owns business logic. Use `GovernanceContext.load`
for deterministic composition. `ServerContext` and `Config.from_env()` remain
compatibility entry points.

`register_core(mcp, ctx)` registers these 18 generic tools onto a FastMCP server:

```
find_runbook  lookup_system  search_body  read_doc  get_runbook
inventory_for_project  recent_changes  daily_progress  promote_note
task_board  task_projects  add_task  set_task_status  delete_task
reconcile_tasks  add_frontmatter  update_frontmatter  describe_commands
```

If the human's need is covered by these, you write **almost no tool code** — you
configure a vault and a profile and call `register_core`. That is the success
path. Resist adding tools that duplicate the above.

## The minimal conformant server

This is the whole server for a vault that uses the built-in Labs profile:

```python
# src/myvault_mcp/server.py
from mcp.server.fastmcp import FastMCP

from vault_engine.config import Config
from vault_engine.context import ServerContext
from vault_engine.core_tools import register_core

mcp = FastMCP("myvault-mcp")
ctx = ServerContext(Config.from_env())   # vault + active schema profile
register_core(mcp, ctx)                   # the 18 generic tools

def main() -> None:
    mcp.run()                             # stdio transport

if __name__ == "__main__":
    main()
```

Expose it as a console script in `pyproject.toml`:

```toml
[project.scripts]
myvault-mcp = "myvault_mcp.server:main"
```

That is a complete, registrable stdio MCP. Everything below is for vaults that
need a *different* schema or *extra* tools.

## Configuration is environment-first (deterministic, no hardcoding)

`Config.from_env()` reads a config file resolved from `$SVMC_CONFIG`, with env
overrides taking precedence. Never hardcode a path in code — set env. The keys
the agent will most often set:

| Env var | Meaning | Default |
| --- | --- | --- |
| `SVMC_CONFIG` | path to the TOML config file | a per-user default |
| `SVMC_VAULT_PATH` | vault root | `~/Documents/vault` |
| `SVMC_DAILY_NOTES_DIR` | daily-note subdir | `00 Inbox/Daily Note` |
| `SVMC_TOPOLOGY_PATH` | optional topology JSON | `<vault>/02 Infrastructure/Topology/topology.json` |

Register the server with the MCP host by passing these in the host's `env`
block — do not bake machine-specific paths into the package.

## Defining your own schema profile (when the Labs one doesn't fit)

A vault's frontmatter contract is a single immutable `SchemaProfile`. To support
a new domain, construct one and pass it to the context — **do not fork the
engine**:

```python
from vault_engine.schema import SchemaProfile
from vault_engine.context import ServerContext
from vault_engine.config import Config

RESEARCH_PROFILE = SchemaProfile(
    name="research",
    doc_types=frozenset({"paper", "note", "experiment", "task"}),
    environments=frozenset({"lab", "field"}),
    statuses=frozenset({"draft", "active", "archived"}),
    sensitivities=frozenset({"public", "internal", "sensitive", "restricted"}),
    doc_id_prefixes=("paper-", "note-", "exp-", "task-"),
    required_fields=("doc_id", "doc_type", "title", "status"),
    task_statuses=frozenset({"open", "blocked", "done"}),
    task_required_fields=("doc_id", "doc_type", "title", "status"),
    task_fields=("closed", "related_projects"),
)

ctx = ServerContext(Config.from_env(), profile=RESEARCH_PROFILE)
```

Rules that keep writes safe and the index honest:

- **`doc_id` is immutable** and prefixed per `doc_id_prefixes`. Validate enums
  *before* touching disk; the write tools reject docs that violate the profile.
- Keep `sensitivities` containing `restricted` — the sensitivity gate withholds
  `restricted` bodies unless a local unlock is configured. Don't weaken this.
- Tasks are a *second* profile within the vault (their own lifecycle and required
  fields). Set `task_statuses` / `task_required_fields` deliberately.
- Domain field rules belong in `document_schemas` using generic
  `DocumentSchema` / `FieldSchema` values. Never add a domain enum or field name
  to the engine framework itself. New contract consumers use `contract_dict()`
  and `fingerprint()`; do not broaden the legacy `as_dict()` wire shape.
- New documents use `atomic_create_text`; updates use `atomic_write_text`; a
  checked set uses `transactional_replace`. Do not rebuild those semantics in a
  domain layer.
- Reconciliations use `GovernancePlan` when review/apply can be separated, and
  writes may emit `MutationReceipt` for audit or projection consumers. Receipts
  are evidence, not state, and never contain bodies or secrets.

## Adding domain tools (only what the core doesn't cover)

Add tools the same way the family servers do — register a thin group on top of
the same `mcp`, pulling what you need off `ctx`:

```python
@mcp.tool()
def my_domain_tool(arg: str) -> dict:
    idx = ctx.loader.index()          # the shared lenient index
    ...
    return {"ok": True, "result": ...}   # see the response contract below
```

Hard rules — match the engine, don't diverge:

- **One response shape.** Every tool returns a single dict. Failures use exactly
  `{"ok": false, "error": "<message>"}` (singular `error`). Hosts and CLIs key
  off this.
- **No arbitrary-path / arbitrary-text write tool.** If you can't name the file
  shape, validate its fields, and report exactly what changed, it isn't a write
  tool. Route writes through the engine's serializer + atomic replace; never
  hand-roll YAML or `open(path, "w")`.
- **Read through the gate.** Surface bodies via the engine's gated readers so
  `restricted` content stays withheld. Don't add a tool that returns raw bodies.
- **Reuse the index/search/tasks** rather than re-scanning the vault.

## Verify before claiming done

```bash
uv run ruff check .        # lint
uv run pytest -q           # tests (write a regression test for each new tool)
uv run myvault-mcp         # smoke-run the stdio server
```

A new tool without a test is not done. Tests should be hermetic: build a tiny
fake vault on disk in a fixture and call the tool function directly — no running
MCP host required.

## Ship it securely (the packaging baseline)

Mirror this repo's setup so a downstream package is release-grade:

- **Trusted Publishing**, not tokens. Publish from GitHub Actions via OIDC; add
  the publisher under your project's *Publishing* settings on PyPI, and keep the
  publish job's permissions to `id-token: write` only. See this repo's
  `.github/workflows/publish.yml`.
- **Attestations on.** `pypa/gh-action-pypi-publish` emits PEP 740 provenance by
  default — leave it on.
- **Pin actions to SHAs** and let Dependabot bump them (`.github/dependabot.yml`).
- **Ship a `LICENSE`, `SECURITY.md`, `CHANGELOG.md`,** and correct install
  metadata. Make sure the README's `pip install <dist-name>` matches the real
  distribution name — a wrong name points users at someone else's package.

## Anti-patterns (these mean you've gone off-spec)

- Forking the engine to change doc-types — define a `SchemaProfile` instead.
- Re-implementing search, indexing, task tracking, or YAML writing.
- A write tool that takes a path + free text.
- Returning bodies that bypass the sensitivity gate.
- Multiple/ad-hoc error shapes instead of `{"ok": false, "error": ...}`.
- Hardcoding vault paths in code instead of reading `Config.from_env()`.
