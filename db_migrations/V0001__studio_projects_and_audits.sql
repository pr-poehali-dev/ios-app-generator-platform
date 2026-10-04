CREATE TABLE IF NOT EXISTS t_p49276342_ios_app_generator_pl.projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    template VARCHAR(50) NOT NULL DEFAULT 'empty',
    source_type VARCHAR(20) NOT NULL DEFAULT 'new',
    repo_url TEXT NOT NULL DEFAULT '',
    stack VARCHAR(200) NOT NULL DEFAULT '',
    install_cmd VARCHAR(300) NOT NULL DEFAULT '',
    dev_cmd VARCHAR(300) NOT NULL DEFAULT '',
    build_cmd VARCHAR(300) NOT NULL DEFAULT '',
    output_dir VARCHAR(200) NOT NULL DEFAULT '',
    node_version VARCHAR(50) NOT NULL DEFAULT '',
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS t_p49276342_ios_app_generator_pl.project_audits (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    filename VARCHAR(300) NOT NULL DEFAULT '',
    archive_size BIGINT NOT NULL DEFAULT 0,
    report JSONB NOT NULL DEFAULT '{}'::jsonb,
    tree JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_audits_project ON t_p49276342_ios_app_generator_pl.project_audits (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON t_p49276342_ios_app_generator_pl.projects (updated_at DESC);