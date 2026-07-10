"""Governance runtime — the dependency bundle every adapter receives.

A :class:`GovernanceContext` carries the configured :class:`Config`, active
schema :class:`~vault_engine.schema.SchemaProfile`, and lazily-built vault
loader. MCP tool groups, CLIs, jobs, and tests pull the same governed services
from it; adapters never call each other.

The context is domain-agnostic: a domain server builds its own domain runtimes
(e.g. a writeup runtime, a site-ops runtime) from ``ctx.config`` / ``ctx.loader``
inside its own application layer. The engine never knows about them.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .config import Config
from .schema import LABS_PROFILE, SchemaProfile
from .vault import VaultLoader


class GovernanceContext:
    """A vault's configuration, schema policy, and lazily-built services.

    This is the shared in-process boundary for every adapter: an MCP server, CLI,
    TUI, scheduled job, or test should enter the same governed services through
    one context rather than reimplementing policy or calling another transport.
    """

    def __init__(self, config: Config, profile: SchemaProfile = LABS_PROFILE) -> None:
        self.config = config
        self.profile = profile
        self._loader: VaultLoader | None = None

    @property
    def loader(self) -> VaultLoader:
        if self._loader is None:
            self._loader = VaultLoader(self.config)
        return self._loader

    @classmethod
    def load(
        cls,
        config_path: str | Path | None = None,
        *,
        env: Mapping[str, str] | None = None,
        profile: SchemaProfile = LABS_PROFILE,
    ) -> GovernanceContext:
        """Compose a governed runtime from deterministic configuration inputs."""
        return cls(Config.load(config_path, env=env), profile=profile)


class ServerContext(GovernanceContext):
    """Backward-compatible MCP-era name for :class:`GovernanceContext`."""
