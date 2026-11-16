-- Service connects as app_rw. Migrations run as migrator (owner of all tables).

CREATE TABLE admin_users (
  id          uuid        PRIMARY KEY,
  email       text        NOT NULL UNIQUE,
  role        text        NOT NULL CHECK (role IN ('support', 'admin', 'security_auditor')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  disabled_at timestamptz
);

CREATE TABLE accounts (
  id           uuid        PRIMARY KEY,
  name         text        NOT NULL,
  status       text        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
  suspended_at timestamptz,
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outbox (
  id         bigserial   PRIMARY KEY,
  topic      text        NOT NULL,
  payload    jsonb       NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE legal_holds (
  id          bigserial   PRIMARY KEY,
  scope       text        NOT NULL,   -- a table name, or 'all'
  reason      text        NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  released_at timestamptz
);

CREATE TABLE siem_export_seen (
  event_id uuid        PRIMARY KEY,
  seen_at  timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE ON SEQUENCES TO app_rw;
