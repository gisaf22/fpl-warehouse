CREATE TABLE IF NOT EXISTS dim_players (
    player_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    fpl_id          INTEGER,
    understat_id    INTEGER,
    web_name        TEXT,
    fpl_name        TEXT,
    understat_name  TEXT,
    -- team_id is the warehouse surrogate key (dim_teams.team_id autoincrement),
    -- NOT the FPL integer ID. Use dim_teams.fpl_id for the FPL team integer.
    team_id         INTEGER,
    element_type    INTEGER,
    confidence      INTEGER,
    chance_of_playing_next_round REAL,
    news            TEXT,
    news_updated    TEXT,
    UNIQUE(fpl_id)
);
