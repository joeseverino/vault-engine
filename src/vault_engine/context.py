"""Server runtime context — the dependency bundle each tool group receives.

A :class:`ServerContext` carries the configured :class:`Config`, the active
schema :class:`~vault_engine.schema.SchemaProfile`, and a lazily-built vault
loader. Tool groups register as ``register(mcp, ctx)`` and pull what they need
off it, so a server composes only the groups it wants.

The context is domain-agnostic: a domain server builds its own domain runtimes
(e.g. a writeup runtime, a site-ops runtime) from ``ctx.config`` / ``ctx.loader``
inside its own tool groups. The engine never knows about them.
"""

from __future__ import annotations

from .config import Config
from .schema import LABS_PROFILE, SchemaProfile
from .vault import VaultLoader


class ServerContext:
    """A vault's Config + active profile + lazily-built loader.

    ``profile`` is the vault's frontmatter contract — the schema-validated write
    tools check against it, so two servers differ only by the profile (and vault)
    their context carries.
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
