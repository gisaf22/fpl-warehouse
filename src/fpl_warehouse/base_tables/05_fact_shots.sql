CREATE TABLE IF NOT EXISTS fact_shots (
    shot_id         INTEGER PRIMARY KEY,
    match_id        INTEGER,
    understat_player_id INTEGER,
    minute          INTEGER,
    result          TEXT,
    x               REAL,
    y               REAL,
    xg              REAL,
    situation       TEXT,
    shot_type       TEXT,
    player          TEXT,
    h_a             TEXT,
    player_assisted TEXT,
    last_action     TEXT,
    season          TEXT,
    UNIQUE(shot_id)
);
