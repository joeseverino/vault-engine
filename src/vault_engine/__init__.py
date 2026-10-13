"""vault-engine — a domain-agnostic vault-governance engine.

The reusable core extracted from severino-vault-mcp: a frontmatter
``SchemaProfile`` framework, a lenient vault index, ranked section search, a
task ledger, atomic/transactional writes, a sensitivity gate, and a composable
MCP tool surface (``register_core``) that serves any number of vaults from one
server. Servers compose it against their own vaults and profiles; the engine
itself carries no server or domain knowledge.
"""

__version__ = "2.0.0"  # x-release-please-version
