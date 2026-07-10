"""Configuration from TOML plus environment-variable overrides.

The package is single-user by design: it runs locally as a stdio MCP server
and reads files the local account can already read. A config file keeps
personal vault paths and integration details out of the repository, while
environment variables remain convenient for tests and one-off runs.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = "~/.config/severino-vault-mcp/config.toml"


def _expand_path(raw: str | Path) -> Path:
    return Path(os.path.expanduser(str(raw)))


def _env_path(env: Mapping[str, str], name: str, default: str | Path) -> Path:
    raw = env.get(name)
    if raw is None:
        return _expand_path(default)
    return _expand_path(raw)


def _env_list(
    env: Mapping[str, str], name: str, default: tuple[str, ...] | list[str]
) -> tuple[str, ...]:
    raw = env.get(name)
    if raw is None:
        return tuple(default)
    return tuple(part for part in raw.split(":") if part)


def _env_bool(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


def _value(section: dict[str, Any], key: str, default: Any) -> Any:
    value = section.get(key, default)
    return default if value is None else value


@dataclass(frozen=True)
class Config:
    vault_path: Path
    indexed_dirs: tuple[str, ...]
    daily_notes_dir: str
    aliases_path: Path
    topology_path: Path
    infra_datasets_path: Path
    metadata_url: str
    cache_seconds: int
    allow_secret_adjacent_unlock: bool
    secret_unlock_hash: str | None
    secret_unlock_hash_file: Path
    secret_unlock_keychain_service: str
    secret_unlock_keychain_account: str
    secret_unlock_audit_log: Path

    @classmethod
    def from_env(cls) -> Config:
        """Backward-compatible process-environment constructor."""
        return cls.load()

    @classmethod
    def load(
        cls,
        config_path: str | Path | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> Config:
        """Load one immutable configuration from explicit, injectable inputs.

        ``env`` defaults to :data:`os.environ`; callers can pass a plain mapping
        for deterministic tests or multi-instance composition. An explicit
        ``config_path`` wins over ``SVMC_CONFIG``, which wins over the generic
        engine default. Environment values continue to override TOML values.
        """
        values = os.environ if env is None else env
        resolved_config_path = (
            _expand_path(config_path)
            if config_path is not None
            else _env_path(values, "SVMC_CONFIG", DEFAULT_CONFIG_PATH)
        )
        data = _read_config(resolved_config_path)
        vault = _section(data, "vault")
        metadata = _section(data, "metadata")
        cache = _section(data, "cache")
        # The `secret_adjacent` config section and the SVMC_SECRET_ADJACENT_*
        # env vars below are a backward-compat shim from the rename to
        # `restricted` (see schema.py). Retire them — the second leg of each
        # `os.environ.get(..., os.environ.get("SVMC_SECRET_ADJACENT_...))` — once
        # no local config predates 2026-06; tracked as cleanup, not load-bearing.
        unlock = _section(data, "restricted") or _section(data, "secret_adjacent")

        indexed_dirs = _value(
            vault,
            "indexed_dirs",
            # "07 Backlog" holds the cross-cutting task slice; project tasks
            # live under "01 Projects/<project>/tasks/" and are already covered.
            ["01 Projects", "02 Infrastructure", "03 Runbooks", "07 Backlog"],
        )
        if isinstance(indexed_dirs, str):
            indexed_dirs = [part for part in indexed_dirs.split(":") if part]

        vault_path = _env_path(
            values,
            "SVMC_VAULT_PATH",
            _value(vault, "path", "~/Documents/vault"),
        )

        aliases = _section(data, "aliases")
        aliases_default = vault_path / ".svmc" / "aliases.toml"

        topology = _section(data, "topology")
        topology_default = (
            vault_path / "02 Infrastructure" / "Topology" / "topology.json"
        )

        infra = _section(data, "infra_datasets")
        infra_default = vault_path / "02 Infrastructure" / "_infra-datasets.json"

        return cls(
            vault_path=vault_path,
            daily_notes_dir=str(
                values.get(
                    "SVMC_DAILY_NOTES_DIR",
                    _value(vault, "daily_notes_dir", "00 Inbox/Daily Note"),
                )
            ),
            aliases_path=_env_path(
                values,
                "SVMC_ALIASES_PATH",
                _value(aliases, "path", aliases_default),
            ),
            topology_path=_env_path(
                values,
                "SVMC_TOPOLOGY_PATH",
                _value(topology, "path", topology_default),
            ),
            infra_datasets_path=_env_path(
                values,
                "SVMC_INFRA_DATASETS_PATH",
                _value(infra, "path", infra_default),
            ),
            indexed_dirs=_env_list(values, "SVMC_INDEXED_DIRS", tuple(indexed_dirs)),
            metadata_url=values.get(
                "SVMC_METADATA_URL",
                str(_value(metadata, "url", "")),
            ),
            cache_seconds=int(values.get(
                "SVMC_CACHE_SECONDS",
                str(_value(cache, "seconds", 30)),
            )),
            allow_secret_adjacent_unlock=_env_bool(
                values,
                "SVMC_ALLOW_RESTRICTED_UNLOCK",
                _env_bool(
                    values,
                    "SVMC_ALLOW_SECRET_ADJACENT_UNLOCK",
                    bool(_value(unlock, "allow_unlock", False)),
                ),
            ),
            secret_unlock_hash=values.get(
                "SVMC_RESTRICTED_UNLOCK_HASH",
                values.get(
                    "SVMC_SECRET_ADJACENT_UNLOCK_HASH",
                    _value(unlock, "hash", None),
                ),
            ),
            secret_unlock_hash_file=_env_path(
                values,
                "SVMC_RESTRICTED_UNLOCK_HASH_FILE",
                values.get(
                    "SVMC_SECRET_ADJACENT_UNLOCK_HASH_FILE",
                    _value(
                        unlock,
                        "hash_file",
                        "~/.config/severino-vault-mcp/restricted-unlock.sha256",
                    ),
                ),
            ),
            secret_unlock_keychain_service=values.get(
                "SVMC_RESTRICTED_UNLOCK_KEYCHAIN_SERVICE",
                values.get(
                    "SVMC_SECRET_ADJACENT_UNLOCK_KEYCHAIN_SERVICE",
                    str(_value(unlock, "keychain_service", "severino-vault-mcp")),
                ),
            ),
            secret_unlock_keychain_account=values.get(
                "SVMC_RESTRICTED_UNLOCK_KEYCHAIN_ACCOUNT",
                values.get(
                    "SVMC_SECRET_ADJACENT_UNLOCK_KEYCHAIN_ACCOUNT",
                    str(_value(unlock, "keychain_account", "restricted-unlock")),
                ),
            ),
            secret_unlock_audit_log=_env_path(
                values,
                "SVMC_RESTRICTED_UNLOCK_AUDIT_LOG",
                values.get(
                    "SVMC_SECRET_ADJACENT_UNLOCK_AUDIT_LOG",
                    _value(
                        unlock,
                        "audit_log",
                        "~/.local/state/severino-vault-mcp/audit.log",
                    ),
                ),
            ),
        )
