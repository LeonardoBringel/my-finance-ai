"""Static checks on repository files (FND-18)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_does_not_declare_alembic():
    content = (ROOT / "pyproject.toml").read_text().lower()

    assert "alembic" not in content


def test_lockfile_does_not_contain_alembic():
    content = (ROOT / "uv.lock").read_text().lower()

    assert "alembic" not in content


def test_repo_has_no_migration_files():
    assert not (ROOT / "alembic.ini").exists()
    assert not (ROOT / "alembic").exists()
