-- Civil Agent wood framing sizer schema additions.
-- This migration is written as plain PostgreSQL because the repository does
-- not currently include an ORM or migration runner.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sizer_project_status') THEN
    CREATE TYPE sizer_project_status AS ENUM ('in_progress', 'complete', 'needs_review');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sizer_layout') THEN
    CREATE TYPE sizer_layout AS ENUM ('A', 'B');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS sizer_projects (
  id uuid PRIMARY KEY,
  user_id uuid NULL,
  project_name text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  status sizer_project_status NOT NULL DEFAULT 'in_progress',
  selected_layout sizer_layout NULL,
  input_params jsonb NOT NULL,
  layout_a_result jsonb NULL,
  layout_b_result jsonb NULL,
  comparison_result jsonb NULL
);

CREATE INDEX IF NOT EXISTS idx_sizer_projects_user_id ON sizer_projects (user_id);
CREATE INDEX IF NOT EXISTS idx_sizer_projects_status ON sizer_projects (status);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'users'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'fk_sizer_projects_user_id'
  ) THEN
    ALTER TABLE sizer_projects
      ADD CONSTRAINT fk_sizer_projects_user_id
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'projects'
  ) THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'project_type'
    ) THEN
      ALTER TABLE projects
        ADD COLUMN project_type text NOT NULL DEFAULT 'building_graph';
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'sizer_project_id'
    ) THEN
      ALTER TABLE projects
        ADD COLUMN sizer_project_id uuid NULL;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.table_constraints
      WHERE constraint_name = 'fk_projects_sizer_project_id'
    ) THEN
      ALTER TABLE projects
        ADD CONSTRAINT fk_projects_sizer_project_id
        FOREIGN KEY (sizer_project_id) REFERENCES sizer_projects(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.table_constraints
      WHERE constraint_name = 'chk_projects_project_type'
    ) THEN
      ALTER TABLE projects
        ADD CONSTRAINT chk_projects_project_type
        CHECK (project_type IN ('building_graph', 'wood_framing_sizer'));
    END IF;
  END IF;
END $$;
