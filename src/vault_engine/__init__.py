"""vault-engine — a domain-agnostic vault-governance engine.

The reusable core extracted from severino-vault-mcp: a frontmatter
``SchemaProfile`` framework, a lenient vault index, ranked section search, a
task ledger, atomic/transactional writes, a sensitivity gate, and a composable
MCP tool surface (``register_core``). Servers (severino-vault-mcp,
severino-edu-mcp) compose this engine against their own vault + profile; the
engine itself carries no server or domain knowledge.
"""

__version__ = "0.3.0"
