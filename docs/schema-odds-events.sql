-- Schema for sports betting odds events table
-- This table stores odds data from The-Odds-API for all sports leagues

-- Drop existing table if exists (commented out for safety)
-- DROP TABLE IF EXISTS odds_events;

CREATE TABLE IF NOT EXISTS odds_events (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(100) NOT NULL,
    sport_key VARCHAR(50) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    commence_time TIMESTAMP WITH TIME ZONE,
    home_team VARCHAR(200),
    away_team VARCHAR(200),
    market VARCHAR(50) NOT NULL,
    outcome_name VARCHAR(200) NOT NULL,
    outcome_price DECIMAL(10, 4),
    outcome_point DECIMAL(10, 4),
    bookmaker VARCHAR(200) NOT NULL,
    last_update TIMESTAMP WITH TIME ZONE,
    timestamp BIGINT,
    poll_date VARCHAR(20),
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(sport_key, event_id, market, outcome_name, bookmaker)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_odds_events_sport ON odds_events(sport_key);
CREATE INDEX IF NOT EXISTS idx_odds_events_event ON odds_events(event_id);
CREATE INDEX IF NOT EXISTS idx_odds_events_commence ON odds_events(commence_time);
CREATE INDEX IF NOT EXISTS idx_odds_events_bookmaker ON odds_events(bookmaker);
CREATE INDEX IF NOT EXISTS idx_odds_events_fetched ON odds_events(fetched_at DESC);

-- Composite index for common join queries
CREATE INDEX IF NOT EXISTS idx_odds_events_sport_event ON odds_events(sport_key, event_id);

-- Index for time-range queries
CREATE INDEX IF NOT EXISTS idx_odds_events_time_range ON odds_events(commence_time, fetched_at);

-- Comments for documentation
COMMENT ON TABLE odds_events IS 'Sports betting odds events from The-Odds-API';
COMMENT ON COLUMN odds_events.game_id IS 'Unique game identifier';
COMMENT ON COLUMN odds_events.sport_key IS 'Sport key (e.g., basketball_nba, americanfootball_nfl)';
COMMENT ON COLUMN odds_events.event_id IS 'Event/sportradar ID from The-Odds-API';
COMMENT ON COLUMN odds_events.commence_time IS 'Scheduled start time of the event';
COMMENT ON COLUMN odds_events.market IS 'Market type (e.g., h2h, spreads, totals)';
COMMENT ON COLUMN odds_events.outcome_name IS 'Outcome description (e.g., Team Name, Over, Under)';
COMMENT ON COLUMN odds_events.outcome_price IS 'American odds value';
COMMENT ON COLUMN odds_events.outcome_point IS 'Point spread/total for spreads and totals markets';
COMMENT ON COLUMN odds_events.bookmaker IS 'Bookmaker name (e.g., DraftKings, FanDuel)';
COMMENT ON COLUMN odds_events.last_update IS 'When the odds were last updated by the bookmaker';
COMMENT ON COLUMN odds_events.poll_date IS 'Date when the poll was executed (YYYY-MM-DD)';
COMMENT ON COLUMN odds_events.fetched_at IS 'Timestamp when the record was inserted';
