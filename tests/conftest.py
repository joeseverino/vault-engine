from collections.abc import Callable
from pathlib import Path

import pytest

from vault_engine.config import Config
from vault_engine.vault import VaultLoader


@pytest.fixture
def vault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """tmp_path as the vault root, selected through the environment."""
    monkeypatch.setenv("SVMC_VAULT_PATH", str(tmp_path))
    return tmp_path


@pytest.fixture
def vault_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., VaultLoader]:
    """Build a loader over tmp_path from a config file that indexes the given dirs."""

    def build(indexed_dirs: tuple[str, ...] = ("Notes",)) -> VaultLoader:
        for sub in indexed_dirs:
            (tmp_path / sub).mkdir(exist_ok=True)
        listed = ", ".join(f'"{sub}"' for sub in indexed_dirs)
        cfg = tmp_path / "config.toml"
        cfg.write_text(f'[vault]\npath = "{tmp_path}"\nindexed_dirs = [{listed}]\n')
        monkeypatch.setenv("SVMC_CONFIG", str(cfg))
        monkeypatch.delenv("SVMC_VAULT_PATH", raising=False)
        return VaultLoader(Config.from_env())

    return build
