REDDIT_POSTS_FOR_DIGEST = 20
REDDIT_COMMENTS_PER_POST_FOR_DIGEST = 5
REDDIT_POST_BODY_TRUNCATION = 200
REDDIT_COMMENT_BODY_TRUNCATION = 150
HN_POSTS_FOR_DIGEST = 15
HN_COMMENTS_PER_POST_FOR_DIGEST = 3
HN_COMMENT_BODY_TRUNCATION = 150

NEWS_ARTICLES_FOR_DIGEST = 15
NEWS_ARTICLE_DESCRIPTION_TRUNCATION = 200

DIGEST_FRESHNESS_TTL = 60 * 60  # 1 hour — how often to regenerate
DIGEST_DATA_TTL = 60 * 60 * 24  # 24 hours — max age before digest is discarded
DIGEST_LOCK_TTL = 60 * 5  # 5 minutes — prevent concurrent generation
DIGEST_REFRESH_INTERVAL = 10  # seconds — HTMX polling interval

PEER_SYNC_LOCK_TTL = 60 * 5  # 5 minutes
PEER_TARGET_COUNT = 6  # ask LLM for this many

SENTIMENT_MAX_POSTS = 20
SENTIMENT_MIN_POSTS = 5
SENTIMENT_REDDIT_COMMENTS_PER_POST = 20
SENTIMENT_HN_COMMENTS_PER_POST = 10
SENTIMENT_FRESHNESS_TTL = 43200  # 12 hours
SENTIMENT_DATA_TTL = 86400  # 24 hours
SENTIMENT_LOCK_TTL = 300  # 5 minutes

FINANCE_DATA_TTL = (
    60 * 60 * 24 * 30
)  # 30 days — eviction fallback only, fingerprint drives invalidation
FINANCE_LOCK_TTL = 300  # 5 minutes

RISK_FRESHNESS_TTL = 60 * 60 * 24 * 14  # 2 weeks
RISK_DATA_TTL = 60 * 60 * 24 * 60  # 2 months
RISK_LOCK_TTL = 300  # 5 minutes

VALUATION_FRESHNESS_TTL = (
    60 * 60 * 24 * 7
)  # 1 week — minimum time between regenerations
VALUATION_DATA_TTL = 60 * 60 * 24 * 90  # 3 months — eviction fallback
VALUATION_LOCK_TTL = 300  # 5 minutes

PRODUCT_FRESHNESS_TTL = 60 * 60 * 24 * 7  # 1 week
PRODUCT_DATA_TTL = 60 * 60 * 24 * 30  # 1 month
PRODUCT_LOCK_TTL = 300  # 5 minutes

PEOPLE_FRESHNESS_TTL = 60 * 60 * 24 * 7  # 1 week
PEOPLE_DATA_TTL = 60 * 60 * 24 * 60  # 2 months
PEOPLE_LOCK_TTL = 300  # 5 minutes

OVERALL_ASSESSMENT_DATA_TTL = (
    60 * 60 * 24 * 30
)  # 30 days — eviction fallback, fingerprint drives invalidation
OVERALL_ASSESSMENT_LOCK_TTL = 300  # 5 minutes

REVISION_LOCK_TTL = 60  # 1 minute — revisions are fast (MINI model, no tools)

OUTLOOK_FRESHNESS_TTL = 60 * 60  # 1 hour
OUTLOOK_DATA_TTL = 60 * 60 * 2  # 2 hours
OUTLOOK_LOCK_TTL = 60 * 3  # 3 minutes

DESCRIPTION_FRESHNESS_DAYS = 90  # 3 months — how often to regenerate
DESCRIPTION_LOCK_TTL = 300  # 5 minutes

MAX_AGENT_TURNS = 25


# ── Cache keys ──────────────────────────────────────────────────────

CACHE_KEY_PREFIX = "ts"


def cache_key(*parts: str | int) -> str:
    return f"{CACHE_KEY_PREFIX}:" + ":".join(str(p) for p in parts)
