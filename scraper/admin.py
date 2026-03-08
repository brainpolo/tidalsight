from django.contrib import admin

from scraper.models import Asset, Fundamental, HNComment, HNPost, News, NewsArticle, NewsAssetImpact, PriceHistory, RedditComment, RedditPost


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("ticker", "name", "asset_class", "is_active")
    list_filter = ("asset_class", "is_active")
    search_fields = ("ticker", "name")
    filter_horizontal = ("peers",)


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("asset", "close", "volume", "timestamp")
    list_filter = ("asset",)
    date_hierarchy = "timestamp"


@admin.register(Fundamental)
class FundamentalAdmin(admin.ModelAdmin):
    list_display = ("asset", "market_cap", "pe_ratio", "eps", "fetched_at")
    list_filter = ("asset",)


class NewsAssetImpactInline(admin.TabularInline):
    model = NewsAssetImpact
    extra = 1
    autocomplete_fields = ("asset",)


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ("headline", "category", "source", "published_at")
    list_filter = ("category", "source")
    search_fields = ("headline", "summary")
    date_hierarchy = "published_at"
    inlines = [NewsAssetImpactInline]


@admin.register(NewsAssetImpact)
class NewsAssetImpactAdmin(admin.ModelAdmin):
    list_display = ("news", "asset", "direction", "magnitude")
    list_filter = ("direction", "magnitude")
    autocomplete_fields = ("news", "asset")


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "published_at")
    list_filter = ("source",)
    search_fields = ("title", "description")
    date_hierarchy = "published_at"
    filter_horizontal = ("assets",)


class RedditCommentInline(admin.TabularInline):
    model = RedditComment
    extra = 0
    readonly_fields = ("reddit_id", "author", "body", "score", "created_at")


@admin.register(RedditPost)
class RedditPostAdmin(admin.ModelAdmin):
    list_display = ("subreddit", "title", "score", "num_comments", "posted_at")
    list_filter = ("subreddit",)
    search_fields = ("title", "body")
    date_hierarchy = "posted_at"
    filter_horizontal = ("assets",)
    inlines = [RedditCommentInline]


@admin.register(RedditComment)
class RedditCommentAdmin(admin.ModelAdmin):
    list_display = ("post", "author", "score", "created_at")
    list_filter = ("post__subreddit",)
    search_fields = ("body", "author")


class HNCommentInline(admin.TabularInline):
    model = HNComment
    extra = 0
    readonly_fields = ("hn_id", "author", "body", "posted_at")


@admin.register(HNPost)
class HNPostAdmin(admin.ModelAdmin):
    list_display = ("title", "score", "num_comments", "posted_at")
    search_fields = ("title",)
    date_hierarchy = "posted_at"
    filter_horizontal = ("assets",)
    inlines = [HNCommentInline]


@admin.register(HNComment)
class HNCommentAdmin(admin.ModelAdmin):
    list_display = ("post", "author", "posted_at")
    search_fields = ("body", "author")
