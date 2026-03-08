from django.db import models
from pgvector.django import VectorField

from scraper.constants import (
    EMBEDDING_MAX_COMMENTS,
    HN_AUTHOR_MAX_LENGTH,
    HN_COMMENT_AUTHOR_MAX_LENGTH,
    HN_TITLE_MAX_LENGTH,
    HN_URL_MAX_LENGTH,
    IMPACT_DIRECTION_MAX_LENGTH,
    IMPACT_MAGNITUDE_MAX_LENGTH,
    LARGE_VALUE_DECIMAL_PLACES,
    LARGE_VALUE_MAX_DIGITS,
    NEWS_CATEGORY_MAX_LENGTH,
    NEWS_HEADLINE_MAX_LENGTH,
    NEWS_SOURCE_MAX_LENGTH,
    NEWS_URL_MAX_LENGTH,
    PERCENTAGE_DECIMAL_PLACES,
    PERCENTAGE_MAX_DIGITS,
    PRICE_DECIMAL_PLACES,
    PRICE_MAX_DIGITS,
    RATIO_DECIMAL_PLACES,
    RATIO_MAX_DIGITS,
    REDDIT_AUTHOR_MAX_LENGTH,
    REDDIT_COMMENT_AUTHOR_MAX_LENGTH,
    REDDIT_COMMENT_ID_MAX_LENGTH,
    REDDIT_ID_MAX_LENGTH,
    REDDIT_SUBREDDIT_MAX_LENGTH,
    REDDIT_TITLE_MAX_LENGTH,
    REDDIT_URL_MAX_LENGTH,
    VECTOR_EMBEDDING_DIMENSIONS,
    VOLUME_DECIMAL_PLACES,
    VOLUME_MAX_DIGITS,
)


class Asset(models.Model):
    class AssetClass(models.TextChoices):
        CRYPTO = "crypto", "Cryptocurrency"
        EQUITY = "equity", "Equity"
        COMMODITY = "commodity", "Commodity"
        CURRENCY = "currency", "Currency"

    name = models.CharField(max_length=100)
    ticker = models.CharField(max_length=20, unique=True)
    asset_class = models.CharField(max_length=10, choices=AssetClass.choices)
    website = models.URLField(max_length=200, blank=True)
    peers = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="peer_of"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["asset_class", "name"]

    def __str__(self):
        return f"{self.ticker} ({self.name})"


class PriceHistory(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="prices")
    open = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES
    )
    high = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES
    )
    low = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES
    )
    close = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES
    )
    volume = models.DecimalField(
        max_digits=VOLUME_MAX_DIGITS,
        decimal_places=VOLUME_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        unique_together = [("asset", "timestamp")]
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.asset.ticker} @ {self.timestamp}"


