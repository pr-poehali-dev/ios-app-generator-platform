CREATE TABLE IF NOT EXISTS t_p49276342_ios_app_generator_pl.runners (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL DEFAULT '',
    key_hash CHAR(64) NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_runners_key_hash ON t_p49276342_ios_app_generator_pl.runners (key_hash);

CREATE TABLE IF NOT EXISTS t_p49276342_ios_app_generator_pl.runner_jobs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    runner_id INTEGER NULL,
    repo VARCHAR(200) NOT NULL,
    branch VARCHAR(200) NOT NULL DEFAULT '',
    commit_sha CHAR(40) NOT NULL,
    install_cmd VARCHAR(50) NOT NULL,
    build_cmd VARCHAR(50) NOT NULL,
    node_major INTEGER NOT NULL DEFAULT 20,
    output_dir VARCHAR(100) NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    phase VARCHAR(20) NOT NULL DEFAULT '',
    exit_install INTEGER NULL,
    exit_build INTEGER NULL,
    output_files INTEGER NULL,
    output_bytes BIGINT NULL,
    log TEXT NOT NULL DEFAULT '',
    error VARCHAR(500) NOT NULL DEFAULT '',
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_runner_jobs_project ON t_p49276342_ios_app_generator_pl.runner_jobs (project_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_runner_jobs_status ON t_p49276342_ios_app_generator_pl.runner_jobs (status, id);