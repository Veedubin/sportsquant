-- Ignite 3.x Cache Persistence Tables
-- These tables mirror Ignite cache data for durability

-- NBA Players persistence table
CREATE TABLE IF NOT EXISTS nba_players_persistence (
    cache_key VARCHAR(255) PRIMARY KEY,
    cache_value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version INTEGER DEFAULT 1
);

-- NBA Games persistence table
CREATE TABLE IF NOT EXISTS nba_games_persistence (
    cache_key VARCHAR(255) PRIMARY KEY,
    cache_value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version INTEGER DEFAULT 1
);

-- NBA Schedule persistence table
CREATE TABLE IF NOT EXISTS nba_schedule_persistence (
    cache_key VARCHAR(255) PRIMARY KEY,
    cache_value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version INTEGER DEFAULT 1
);

-- NBA Player Stats persistence table
CREATE TABLE IF NOT EXISTS nba_player_stats_persistence (
    cache_key VARCHAR(255) PRIMARY KEY,
    cache_value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version INTEGER DEFAULT 1
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_nba_players_cache_key ON nba_players_persistence(cache_key);
CREATE INDEX IF NOT EXISTS idx_nba_games_cache_key ON nba_games_persistence(cache_key);
CREATE INDEX IF NOT EXISTS idx_nba_schedule_cache_key ON nba_schedule_persistence(cache_key);
CREATE INDEX IF NOT EXISTS idx_nba_stats_cache_key ON nba_player_stats_persistence(cache_key);

-- Optional: Add updated_at index for finding stale entries
CREATE INDEX IF NOT EXISTS idx_nba_players_updated_at ON nba_players_persistence(updated_at);
CREATE INDEX IF NOT EXISTS idx_nba_games_updated_at ON nba_games_persistence(updated_at);
