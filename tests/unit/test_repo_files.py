"""Static checks on repository files (FND-18 to FND-23)."""

import json
import re
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


# --- deploy/db/create_role.sql (FND-19 to FND-23, static part only) ---

ROLE_SQL = ROOT / "deploy" / "db" / "create_role.sql"
GRANT_PATTERN = re.compile(
    r"\bGRANT\s+(?P<privileges>.+?)\s+ON\s+(?P<objects>.+?)"
    r"\s+TO\s+(?P<role>\w+)\s*;",
    re.IGNORECASE | re.DOTALL,
)
WRITE_PRIVILEGES = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
    "ALL",
)


def role_sql() -> str:
    """The script with `--` comments removed, so tests see only statements."""
    lines = ROLE_SQL.read_text().splitlines()
    return "\n".join(re.sub(r"--.*$", "", line) for line in lines)


def grants() -> list[re.Match]:
    return list(GRANT_PATTERN.finditer(role_sql()))


def test_role_script_exists():
    assert ROLE_SQL.is_file()


def test_role_script_takes_password_from_psql_variable():
    assert ":'ai_password'" in role_sql()


def test_role_script_has_no_literal_password():
    sql = role_sql()
    passwords = re.findall(r"\bPASSWORD\s+([^\s;]+)", sql, re.IGNORECASE)

    assert passwords
    assert set(passwords) == {":'ai_password'"}
    assert not re.search(r"\bPASSWORD\s+'", sql, re.IGNORECASE)


def test_role_script_has_no_write_grant():
    found = grants()

    assert found
    for grant in found:
        privileges = re.findall(r"\w+", grant["privileges"].upper())
        assert not set(privileges) & set(WRITE_PRIVILEGES), grant[0]


def test_role_script_grants_only_to_the_ai_role():
    for grant in grants():
        assert grant["role"] == "my_finance_ai", grant[0]


def test_role_script_select_grants_are_exactly_the_allowed_objects():
    selected = set()
    for grant in grants():
        match = re.fullmatch(
            r"SELECT\s*(?:\((?P<columns>[^)]*)\))?",
            grant["privileges"].strip(),
            re.IGNORECASE,
        )
        if match is None:
            continue
        columns = None
        if match["columns"]:
            columns = tuple(c.strip() for c in match["columns"].split(","))
        for table in grant["objects"].split(","):
            selected.add((table.strip(), columns))

    assert selected == {
        ("transactions", None),
        ("categories", None),
        ("alembic_version", None),
        ("users", ("id", "token_version")),
    }


def test_role_script_only_other_grant_is_schema_usage():
    others = [
        g
        for g in grants()
        if not g["privileges"].strip().upper().startswith("SELECT")
    ]

    assert [
        (o["privileges"].upper(), " ".join(o["objects"].lower().split()))
        for o in others
    ] == [("USAGE", "schema public")]


def test_role_script_sets_login_and_read_only_default():
    sql = role_sql()

    assert re.search(
        r"ALTER\s+ROLE\s+my_finance_ai\s+WITH\s+LOGIN\s+PASSWORD",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        r"ALTER\s+ROLE\s+my_finance_ai\s+SET\s+"
        r"default_transaction_read_only\s*=\s*on",
        sql,
        re.IGNORECASE,
    )


def test_role_script_quits_before_changes_when_password_is_missing():
    sql = role_sql()

    assert r"\if :{?ai_password}" in sql
    assert sql.index(r"\quit") < sql.index("CREATE ROLE")


def test_role_script_creates_role_only_when_missing():
    sql = role_sql()

    assert re.search(r"FROM\s+pg_roles", sql, re.IGNORECASE)
    assert r"\gset" in sql
    assert sql.index(r"\gset") < sql.index("CREATE ROLE")


def test_role_script_revokes_everything_before_granting():
    sql = role_sql()
    revoke_tables = re.search(
        r"REVOKE\s+ALL\s+ON\s+ALL\s+TABLES\s+IN\s+SCHEMA\s+public"
        r"\s+FROM\s+my_finance_ai\s*;",
        sql,
        re.IGNORECASE,
    )
    revoke_sequences = re.search(
        r"REVOKE\s+ALL\s+ON\s+ALL\s+SEQUENCES\s+IN\s+SCHEMA\s+public"
        r"\s+FROM\s+my_finance_ai\s*;",
        sql,
        re.IGNORECASE,
    )

    assert revoke_tables and revoke_sequences
    first_grant = grants()[0].start()
    assert revoke_tables.start() < first_grant
    assert revoke_sequences.start() < first_grant


# --- FND-24 Dockerfile ---

DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def dockerfile_lines() -> list[str]:
    """Instructions, with `\\` continuations joined and comments removed."""
    text = DOCKERFILE.read_text().replace("\\\n", " ")
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def dockerfile_cmd() -> list[str]:
    cmd = [line for line in dockerfile_lines() if line.startswith("CMD ")]
    assert len(cmd) == 1
    return json.loads(cmd[0].removeprefix("CMD "))


def test_dockerfile_uses_python_313_slim_base():
    assert dockerfile_lines()[0] == "FROM python:3.13-slim"


def test_dockerfile_installs_locked_runtime_dependencies_with_uv():
    installs = [line for line in dockerfile_lines() if "uv sync" in line]

    assert installs
    for line in installs:
        assert "--frozen" in line
        assert "--no-dev" in line
    assert any("uv sync --frozen --no-dev" in line for line in installs)


def test_dockerfile_pins_uv_image_to_0_13_0():
    uv_images = [
        line
        for line in dockerfile_lines()
        if line.startswith("COPY --from=") and "astral-sh/uv" in line
    ]

    assert len(uv_images) == 1
    assert "ghcr.io/astral-sh/uv:0.13.0 " in uv_images[0]


def test_dockerfile_cmd_runs_uvicorn_with_one_worker_on_port_8000():
    cmd = " ".join(dockerfile_cmd())

    assert "uvicorn" in cmd
    assert "my_finance_ai.main:create_app" in cmd
    assert "--factory" in cmd
    assert re.search(r"--workers\s+1\b", cmd) or "--workers=1" in cmd
    assert re.search(r"--port\s+8000\b", cmd) or "--port=8000" in cmd


def test_dockerfile_runs_as_non_root_user():
    users = [line for line in dockerfile_lines() if line.startswith("USER ")]

    assert users
    assert users[-1] not in {"USER root", "USER 0"}


def test_dockerfile_healthcheck_probes_health_without_curl():
    health = [
        line
        for line in dockerfile_lines()
        if line.startswith("HEALTHCHECK") or "/health" in line
    ]

    assert any("/health" in line for line in health)
    assert any("urllib.request" in line for line in health)
    assert not any("curl" in line for line in dockerfile_lines())


def test_dockerfile_does_not_install_build_toolchain():
    content = DOCKERFILE.read_text()

    assert "build-essential" not in content
    assert "libpq-dev" not in content


def test_dockerignore_keeps_secrets_and_host_venv_out_of_the_image():
    entries = DOCKERIGNORE.read_text().split()

    assert ".env" in entries
    assert ".venv" in entries
    assert ".git" in entries
