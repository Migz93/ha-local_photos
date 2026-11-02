"""Tests for script/template-sync-guard, which keeps newer versions a template sync would lower."""

from pathlib import Path
import subprocess
import sys

import pytest

GUARD = Path(__file__).parents[1] / ".lib" / "version_guard.py"
RENOVATE_CONFIG = '{"enabledManagers":["mise","pip_requirements","custom.regex","github-actions","npm","devcontainer"],"customManagers":[{"customType":"regex","managerFilePatterns":["/(^|/)custom_components/[^/]+/manifest\\\\.json$/"],"matchStrings":["\\"(?<depName>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\\\\[[^\\\\]]*\\\\])?==(?<currentValue>[^\\"\\\\s;]+)\\""],"datasourceTemplate":"pypi"},{"customType":"regex","managerFilePatterns":["/(^|/)mise\\\\.toml$/","/(^|/)\\\\.devcontainer/devcontainer\\\\.json$/"],"matchStrings":["min_version = \\"(?<currentValue>[^\\"]+)\\"","\\"ghcr\\\\.io/devcontainers-extra/features/mise:\\\\d+(?:@sha256:[a-f0-9]+)?\\":\\\\s*\\\\{\\\\s*\\"version\\":\\\\s*\\"(?<currentValue>[^\\"]+)\\""],"depNameTemplate":"jdx/mise","datasourceTemplate":"github-releases","extractVersionTemplate":"^v(?<version>.+)$"},{"customType":"regex","managerFilePatterns":["/(^|/)\\\\.github/workflows/[^/]+\\\\.ya?ml$/"],"matchStrings":["# renovate: datasource=(?<datasource>\\\\S+) depName=(?<depName>\\\\S+)(?: extractVersion=(?<extractVersion>\\\\S+))?\\\\n\\\\s+version: \\"?(?<currentValue>[^\\"\\\\s]+)\\"?"]}],"mise":{"managerFilePatterns":["/(^|/)mise\\\\.devcontainer\\\\.toml$/","/(^|/)\\\\.config/mise/conf\\\\.d/[^/]+\\\\.toml$/"]}}'
SHA_OLD = "a" * 40
SHA_NEW = "b" * 40

BASE = {
    "mise.toml": 'min_version = "2026.10.22"\n\n[tools]\npython = "3.14.9"\nuv = "0.14.0"\n',
    "requirements_test.txt": "pytest-homeassistant-custom-component==0.13.380\n",
    "package.json": '{\n  "devDependencies": {\n    "prettier": "3.9.0",\n    "pyright": "1.1.408"\n  }\n}\n',
    ".devcontainer/devcontainer.json": (
        '{\n  "features": {\n    "ghcr.io/devcontainers-extra/features/mise:1": {\n'
        '      "version": "2026.10.22"\n    }\n  }\n}\n'
    ),
    ".github/workflows/lint.yml": (
        f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA_NEW} # v7.1.0\n"
        "      - uses: jdx/mise-action@" + SHA_NEW + " # v5.2.5\n        with:\n"
        "          # renovate: datasource=github-releases depName=jdx/mise\n"
        '          version: "2026.10.22"\n'
    ),
}

SYNCED = {
    "mise.toml": 'min_version = "2026.10.1"\n\n[tools]\npython = "3.14.9"\nuv = "0.13.7"\nfd = "10.5.0"\n',
    "requirements_test.txt": "pytest-homeassistant-custom-component==0.13.375\n",
    "package.json": '{\n  "devDependencies": {\n    "prettier": "3.8.2",\n    "pyright": "1.1.409"\n  }\n}\n',
    ".devcontainer/devcontainer.json": (
        '{\n  "features": {\n    "ghcr.io/devcontainers-extra/features/mise:1": {\n'
        '      "version": "2026.9.30"\n    }\n  }\n}\n'
    ),
    ".github/workflows/lint.yml": (
        f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA_OLD} # v7.0.1\n"
        "      - uses: jdx/mise-action@" + SHA_NEW + " # v5.2.5\n        with:\n"
        "          # renovate: datasource=github-releases depName=jdx/mise\n"
        '          version: "2026.10.1"\n'
    ),
}


def _write(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def synced(tmp_path: Path) -> Path:
    """A repository whose committed state is BASE and whose working tree holds the sync's SYNCED."""
    for command in (
        ["git", "init", "--quiet", "--initial-branch=main"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Guard Test"],
    ):
        subprocess.run(command, cwd=tmp_path, check=True)
    _write(tmp_path, {**BASE, ".github/renovate.json": RENOVATE_CONFIG})
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "test: base"], cwd=tmp_path, check=True
    )
    _write(tmp_path, SYNCED)
    return tmp_path


def _guard(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(GUARD), "HEAD", *args], cwd=root, capture_output=True, text=True, check=False
    )


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


@pytest.mark.unit
def test_restores_every_lowered_pin(synced: Path) -> None:
    """Each format gets back the repository's own, higher version; everything else stays as synced."""
    result = _guard(synced)

    assert result.returncode == 0, result.stderr
    mise = _read(synced, "mise.toml")
    assert 'min_version = "2026.10.22"' in mise
    assert 'uv = "0.14.0"' in mise
    assert 'fd = "10.5.0"' in mise
    assert "==0.13.380" in _read(synced, "requirements_test.txt")
    package = _read(synced, "package.json")
    assert '"prettier": "3.9.0"' in package
    assert '"pyright": "1.1.409"' in package
    assert '"version": "2026.10.22"' in _read(synced, ".devcontainer/devcontainer.json")
    workflow = _read(synced, ".github/workflows/lint.yml")
    assert f"actions/checkout@{SHA_NEW} # v7.1.0" in workflow
    assert 'version: "2026.10.22"' in workflow


