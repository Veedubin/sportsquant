-- Schema for NBA players roster table
-- This table stores player roster information for each season

CREATE TABLE IF NOT EXISTS nba_players (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(100) NOT NULL,
    player_name VARCHAR(200) NOT NULL,
    season VARCHAR(20) NOT NULL,
    team_id VARCHAR(50),
    team_abbreviation VARCHAR(10),
    first_season VARCHAR(10),
    last_season VARCHAR(10),
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(player_id, season)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_nba_players_player ON nba_players(player_id);
CREATE INDEX IF NOT EXISTS idx_nba_players_season ON nba_players(season);
CREATE INDEX IF NOT EXISTS idx_nba_players_team ON nba_players(team_id);
CREATE INDEX IF NOT EXISTS idx_nba_players_name ON nba_players(player_name);

-- Comments for documentation
COMMENT ON TABLE nba_players IS 'NBA player roster information by season';
COMMENT ON COLUMN nba_players.player_id IS 'NBA player ID (format varies by source)';
COMMENT ON COLUMN nba_players.player_name IS 'Full player name';
COMMENT ON COLUMN nba_players.season IS 'Season (e.g., 2022-23)';
COMMENT ON COLUMN nba_players.team_id IS 'NBA team ID';
COMMENT ON COLUMN nba_players.team_abbreviation IS 'Team abbreviation (e.g., LAL, BOS)';
COMMENT ON COLUMN nba_players.first_season IS 'First season player was in NBA';
COMMENT ON COLUMN nba_players.last_season IS 'Last season player was in NBA';
COMMENT ON COLUMN nba_players.fetched_at IS 'Timestamp when the record was inserted';
