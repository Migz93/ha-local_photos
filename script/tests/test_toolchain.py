"""Tests for script/setup/toolchain, which installs the tools mise.toml pins."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

import pytest

SCRIPT_DIR = Path(__file__).parents[1]


@pytest.mark.unit
def test_own_machine_without_mise_falls_back_to_path(tmp_path: Path) -> None:
    """Outside an environment the project owns, a missing mise is reported, not installed."""
    repo = tmp_path / "repository"
    (repo / "script" / "setup").mkdir(parents=True)
    (repo / "script" / ".lib").mkdir()
    shutil.copy(SCRIPT_DIR / "setup" / "toolchain", repo / "script" / "setup" / "toolchain")
    for library in ("output.sh", "download.sh"):
        shutil.copy(SCRIPT_DIR / ".lib" / library, repo / "script" / ".lib" / library)
    (repo / "mise.toml").write_text('min_version = "2026.10.22"\n', encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key not in {"REMOTE_CONTAINERS", "CODESPACES"}}
    commands = tmp_path / "commands"
    commands.mkdir()
    for name in ("bash", "dirname", "mkdir", "cat", "rm", "rmdir", "python3"):
        command = shutil.which(name)
        assert command is not None
        (commands / name).symlink_to(command)
    env.update({"HOME": str(tmp_path), "PATH": str(commands), "MISE_DATA_DIR": str(tmp_path / "mise")})
    env.pop("CLAUDE_CODE_REMOTE", None)

    result = subprocess.run(
        ["bash", "script/setup/toolchain"], cwd=repo, capture_output=True, text=True, env=env, check=False
    )

    assert result.returncode == 0, result.stderr
    assert "mise not found" in result.stdout + result.stderr
    assert not (tmp_path / ".local" / "bin" / "mise").exists()


@pytest.mark.unit
def test_renovate_preview_only_enables_the_isolated_repository(tmp_path: Path) -> None:
    """Local previews preserve package exclusions and never change the real opt-in file."""
    repo, binaries = tmp_path / "repo", tmp_path / "bin"
    (repo / ".github").mkdir(parents=True)
    binaries.mkdir()
    config = {"enabled": False, "packageRules": [{"matchManagers": ["npm"], "enabled": False}]}
    (repo / ".github/renovate.json").write_text(json.dumps(config), encoding="utf-8")
    for args in (
        ["init", "--quiet"],
        ["add", "."],
        [
            "-c",
            "user.name=Preview",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "test: config",
        ],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)
    stub = binaries / "renovate"
    stub.write_text("#!/bin/sh\ncat .github/renovate.json\n", encoding="utf-8")
    stub.chmod(0o755)
    task = tomllib.loads((SCRIPT_DIR.parent / "mise.toml").read_text(encoding="utf-8"))["tasks"]["renovate-dry-run"][
        "run"
    ]
    env = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "RENOVATE_GITHUB_COM_TOKEN": "unused-preview-test-token",
    }
    result = subprocess.run(["bash", "-c", task], cwd=repo, capture_output=True, text=True, env=env, check=False)
    assert result.returncode == 0, result.stderr
    preview = json.loads(result.stdout)
    assert preview["enabled"] is True
    assert preview["packageRules"] == config["packageRules"]
    assert json.loads((repo / ".github/renovate.json").read_text(encoding="utf-8")) == config
