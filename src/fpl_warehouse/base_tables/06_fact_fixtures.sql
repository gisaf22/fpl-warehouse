CREATE TABLE IF NOT EXISTS fact_fixtures (
    fixture_id      INTEGER PRIMARY KEY,
    event           INTEGER,
    home_team_id    INTEGER,
    away_team_id    INTEGER,
    home_score      INTEGER,
    away_score      INTEGER,
    kickoff_time    TEXT,
    finished        INTEGER,
    home_difficulty INTEGER,
    away_difficulty INTEGER,
    UNIQUE(fixture_id)
);