@pytest.mark.unit
def test_reports_what_it_kept(synced: Path) -> None:
    """The Markdown report names every restored pin with both versions."""
    result = _guard(synced)

    assert "| `mise.toml` | `uv` | 0.13.7 | 0.14.0 |" in result.stdout
    assert "| `.github/workflows/lint.yml` | `actions/checkout` | v7.0.1 | v7.1.0 |" in result.stdout
    assert "pyright" not in result.stdout


@pytest.mark.unit
def test_check_mode_changes_nothing(synced: Path) -> None:
    """--check reports and fails without touching a file."""
    result = _guard(synced, "--check")

    assert result.returncode == 1
    assert "would keep" in result.stdout
    assert _read(synced, "mise.toml") == SYNCED["mise.toml"]


@pytest.mark.unit
def test_silent_when_nothing_is_lowered(synced: Path) -> None:
    """A sync that only raises versions passes without a report."""
    _write(synced, BASE)

    result = _guard(synced, "--check")

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.unit
def test_each_occurrence_is_compared_on_its_own(synced: Path) -> None:
    """Two jobs pinning one action at different versions keep their own; only the lowered one is restored."""
    base = f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA_OLD} # v6.0.0\n      - uses: actions/checkout@{SHA_NEW} # v7.1.0\n"
    lowered = f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA_OLD} # v6.0.0\n      - uses: actions/checkout@{SHA_OLD} # v7.0.1\n"
    _write(synced, {".github/workflows/two.yml": base})
    subprocess.run(["git", "add", "."], cwd=synced, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "test: two jobs"], cwd=synced, check=True
    )
    _write(synced, {**SYNCED, ".github/workflows/two.yml": lowered})

    _guard(synced)

    workflow = _read(synced, ".github/workflows/two.yml")
    assert f"actions/checkout@{SHA_OLD} # v6.0.0" in workflow
    assert f"actions/checkout@{SHA_NEW} # v7.1.0" in workflow


@pytest.mark.unit
def test_a_release_replaces_its_pre_release(synced: Path) -> None:
    """A beta pinned here is not kept over the stable release the template moves to."""
    _write(synced, {"requirements_test.txt": "pytest-homeassistant-custom-component==0.13.381b1\n"})
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--quiet", "-am", "test: beta"], cwd=synced, check=True
    )
    _write(synced, {**SYNCED, "requirements_test.txt": "pytest-homeassistant-custom-component==0.13.381\n"})

    _guard(synced)

    assert "==0.13.381\n" in _read(synced, "requirements_test.txt")


@pytest.mark.unit
def test_range_overrides_and_devcontainer_feature_tags(synced: Path) -> None:
    """Syncs preserve npm range prefixes and numeric container feature pins."""
    base = {
        "package.json": '{"overrides":{"katex":"^0.19.0","re2js":"~2.9.0"}}',
        ".devcontainer/devcontainer.json": '{"features":{"ghcr.io/devcontainers/features/node:3":{}}}',
    }
    _write(synced, base)
    subprocess.run(["git", "add", "."], cwd=synced, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "test: versions"], cwd=synced, check=True
    )
    _write(
        synced,
        {
            "package.json": '{"overrides":{"katex":"^0.18.2","re2js":"~2.8.7"}}',
            ".devcontainer/devcontainer.json": '{"features":{"ghcr.io/devcontainers/features/node:2":{}}}',
        },
    )
    result = _guard(synced)
    assert result.returncode == 0, result.stderr
    assert "^0.19.0" in _read(synced, "package.json")
    assert "~2.9.0" in _read(synced, "package.json")
    assert "node:3" in _read(synced, ".devcontainer/devcontainer.json")


@pytest.mark.unit
def test_new_named_step_does_not_hide_existing_action_downgrade(synced: Path) -> None:
    """A new checkout step is not paired with an existing step's version."""
    path = ".github/workflows/named.yml"
    before = f"jobs:\n  build:\n    steps:\n      - name: Existing checkout\n        uses: actions/checkout@{SHA_NEW} # v7.0.0\n"
    _write(synced, {path: before})
    subprocess.run(["git", "add", "."], cwd=synced, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "test: named step"], cwd=synced, check=True
    )
    after = f"jobs:\n  build:\n    steps:\n      - name: New checkout\n        uses: actions/checkout@{SHA_NEW} # v8.0.0\n      - name: Existing checkout\n        uses: actions/checkout@{SHA_OLD} # v6.0.0\n"
    _write(synced, {path: after})
    result = _guard(synced)
    assert result.returncode == 0, result.stderr
    assert f"actions/checkout@{SHA_NEW} # v7.0.0" in _read(synced, path)
    assert "# v8.0.0" in _read(synced, path)


@pytest.mark.unit
@pytest.mark.parametrize(("old", "new"), [("1.2.0-beta.2", "1.2.0-beta.1"), ("1.2.0-preview.2", "1.2.0-preview.1")])
def test_spelled_out_prereleases_keep_their_number(synced: Path, old: str, new: str) -> None:
    """Long prerelease names do not collapse to their one-letter prefixes."""
    path = "requirements_test.txt"
    _write(synced, {path: f"example=={old}\n"})
    subprocess.run(["git", "add", "."], cwd=synced, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "test: prerelease"], cwd=synced, check=True
    )
    _write(synced, {path: f"example=={new}\n"})
    assert _guard(synced).returncode == 0
    assert old in _read(synced, path)
