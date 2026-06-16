-- Schema for NBA player statistics table
-- This table stores player game stats for the NBA

CREATE TABLE IF NOT EXISTS nba_player_stats (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(100) NOT NULL,
    season INTEGER NOT NULL,
    season_type VARCHAR(50),
    game_date VARCHAR(20),
    matchup VARCHAR(100),
    player_id VARCHAR(100),
    player_name VARCHAR(200),
    team VARCHAR(200),
    team_abbreviation VARCHAR(10),
    points FLOAT,
    rebounds FLOAT,
    assists FLOAT,
    minutes FLOAT,
    fg_pct FLOAT,
    fg3_pct FLOAT,
    ft_pct FLOAT,
    steals FLOAT,
    blocks FLOAT,
    turnovers FLOAT,
    fouls FLOAT,
    plus_minus FLOAT,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    timestamp BIGINT,
    UNIQUE(game_id, player_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_nba_player_stats_game ON nba_player_stats(game_id);
CREATE INDEX IF NOT EXISTS idx_nba_player_stats_player ON nba_player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_nba_player_stats_date ON nba_player_stats(game_date);
CREATE INDEX IF NOT EXISTS idx_nba_player_stats_season ON nba_player_stats(season);
CREATE INDEX IF NOT EXISTS idx_nba_player_stats_team ON nba_player_stats(team_abbreviation);
CREATE INDEX IF NOT EXISTS idx_nba_player_stats_player_season ON nba_player_stats(player_id, season);

-- Comments for documentation
COMMENT ON TABLE nba_player_stats IS 'NBA player statistics from game logs';
COMMENT ON COLUMN nba_player_stats.game_id IS 'NBA game ID (format: 002YYMMMM)';
COMMENT ON COLUMN nba_player_stats.season IS 'Season year (e.g., 2024 for 2024-25 season)';
COMMENT ON COLUMN nba_player_stats.season_type IS 'Season type (Regular Season, Playoffs)';
COMMENT ON COLUMN nba_player_stats.matchup IS 'Matchup string (e.g., LAL vs. BOS)';
COMMENT ON COLUMN nba_player_stats.player_id IS 'NBA player ID';
COMMENT ON COLUMN nba_player_stats.player_name IS 'Full player name';
COMMENT ON COLUMN nba_player_stats.team_abbreviation IS 'Team abbreviation (e.g., LAL, BOS)';
COMMENT ON COLUMN nba_player_stats.fetched_at IS 'Timestamp when the record was inserted';
