"""Configuration is injectable without changing process-global environment."""

from vault_engine.config import Config


def test_load_accepts_explicit_path_and_environment_mapping(tmp_path) -> None:
    vault_from_file = tmp_path / "file-vault"
    vault_from_env = tmp_path / "env-vault"
    config = tmp_path / "instance.toml"
    config.write_text(
        f'[vault]\npath = "{vault_from_file}"\nindexed_dirs = ["Docs"]\n'
        '[cache]\nseconds = 20\n',
        encoding="utf-8",
    )

    loaded = Config.load(
        config,
        env={
            "SVMC_VAULT_PATH": str(vault_from_env),
            "SVMC_CACHE_SECONDS": "7",
        },
    )

    assert loaded.vault_path == vault_from_env
    assert loaded.indexed_dirs == ("Docs",)
    assert loaded.cache_seconds == 7


def test_explicit_path_wins_over_env_config_path(tmp_path) -> None:
    chosen = tmp_path / "chosen.toml"
    ignored = tmp_path / "ignored.toml"
    chosen.write_text(f'[vault]\npath = "{tmp_path / "chosen"}"\n')
    ignored.write_text(f'[vault]\npath = "{tmp_path / "ignored"}"\n')

    loaded = Config.load(chosen, env={"SVMC_CONFIG": str(ignored)})

    assert loaded.vault_path == tmp_path / "chosen"