class Fundamental(models.Model):
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="fundamentals"
    )
    market_cap = models.DecimalField(
        max_digits=LARGE_VALUE_MAX_DIGITS,
        decimal_places=LARGE_VALUE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    pe_ratio = models.DecimalField(
        max_digits=RATIO_MAX_DIGITS,
        decimal_places=RATIO_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    eps = models.DecimalField(
        max_digits=RATIO_MAX_DIGITS,
        decimal_places=RATIO_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    dividend_yield = models.DecimalField(
        max_digits=PERCENTAGE_MAX_DIGITS,
        decimal_places=PERCENTAGE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    revenue = models.DecimalField(
        max_digits=LARGE_VALUE_MAX_DIGITS,
        decimal_places=LARGE_VALUE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    profit_margin = models.DecimalField(
        max_digits=PERCENTAGE_MAX_DIGITS,
        decimal_places=PERCENTAGE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    beta = models.DecimalField(
        max_digits=PERCENTAGE_MAX_DIGITS,
        decimal_places=PERCENTAGE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    debt_to_equity = models.DecimalField(
        max_digits=RATIO_MAX_DIGITS,
        decimal_places=RATIO_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    free_cash_flow = models.DecimalField(
        max_digits=LARGE_VALUE_MAX_DIGITS,
        decimal_places=LARGE_VALUE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    return_on_equity = models.DecimalField(
        max_digits=PERCENTAGE_MAX_DIGITS,
        decimal_places=PERCENTAGE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    price_to_book = models.DecimalField(
        max_digits=RATIO_MAX_DIGITS,
        decimal_places=RATIO_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    fifty_two_week_high = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    fifty_two_week_low = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"{self.asset.ticker} fundamentals @ {self.fetched_at}"


class News(models.Model):
    class Category(models.TextChoices):
        EARNINGS = "earnings", "Earnings"
        MACRO = "macro", "Macroeconomic"
        REGULATORY = "regulatory", "Regulatory"
        GEOPOLITICAL = "geopolitical", "Geopolitical"
        SECTOR = "sector", "Sector"
        COMPANY = "company", "Company"
        MARKET = "market", "Market"

    headline = models.CharField(max_length=NEWS_HEADLINE_MAX_LENGTH)
    summary = models.TextField(blank=True)
    source = models.CharField(max_length=NEWS_SOURCE_MAX_LENGTH, blank=True)
    url = models.URLField(
        max_length=NEWS_URL_MAX_LENGTH, unique=True, null=True, blank=True
    )
    category = models.CharField(
        max_length=NEWS_CATEGORY_MAX_LENGTH, choices=Category.choices, blank=True
    )
    published_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    assets = models.ManyToManyField(
        Asset, through="NewsAssetImpact", related_name="news"
    )

    class Meta:
        ordering = ["-published_at"]
        verbose_name_plural = "news"

    def __str__(self):
        return self.headline


class NewsAssetImpact(models.Model):
    class Direction(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEGATIVE = "negative", "Negative"
        STAGNANT = "stagnant", "Stagnant"

    class Magnitude(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="impacts")
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="news_impacts"
    )
    direction = models.CharField(
        max_length=IMPACT_DIRECTION_MAX_LENGTH, choices=Direction.choices
    )
    magnitude = models.CharField(
        max_length=IMPACT_MAGNITUDE_MAX_LENGTH,
        choices=Magnitude.choices,
        default=Magnitude.MEDIUM,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("news", "asset")]
        ordering = ["-news__published_at"]

    def __str__(self):
        return f"{self.asset.ticker}: {self.direction} ({self.magnitude})"


class RedditPost(models.Model):
    reddit_id = models.CharField(max_length=REDDIT_ID_MAX_LENGTH, unique=True)
    subreddit = models.CharField(max_length=REDDIT_SUBREDDIT_MAX_LENGTH)
    title = models.CharField(max_length=REDDIT_TITLE_MAX_LENGTH)
    body = models.TextField(blank=True)
    author = models.CharField(max_length=REDDIT_AUTHOR_MAX_LENGTH)
    score = models.IntegerField()
    upvote_ratio = models.FloatField()
    num_comments = models.IntegerField()
    url = models.URLField(max_length=REDDIT_URL_MAX_LENGTH)
    posted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    assets = models.ManyToManyField(Asset, blank=True, related_name="reddit_posts")
    embedding = VectorField(
        dimensions=VECTOR_EMBEDDING_DIMENSIONS, null=True, blank=True
    )

    class Meta:
        ordering = ["-posted_at"]

    def __str__(self):
        return f"r/{self.subreddit}: {self.title[:80]}"

    def get_embedding_text(self, comment_bodies: list[str] | None = None) -> str:
        """Build the text used for embedding generation.

        Args:
            comment_bodies: Pre-fetched comment bodies to avoid a DB query.
                If None, fetches top comments from the DB.
        """
        parts = [self.title]
        if self.body:
            parts.append(self.body)
        if comment_bodies is None:
            comment_bodies = list(
                self.comments.order_by("-score").values_list("body", flat=True)[
                    :EMBEDDING_MAX_COMMENTS
                ]
            )
        parts.extend(comment_bodies)
        return "\n".join(parts)


class RedditComment(models.Model):
    reddit_id = models.CharField(max_length=REDDIT_COMMENT_ID_MAX_LENGTH, unique=True)
    post = models.ForeignKey(
        RedditPost, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.CharField(max_length=REDDIT_COMMENT_AUTHOR_MAX_LENGTH)
    body = models.TextField()
    score = models.IntegerField()
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-score"]

    def __str__(self):
        return f"Comment by {self.author} (score: {self.score})"


class HNPost(models.Model):
    hn_id = models.IntegerField(unique=True)
    title = models.CharField(max_length=HN_TITLE_MAX_LENGTH)
    url = models.URLField(max_length=HN_URL_MAX_LENGTH, blank=True)
    author = models.CharField(max_length=HN_AUTHOR_MAX_LENGTH)
    score = models.IntegerField()
    num_comments = models.IntegerField()
    posted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    assets = models.ManyToManyField(Asset, blank=True, related_name="hn_posts")
    embedding = VectorField(
        dimensions=VECTOR_EMBEDDING_DIMENSIONS, null=True, blank=True
    )

    class Meta:
        ordering = ["-posted_at"]

    def __str__(self):
        return f"HN: {self.title[:80]}"

    def get_embedding_text(self, comment_bodies: list[str] | None = None) -> str:
        parts = [self.title]
        if comment_bodies is None:
            comment_bodies = list(
                self.comments.values_list("body", flat=True)[:EMBEDDING_MAX_COMMENTS]
            )
        parts.extend(comment_bodies)
        return "\n".join(parts)


class HNComment(models.Model):
    hn_id = models.IntegerField(unique=True)
    post = models.ForeignKey(HNPost, on_delete=models.CASCADE, related_name="comments")
    author = models.CharField(max_length=HN_COMMENT_AUTHOR_MAX_LENGTH)
    body = models.TextField()
    posted_at = models.DateTimeField()

    class Meta:
        ordering = ["-posted_at"]

    def __str__(self):
        return f"HN comment by {self.author} on {self.post.hn_id}"


class NewsArticle(models.Model):
    url = models.URLField(max_length=NEWS_URL_MAX_LENGTH, unique=True)
    title = models.CharField(max_length=NEWS_HEADLINE_MAX_LENGTH)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=NEWS_SOURCE_MAX_LENGTH, blank=True)
    thumbnail = models.URLField(max_length=NEWS_URL_MAX_LENGTH, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    assets = models.ManyToManyField(Asset, blank=True, related_name="news_articles")
    embedding = VectorField(
        dimensions=VECTOR_EMBEDDING_DIMENSIONS, null=True, blank=True
    )

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title[:80]

    def get_embedding_text(self) -> str:
        parts = [self.title]
        if self.description:
            parts.append(self.description)
        return "\n".join(parts)


class Analysis(models.Model):
    class Sentiment(models.TextChoices):
        BULLISH = "bullish", "Bullish"
        BEARISH = "bearish", "Bearish"
        NEUTRAL = "neutral", "Neutral"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="analyses")
    summary = models.TextField()
    sentiment = models.CharField(max_length=10, choices=Sentiment.choices)
    trend_prediction = models.TextField()
    sources_used = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.asset.ticker} analysis ({self.sentiment}) @ {self.created_at}"
