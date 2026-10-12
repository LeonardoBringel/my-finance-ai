-- Provisions the read-only database role used by my-finance-ai.
--
-- Run as a superuser, against the my-finance database. Safe to re-run: it
-- converges to the same privileges every time.
--
--   psql -v ON_ERROR_STOP=1 -v ai_password="$AI_DB_PASSWORD" \
--        -d <DB_NAME> -f deploy/db/create_role.sql

-- Step 1: refuse to run without the password variable, before any change.
\if :{?ai_password}
\else
  \echo 'Usage: psql -v ON_ERROR_STOP=1 -v ai_password="$AI_DB_PASSWORD" -d <DB_NAME> -f deploy/db/create_role.sql'
  \quit
\endif

-- Step 2: create the role only if missing (CREATE ROLE has no IF NOT EXISTS).
SELECT NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'my_finance_ai'
) AS role_missing \gset
\if :role_missing
  CREATE ROLE my_finance_ai LOGIN;
\endif

BEGIN;

-- Step 3: login, password and read-only default for every session.
ALTER ROLE my_finance_ai WITH LOGIN PASSWORD :'ai_password';
ALTER ROLE my_finance_ai SET default_transaction_read_only = on;

-- Step 4: converge. Drop any previous table or column grant first.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM my_finance_ai;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM my_finance_ai;

-- Step 5: the minimum the service needs.
GRANT USAGE ON SCHEMA public TO my_finance_ai;
GRANT SELECT ON transactions, categories, alembic_version TO my_finance_ai;
GRANT SELECT (id, token_version) ON users TO my_finance_ai;

COMMIT;
