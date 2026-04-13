CREATE TABLE IF NOT EXISTS dim_gameweeks (
    gw_id           INTEGER PRIMARY KEY,
    deadline_time   TEXT,
    finished        INTEGER,
    is_current      INTEGER,
    is_next         INTEGER
);
