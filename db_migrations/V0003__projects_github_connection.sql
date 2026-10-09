ALTER TABLE t_p49276342_ios_app_generator_pl.projects ADD COLUMN IF NOT EXISTS gh_repo VARCHAR(200) NOT NULL DEFAULT '';
ALTER TABLE t_p49276342_ios_app_generator_pl.projects ADD COLUMN IF NOT EXISTS gh_branch VARCHAR(200) NOT NULL DEFAULT '';
ALTER TABLE t_p49276342_ios_app_generator_pl.projects ADD COLUMN IF NOT EXISTS gh_token_enc TEXT NOT NULL DEFAULT '';