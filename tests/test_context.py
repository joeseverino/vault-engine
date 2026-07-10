"""CLI and MCP adapters compose the same transport-independent governance context."""

from vault_engine.context import GovernanceContext, ServerContext
from vault_engine.schema import EDUCATION_PROFILE


def test_governance_context_loads_explicit_instance_and_profile(tmp_path) -> None:
    config = tmp_path / "edu.toml"
    config.write_text(f'[vault]\npath = "{tmp_path / "vault"}"\n')
    ctx = GovernanceContext.load(config, env={}, profile=EDUCATION_PROFILE)
    assert ctx.config.vault_path == tmp_path / "vault"
    assert ctx.profile is EDUCATION_PROFILE
    assert ctx.loader.config is ctx.config


def test_server_context_remains_a_governance_context(tmp_path) -> None:
    ctx = ServerContext.load(env={"SVMC_VAULT_PATH": str(tmp_path)})
    assert isinstance(ctx, GovernanceContext)
