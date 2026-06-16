"""Data schema package for sportsquant.

Re-exports all public symbols from sub-modules for convenient access:

- stat_mapping: Cross-site stat key bidirectional mappings
- player_mapping: Fuzzy player name matching with rapidfuzz
- db: Cross-reference SQLite database
- sportsbooks_schema: Player-prop column definitions
- sportsbooks_io: Player-prop CSV read/write helpers
"""

# stat_mapping: canonical stat keys and site mapping functions
from sportsquant.data.schemas.stat_mapping import (
    CANONICAL_KEYS,
    PRIZEPICKS_KEYS,
    FANDUEL_KEYS,
    UNDERDOG_KEYS,
    DRAFTKINGS_KEYS,
    SITES,
    SITE_KEY_MAPPINGS,
    SITE_REVERSE_MAPPINGS,
    to_canonical,
    from_canonical,
    get_all_site_keys,
    is_canonical,
    get_canonical_stats,
)

# player_mapping: fuzzy player name matching
from sportsquant.data.schemas.player_mapping import (
    NICKNAME_TO_CANONICAL,
    MatchResult,
    normalize_for_matching,
    find_player,
    build_player_index,
    find_player_indexed,
    add_nickname_mapping,
    suggest_similar_names,
)

# db: cross-reference database
from sportsquant.data.schemas.db import (
    CrossReferenceDB,
    DB_PATH,
    get_db,
    close_db,
)

# sportsbooks_schema: player-prop column definitions
from sportsquant.data.schemas.sportsbooks_schema import (
    PLAYER_PROP_COLUMNS,
    PLAYER_PROP_REQUIRED_COLUMNS,
)

# sportsbooks_io: player-prop CSV I/O
from sportsquant.data.schemas.sportsbooks_io import (
    read_player_props_csv,
    write_player_props_csv,
)

__all__ = [
    # stat_mapping
    "CANONICAL_KEYS",
    "PRIZEPICKS_KEYS",
    "FANDUEL_KEYS",
    "UNDERDOG_KEYS",
    "DRAFTKINGS_KEYS",
    "SITES",
    "SITE_KEY_MAPPINGS",
    "SITE_REVERSE_MAPPINGS",
    "to_canonical",
    "from_canonical",
    "get_all_site_keys",
    "is_canonical",
    "get_canonical_stats",
    # player_mapping
    "NICKNAME_TO_CANONICAL",
    "MatchResult",
    "normalize_for_matching",
    "find_player",
    "build_player_index",
    "find_player_indexed",
    "add_nickname_mapping",
    "suggest_similar_names",
    # db
    "CrossReferenceDB",
    "DB_PATH",
    "get_db",
    "close_db",
    # sportsbooks_schema
    "PLAYER_PROP_COLUMNS",
    "PLAYER_PROP_REQUIRED_COLUMNS",
    # sportsbooks_io
    "read_player_props_csv",
    "write_player_props_csv",
]
