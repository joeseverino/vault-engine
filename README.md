# vault-engine

A domain-agnostic **vault-governance engine** — the reusable core behind
[`severino-vault-mcp`](https://github.com/joeseverino/severino-vault-mcp) and
`severino-edu-mcp`. It governs a Git-backed, frontmatter-tagged Markdown vault
(Obsidian-style) and exposes that governance both as a library and as a
composable MCP tool surface.

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
pip install vault-engine        # or:  uv add vault-engine
```

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
