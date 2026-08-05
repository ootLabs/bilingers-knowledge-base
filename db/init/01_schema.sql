-- Runs once, on the first start of an empty postgres volume.
-- Keep this file as the minimal bootstrap only; real schema changes belong in
-- migrations once the backend gets a migration tool.

CREATE TABLE IF NOT EXISTS health_probe (
    id          SMALLINT PRIMARY KEY DEFAULT 1,
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT health_probe_single_row CHECK (id = 1)
);

INSERT INTO health_probe (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
