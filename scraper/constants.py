PRICE_MAX_DIGITS = 20
PRICE_DECIMAL_PLACES = 8

VOLUME_MAX_DIGITS = 20
VOLUME_DECIMAL_PLACES = 2

LARGE_VALUE_MAX_DIGITS = 24
LARGE_VALUE_DECIMAL_PLACES = 2

RATIO_MAX_DIGITS = 12
RATIO_DECIMAL_PLACES = 4

PERCENTAGE_MAX_DIGITS = 8
PERCENTAGE_DECIMAL_PLACES = 6

DEFAULT_PRICE_PERIOD = "1y"
DEFAULT_PRICE_INTERVAL = "1h"
DAILY_PRICE_PERIOD = "max"
DAILY_PRICE_INTERVAL = "1d"

# Minimum seconds between re-fetching data for the same asset
REQUEST_TIMEOUT_SECONDS = 10
SYNC_LOCK_TTL = 120  # seconds — prevents concurrent syncs for the same ticker

FUNDAMENTALS_STALENESS_SECONDS = 3600
HOURLY_PRICES_STALENESS_SECONDS = 3600
DAILY_PRICES_STALENESS_SECONDS = 86400

# News
NEWS_HEADLINE_MAX_LENGTH = 300
NEWS_SOURCE_MAX_LENGTH = 100
NEWS_URL_MAX_LENGTH = 500
NEWS_CATEGORY_MAX_LENGTH = 20
IMPACT_DIRECTION_MAX_LENGTH = 10
IMPACT_MAGNITUDE_MAX_LENGTH = 10

# Reddit
REDDIT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
REDDIT_DEFAULT_LIMIT = 100
REDDIT_DEFAULT_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "stockmarket",
    "options",
    "pennystocks",
    "ValueInvesting",
    "dividends",
    "SecurityAnalysis",
    "Daytrading",
    "algotrading",
    "cryptocurrency",
    "bitcoin",
    "ethereum",
    "CryptoMarkets",
]
REDDIT_ID_MAX_LENGTH = 20
REDDIT_SUBREDDIT_MAX_LENGTH = 50
REDDIT_TITLE_MAX_LENGTH = 500
REDDIT_AUTHOR_MAX_LENGTH = 50
REDDIT_URL_MAX_LENGTH = 500
REDDIT_COMMENT_ID_MAX_LENGTH = 20
REDDIT_COMMENT_AUTHOR_MAX_LENGTH = 50
REDDIT_DEFAULT_COMMENT_LIMIT = 25

# Hacker News
HN_TOP_STORIES_LIMIT = 200
HN_MIN_SCORE = 10
HN_TITLE_MAX_LENGTH = 500
HN_URL_MAX_LENGTH = 500
HN_AUTHOR_MAX_LENGTH = 50
HN_COMMENT_AUTHOR_MAX_LENGTH = 50
HN_DEFAULT_COMMENT_LIMIT = 25
HN_STALENESS_SECONDS = 3600

# Asset keyword matching — words to ignore when building keyword map from asset names
ASSET_NAME_STOP_WORDS = frozenset({
    "inc", "corp", "corporation", "ltd", "limited", "co", "company",
    "group", "holdings", "plc", "sa", "ag", "nv", "se",
    "the", "and", "of", "usd", "etf", "fund", "trust", "class",
})
ASSET_KEYWORD_MIN_LENGTH = 3

# Brave News
BRAVE_NEWS_DEFAULT_QUERY = "stock market finance"
BRAVE_NEWS_DEFAULT_COUNT = 20
BRAVE_NEWS_DEFAULT_FRESHNESS = "pm"  # past month (max supported by Brave News API)
BRAVE_NEWS_TICKER_STALENESS_SECONDS = 3600  # 1 hour — per-asset news freshness on page visit

# Embeddings
VECTOR_EMBEDDING_DIMENSIONS = 2048
EMBEDDING_MAX_COMMENTS = 50
