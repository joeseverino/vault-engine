# severino-vault-engine

[![PyPI](https://img.shields.io/pypi/v/severino-vault-engine.svg)](https://pypi.org/project/severino-vault-engine/)
[![Python](https://img.shields.io/pypi/pyversions/severino-vault-engine.svg)](https://pypi.org/project/severino-vault-engine/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A domain-agnostic **vault-governance engine** — the reusable core behind
[`severino-vault-mcp`](https://github.com/joeseverino/severino-vault-mcp) and
`severino-edu-mcp`. It governs a Git-backed, frontmatter-tagged Markdown vault
(Obsidian-style) and exposes that governance both as a library and as a
composable MCP tool surface.

> **Building your own MCP on this engine?** Read [`AGENTS.md`](AGENTS.md) — a
> drop-in recipe an AI coding agent can follow to stand up a conformant server
> in minutes.

## What's in it

- **`SchemaProfile`** — a vault's frontmatter contract (doc-types, statuses,
  id-prefixes, task lifecycle, and composable per-document field rules), with a
  versioned complete contract and deterministic fingerprint. One engine, many
  profiles: a different vault is a different profile, not a fork.
- **Index + search** — a lenient frontmatter index and ranked, section-scoped
  retrieval (`find_sections`) that returns menus, never raw bodies.
- **Task ledger** — `doc_type: task` docs derived from the index, with a
  validated write path.
- **Atomic writes** — a single serializer and `atomic_create_text` /
  `atomic_write_text` / `transactional_replace`, so every writer shares one
  escaping + durability rule and concurrent creates never replace each other.
- **Governance contracts** — deterministic fingerprints, stale-safe reviewable
  plans, and body-free mutation receipts shared by CLI, MCP, audit, and
  projection consumers.
- **`register_core(mcp, vaults)`**: registers the 8 core MCP tools once (find,
  gated doc read, frontmatter and link writes, the task board and writes,
  recent changes, daily progress), each routed by a `vault` argument to that
  vault's config, schema profile and sensitivity gate.

## Install

```bash
pip install severino-vault-engine        # or:  uv add severino-vault-engine
```

The import package is `vault_engine`; the distribution on PyPI is
`severino-vault-engine`. Python 3.14 or newer is required.

## Use

```python
from vault_engine.config import Config
from vault_engine.context import GovernanceContext
from vault_engine.core_tools import register_core
from vault_engine.schema import EDUCATION_PROFILE
from mcp.server.fastmcp import FastMCP

labs = GovernanceContext(Config.load("labs.toml"))
edu = GovernanceContext(Config.load("edu.toml"), profile=EDUCATION_PROFILE)
mcp = FastMCP("my-vault-mcp")
register_core(mcp, {"labs": labs, "edu": edu}, default="labs")  # + your own tool groups
```

Domain tool groups register beside it with a single vault's context; everything
generic lives here.

## One governance runtime, many adapters

MCP is the governed AI surface, not an implementation dependency for the CLI.
Both adapters compose the same in-process runtime:

```text
CLI ─┐
     ├─> GovernanceContext ─> application services ─> governed stores
MCP ─┘
```

Configuration is injectable for deterministic multi-vault composition:

```python
ctx = GovernanceContext.load(
    "~/.config/my-vault/config.toml",
    env={"SVMC_CACHE_SECONDS": "10"},
    profile=MY_PROFILE,
)
```

`ServerContext` remains a backward-compatible subclass. See
[`docs/governance-runtime.md`](docs/governance-runtime.md) for the extension
model and contracts.

## Security

Releases are published to PyPI from GitHub Actions via **OIDC Trusted
Publishing** (no long-lived API tokens) with **PEP 740 attestations**. To report
a vulnerability, see [`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE) © Joe Severino
