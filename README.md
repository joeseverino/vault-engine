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
  id-prefixes, the task lifecycle), with `as_dict()` (HQ/CI contract) and
  `check_doc_enums()`. One engine, many profiles: a different vault is a
  different profile, not a fork.
- **Index + search** — a lenient frontmatter index and ranked, section-scoped
  retrieval (`find_sections`) that returns menus, never raw bodies.
- **Task ledger** — `doc_type: task` docs derived from the index, with a
  validated write path.
- **Atomic writes** — a single serializer and `atomic_write_text` /
  `transactional_replace`, so every writer shares one escaping + durability rule.
- **`register_core(mcp, ctx)`** — composes the generic MCP tools (search, doc
  read with a sensitivity gate, project inventory, daily progress, the task
  ledger, schema-validated frontmatter writes) onto any FastMCP server.

## Install

```bash
pip install severino-vault-engine        # or:  uv add severino-vault-engine
```

The import package is `vault_engine`; the distribution on PyPI is
`severino-vault-engine`.

## Use

```python
from vault_engine.config import Config
from vault_engine.context import ServerContext
from vault_engine.core_tools import register_core
from mcp.server.fastmcp import FastMCP

ctx = ServerContext(Config.from_env())          # your vault + profile
mcp = FastMCP("my-vault-mcp")
register_core(mcp, ctx)                          # + your own tool groups
```

The servers in the family own only their domain (writeup/topology tools, course
tools) and a thin entrypoint; everything generic lives here.

## Security

Releases are published to PyPI from GitHub Actions via **OIDC Trusted
Publishing** (no long-lived API tokens) with **PEP 740 attestations**. To report
a vulnerability, see [`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE) © Joe Severino
