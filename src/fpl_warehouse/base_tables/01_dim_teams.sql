CREATE TABLE IF NOT EXISTS dim_teams (
    team_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fpl_id          INTEGER,
    fpl_name        TEXT,
    understat_name  TEXT,
    short_name      TEXT,
    UNIQUE(fpl_name)
);
