CREATE TABLE IF NOT EXISTS t_p49276342_ios_app_generator_pl.studio_login_attempts (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON t_p49276342_ios_app_generator_pl.studio_login_attempts (ip, created_at DESC);