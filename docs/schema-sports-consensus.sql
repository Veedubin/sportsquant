-- Schema for sports betting consensus/steam moves
-- Tracks line movement and consensus data across bookmakers

CREATE TABLE IF NOT EXISTS sports_consensus (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL,
    sport_key VARCHAR(50) NOT NULL,
    commence_time TIMESTAMP WITH TIME ZONE,
    home_team VARCHAR(200),
    away_team VARCHAR(200),
    market VARCHAR(50) NOT NULL,
    outcome_name VARCHAR(200) NOT NULL,
    consensus_price DECIMAL(10, 4),
    consensus_point DECIMAL(10, 4),
    move_type VARCHAR(20),  -- steam_move, reverse_line_movement, steady
    move_percent FLOAT,
    sharp_percent FLOAT,
    ticket_count INTEGER,
    percent_bets FLOAT,
    money_percent FLOAT,
    bookmakers_count INTEGER,
    timestamp BIGINT,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(event_id, market, outcome_name)
);

CREATE INDEX IF NOT EXISTS idx_sports_consensus_event ON sports_consensus(event_id);
CREATE INDEX IF NOT EXISTS idx_sports_consensus_sport ON sports_consensus(sport_key);
CREATE INDEX IF NOT EXISTS idx_sports_consensus_move ON sports_consensus(move_type);
CREATE INDEX IF NOT EXISTS idx_sports_consensus_fetched ON sports_consensus(fetched_at DESC);

COMMENT ON TABLE sports_consensus IS 'Consensus and line movement data across bookmakers';
