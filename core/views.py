import json
from collections import defaultdict
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import TruncDate
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST

from analyst.app_behaviour import (
    DESCRIPTION_FRESHNESS_DAYS,
    DIGEST_REFRESH_INTERVAL,
    SENTIMENT_MIN_POSTS,
)
from analyst.managers.digest_manager import get_market_digest
from analyst.managers.external_risk_manager import (
    _cache_keys as external_risk_cache_keys,
)
from analyst.managers.financial_health_manager import (
    _cache_keys as financial_health_cache_keys,
)
from analyst.managers.financial_health_manager import (
    _source_fingerprint as financial_health_fingerprint,
)
from analyst.managers.leadership_manager import (
    _cache_keys as leadership_cache_keys,
)
from analyst.managers.leadership_manager import (
    _is_cache_valid as leadership_is_cache_valid,
)
from analyst.managers.leadership_manager import (
    _source_fingerprint as leadership_fingerprint,
)
from analyst.managers.overall_assessment_manager import (
    _cache_keys as overall_cache_keys,
)
from analyst.managers.overall_assessment_manager import (
    _is_cache_valid as overall_is_cache_valid,
)
from analyst.managers.overall_assessment_manager import (
    _source_fingerprint as overall_fingerprint,
)
from analyst.managers.overall_assessment_manager import compute_verdict
from analyst.managers.product_flywheel_manager import (
    _cache_keys as product_flywheel_cache_keys,
)
from analyst.managers.product_flywheel_manager import (
    _is_cache_valid as product_flywheel_is_cache_valid,
)
from analyst.managers.product_flywheel_manager import (
    _source_fingerprint as product_flywheel_fingerprint,
)
from analyst.managers.sentiment_manager import _cache_keys as sentiment_cache_keys
from analyst.managers.valuation_score_manager import (
    _cache_keys as valuation_cache_keys,
)
from analyst.managers.valuation_score_manager import (
    _is_cache_valid as valuation_is_cache_valid,
)
from analyst.managers.valuation_score_manager import (
    _source_fingerprint as valuation_fingerprint,
)
from analyst.tasks import (
    analyse_external_risk,
    analyse_financial_health,
    analyse_leadership,
    analyse_overall,
    analyse_product_flywheel,
    analyse_sentiment,
    analyse_valuation,
    discover_peers,
    generate_asset_description,
)
from core.app_behaviour import (
    ASSET_DETAIL_FAVICON_SIZE,
    ASSET_DETAIL_HN_POSTS,
    ASSET_DETAIL_NEWS_ARTICLES,
    ASSET_DETAIL_REDDIT_POSTS,
    DEFAULT_CHART_RANGE,
    HOME_COUNTS_CACHE_TTL,
    PEERS_CACHE_TTL,
    PRICES_CACHE_TTL,
    PRICES_PAGE_DAYS,
    REPORT_SECTION_POLL_INTERVAL_S,
    RSI_PERIOD,
    SEARCH_MAX_RESULTS,
    SEARCH_MIN_QUERY_LENGTH,
    SPARKLINE_DATA_POINTS,
    TRENDING_BANNER_COUNT,
    TRENDING_CACHE_TTL,
    TRENDING_PERIOD_H,
    TRENDING_REFRESH_INTERVAL,
    VIEW_COOLDOWN_H,
)
from core.forms import ProfileForm, SignInForm, SignUpForm, TidalPasswordChangeForm
from core.managers.fundamental_manager import build_fundamental_cards
from core.managers.user_manager import (
    create_user,
    sign_in_user,
    sign_out_user,
    update_profile,
)
from core.managers.valuation_manager import compute_valuations
from core.models import UserAsset
from core.sparkline import build_sparkline_svg
from core.utils import pct_change, total_post_count
from scraper.clients.yfinance_client import search_tickers
from scraper.managers.asset_manager import (
    get_or_create_asset,
    sync_all_prices,
    sync_fundamentals,
    sync_quick_prices,
)
from scraper.models import Asset, AssetView, PriceHistory
from scraper.tasks import backfill_full_prices, fetch_asset_news


async def _cached(key: str, compute, ttl: int = HOME_COUNTS_CACHE_TTL):
    value = await cache.aget(key)
    if value is None:
        value = await sync_to_async(compute)()
        await cache.aset(key, value, ttl)
    return value


async def home(request):
    return render(
        request,
        "core/home.html",
        {
            "asset_count": await _cached("home:asset_count", Asset.objects.count),
            "post_count": await _cached("home:post_count", total_post_count),
            "digest_refresh_interval": DIGEST_REFRESH_INTERVAL,
            "digest_date": timezone.now(),
        },
    )


@login_required
async def home_watchlist(request):
    """HTMX partial: watchlist widget for the homepage."""
    watched_asset_ids = [
        ua.asset_id
        async for ua in UserAsset.objects.filter(
            user=request.user, in_watchlist=True
        ).only("asset_id")
    ]
    watched = [
        a
        async for a in Asset.objects.filter(pk__in=watched_asset_ids, is_active=True)
        .annotate(
            latest_close=Subquery(
                PriceHistory.objects.filter(asset=OuterRef("pk"))
                .order_by("-timestamp")
                .values("close")[:1]
            ),
            prev_close=Subquery(
                PriceHistory.objects.filter(asset=OuterRef("pk"))
                .order_by("-timestamp")
                .values("close")[1:2]
            ),
        )
        .order_by("ticker")
    ]

    asset_ids = [a.id for a in watched]
    sparkline_map = defaultdict(list)

    if asset_ids:
        sparkline_qs = (
            PriceHistory.objects.filter(asset_id__in=asset_ids)
            .annotate(date=TruncDate("timestamp"))
            .order_by("asset_id", "-date", "-timestamp")
            .distinct("asset_id", "date")
            .values_list("asset_id", "close", "date")
        )
        async for asset_id, close, _date in sparkline_qs:
            if len(sparkline_map[asset_id]) < SPARKLINE_DATA_POINTS:
                sparkline_map[asset_id].append(float(close))

        for asset_id in sparkline_map:
            sparkline_map[asset_id].reverse()

    items = []
    for asset in watched:
        closes = sparkline_map.get(asset.id, [])
        change_pct = pct_change(asset.latest_close, asset.prev_close)
        items.append(
            {
                "asset": asset,
                "latest_close": asset.latest_close,
                "price_change_pct": round(change_pct, 2)
                if change_pct is not None
                else None,
                "sparkline_svg": build_sparkline_svg(closes),
            }
        )

    return render(request, "core/partials/home_watchlist.html", {"items": items})


async def strategy(request):
    return render(request, "core/strategy.html")


async def market_digest(request):
    digest = await sync_to_async(get_market_digest)()
    if digest and digest.get("generated_at"):
        digest["generated_at"] = datetime.fromisoformat(digest["generated_at"])
    return render(request, "core/partials/market_digest.html", {"digest": digest})


async def trending_banner(request):
    """HTMX partial: sticky top banner with most-viewed assets."""
    context = {
        "items": [],
        "trending_refresh_interval": TRENDING_REFRESH_INTERVAL,
    }

    cached = await cache.aget("trending_banner")
    if cached is not None:
        context["items"] = cached
        return render(request, "core/partials/trending_banner.html", context)

    trending_cutoff = timezone.now() - timedelta(hours=TRENDING_PERIOD_H)
    assets = [
        a
        async for a in Asset.objects.filter(is_active=True)
        .annotate(
            recent_views=Count(
                "asset_views",
                filter=Q(asset_views__viewed_at__gte=trending_cutoff),
            ),
            latest_close=Subquery(
                PriceHistory.objects.filter(asset=OuterRef("pk"))
                .order_by("-timestamp")
                .values("close")[:1]
            ),
            prev_close=Subquery(
                PriceHistory.objects.filter(asset=OuterRef("pk"))
                .order_by("-timestamp")
                .values("close")[1:2]
            ),
        )
        .filter(recent_views__gt=0)
        .order_by("-recent_views")[:TRENDING_BANNER_COUNT]
    ]

    asset_ids = [a.id for a in assets]
    sparkline_map = defaultdict(list)
    if asset_ids:
        sparkline_qs = (
            PriceHistory.objects.filter(asset_id__in=asset_ids)
            .annotate(date=TruncDate("timestamp"))
            .order_by("asset_id", "-date", "-timestamp")
            .distinct("asset_id", "date")
            .values_list("asset_id", "close", "date")
        )
        async for asset_id, close, _date in sparkline_qs:
            if len(sparkline_map[asset_id]) < SPARKLINE_DATA_POINTS:
                sparkline_map[asset_id].append(float(close))
        for asset_id in sparkline_map:
            sparkline_map[asset_id].reverse()

    items = []
    for asset in assets:
        closes = sparkline_map.get(asset.id, [])
        change_pct = pct_change(asset.latest_close, asset.prev_close)
        items.append(
            {
                "asset": asset,
                "latest_close": asset.latest_close,
                "price_change_pct": round(change_pct, 2)
                if change_pct is not None
                else None,
                "sparkline_svg": build_sparkline_svg(closes, width=48, height=16),
            }
        )

    if items:
        await cache.aset("trending_banner", items, TRENDING_CACHE_TTL)

    context["items"] = items
    return render(request, "core/partials/trending_banner.html", context)


async def asset_detail(request, ticker):
    """Renders the skeleton page with 1W chart data inlined for instant rendering."""
    ticker = ticker.upper()

    try:
        asset = await sync_to_async(get_or_create_asset)(ticker)
    except ValueError, ConnectionError:
        return render(
            request, "core/asset_unavailable.html", {"ticker": ticker}, status=503
        )

    # For new assets with no price data, fetch 1W quickly then backfill full history
    if not await asset.prices.aexists():
        await sync_to_async(sync_quick_prices)(asset, ticker)
        backfill_full_prices.delay(asset.id, ticker)

    # Track views (cooldown-based dedup via Redis)
    ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    user = request.user if request.user.is_authenticated else None

    if user:
        cooldown_key = f"view:{asset.pk}:u:{user.pk}"
    else:
        cooldown_key = f"view:{asset.pk}:{ip}:{hash(user_agent)}"

    if await cache.aadd(cooldown_key, True, VIEW_COOLDOWN_H * 3600):
        await AssetView.objects.acreate(
            asset=asset, user=user, ip_address=ip, user_agent=user_agent
        )
        await Asset.objects.filter(pk=asset.pk).aupdate(views=F("views") + 1)

    weekly_cutoff = timezone.now() - timedelta(hours=TRENDING_PERIOD_H)
    weekly_views = await asset.asset_views.filter(viewed_at__gte=weekly_cutoff).acount()
    all_time_views = await asset.asset_views.acount()

    is_watched = False
    price_target = None
    user_note = ""
    if request.user.is_authenticated:
        user_asset = await UserAsset.objects.filter(
            user=request.user, asset=asset
        ).afirst()
        if user_asset:
            is_watched = user_asset.in_watchlist
            user_note = user_asset.note
            if user_asset.price_target is not None:
                price_target = float(user_asset.price_target)

    # Inline 1W hourly data for instant chart render (no HTMX round-trip)
    hourly_cutoff = timezone.now() - timedelta(days=7)
    hourly_prices = [
        p
        async for p in asset.prices.filter(timestamp__gte=hourly_cutoff)
        .only("close", "timestamp")
        .order_by("timestamp")
    ]
    chart_data_json = json.dumps(
        [
            {"close": float(p.close), "ts": int(p.timestamp.timestamp() * 1000)}
            for p in hourly_prices
        ]
    )

    # Pull cached scores for report card (if available)
    sentiment_data_key, _, _ = sentiment_cache_keys(ticker)
    cached_sentiment = await cache.aget(sentiment_data_key)
    sentiment_score_5 = None
    sentiment_filled_dots = 0
    sentiment_brief = ""
    sentiment_label = ""
    sentiment_themes = []
    if cached_sentiment and "sentiment_score" in cached_sentiment:
        # Normalise -1..1 → 0..5
        sentiment_score_5 = round((cached_sentiment["sentiment_score"] + 1) * 2.5, 1)
        sentiment_filled_dots = int(round(sentiment_score_5))
        sentiment_brief = cached_sentiment.get("brief", "")
        sentiment_label = cached_sentiment.get("sentiment_label", "")
        sentiment_themes = cached_sentiment.get("key_themes", [])

    health_data_key, _, _ = financial_health_cache_keys(ticker)
    cached_health = await cache.aget(health_data_key)
    health_score_5 = None
    if cached_health and "score" in cached_health:
        health_score_5 = cached_health["score"]

    return render(
        request,
        "core/asset_detail.html",
        {
            "asset": asset,
            "is_watched": is_watched,
            "favicon_size": ASSET_DETAIL_FAVICON_SIZE,
            "default_chart_range": DEFAULT_CHART_RANGE,
            "rsi_period": RSI_PERIOD,
            "chart_data_json": chart_data_json,
            "weekly_views": weekly_views,
            "all_time_views": all_time_views,
            "price_target": price_target,
            "user_note": user_note,
            "sentiment_score_5": sentiment_score_5,
            "sentiment_filled_dots": sentiment_filled_dots,
            "sentiment_brief": sentiment_brief,
            "sentiment_label": sentiment_label,
            "sentiment_themes": sentiment_themes,
            "health_score_5": health_score_5,
            "report_section_poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
        },
    )


@login_required
@require_POST
async def toggle_watchlist(request, ticker):
    """HTMX partial: toggle asset in user's watchlist, return new star state."""
    ticker = ticker.upper()
    try:
        asset = await Asset.objects.aget(ticker=ticker)
    except Asset.DoesNotExist as err:
        raise Http404 from err

    user_asset, created = await UserAsset.objects.aget_or_create(
        user=request.user, asset=asset
    )
    if created:
        is_watched = True
    else:
        user_asset.in_watchlist = not user_asset.in_watchlist
        await user_asset.asave(update_fields=["in_watchlist"])
        is_watched = user_asset.in_watchlist

    return render(
        request,
        "core/partials/watchlist_star.html",
        {
            "asset": asset,
            "is_watched": is_watched,
        },
    )


@cache_page(PRICES_CACHE_TTL)
async def asset_header(request, ticker):
    """Partial: price, change, and valuations. Triggers price sync."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/asset_header.html", {})

    await sync_to_async(sync_all_prices)(ticker)

    last_two = [p async for p in asset.prices.all()[:2]]
    latest_price = last_two[0] if last_two else None
    previous_close = last_two[1] if len(last_two) > 1 else None
    if latest_price and previous_close:
        price_change = latest_price.close - previous_close.close
        price_change_pct = pct_change(latest_price.close, previous_close.close)
    else:
        price_change = None
        price_change_pct = None

    fundamental = await asset.fundamentals.afirst()
    valuations = await sync_to_async(compute_valuations)(
        asset, fundamental, latest_price
    )

    return render(
        request,
        "core/partials/asset_header.html",
        {
            "latest_price": latest_price,
            "price_change": price_change,
            "price_change_pct": price_change_pct,
            "valuations": valuations,
        },
    )


async def asset_fundamentals(request, ticker):
    """Partial: fundamentals grid + gauges. Triggers fundamentals sync."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/asset_fundamentals.html", {})

    await sync_to_async(sync_fundamentals)(ticker)

    fundamental = await asset.fundamentals.afirst()
    latest_price = await asset.prices.afirst()
    fundamental_cards = build_fundamental_cards(fundamental, latest_price)

    return render(
        request,
        "core/partials/asset_fundamentals.html",
        {
            "fundamental_cards": fundamental_cards,
        },
    )


async def asset_description(request, ticker):
    """Partial: brief company description. Triggers generation if empty."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/asset_description.html", {})

    if asset.description:
        # Silently refresh if older than 90 days
        if (
            not asset.description_updated_at
            or (timezone.now() - asset.description_updated_at).days > DESCRIPTION_FRESHNESS_DAYS
        ):
            generate_asset_description.delay(asset.id)
        return render(
            request,
            "core/partials/asset_description.html",
            {"description": asset.description},
        )

    # Kick off Celery task and tell HTMX to retry
    generate_asset_description.delay(asset.id)
    response = render(
        request,
        "core/partials/asset_description.html",
        {"loading": True, "ticker": ticker},
    )
    response["HX-Trigger-After-Settle"] = '{"retryDescription": true}'
    return response


async def asset_peers(request, ticker):
    """Partial: peer/competitor cards. Triggers peer discovery if needed."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/asset_peers.html", {})

    cache_key = f"asset_peers:{ticker}"
    cached = await cache.aget(cache_key)
    if cached is not None:
        return render(request, "core/partials/asset_peers.html", {"peers": cached})

    if not await asset.peers.aexists():
        # Kick off Celery task and tell HTMX to retry
        discover_peers.delay(asset.id)
        response = render(request, "core/partials/asset_peers.html", {"loading": True})
        response["HX-Trigger-After-Settle"] = '{"retryPeers": true}'
        return response

    peers = [
        p
        async for p in asset.peers.annotate(
            latest_close=Subquery(
                PriceHistory.objects.filter(asset=OuterRef("pk"))
                .order_by("-timestamp")
                .values("close")[:1]
            ),
            prev_close=Subquery(
                PriceHistory.objects.filter(asset=OuterRef("pk"))
                .order_by("-timestamp")
                .values("close")[1:2]
            ),
        )
    ]

    peer_ids = [p.id for p in peers]
    sparkline_map = defaultdict(list)
    if peer_ids:
        sparkline_qs = (
            PriceHistory.objects.filter(asset_id__in=peer_ids)
            .annotate(date=TruncDate("timestamp"))
            .order_by("asset_id", "-date", "-timestamp")
            .distinct("asset_id", "date")
            .values_list("asset_id", "close", "date")
        )
        async for asset_id, close, _date in sparkline_qs:
            if len(sparkline_map[asset_id]) < SPARKLINE_DATA_POINTS:
                sparkline_map[asset_id].append(float(close))
        for asset_id in sparkline_map:
            sparkline_map[asset_id].reverse()

    peer_data = []
    for peer in peers:
        change_pct = pct_change(peer.latest_close, peer.prev_close)
        closes = sparkline_map.get(peer.id, [])
        peer_data.append(
            {
                "asset": peer,
                "latest_close": peer.latest_close,
                "price_change_pct": round(change_pct, 2)
                if change_pct is not None
                else None,
                "sparkline_svg": build_sparkline_svg(closes, width=56, height=18),
            }
        )

    if peer_data:
        await cache.aset(cache_key, peer_data, PEERS_CACHE_TTL)

    return render(request, "core/partials/asset_peers.html", {"peers": peer_data})


async def asset_sentiment(request, ticker):
    """Partial: AI sentiment gauge. Runs agent in background thread if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request, "core/partials/asset_sentiment.html", {"insufficient": True}
        )

    data_key, fresh_key, _ = sentiment_cache_keys(ticker)
    cached = await cache.aget(data_key)

    if cached and await cache.aget(fresh_key):
        gauge_pct = (cached["sentiment_score"] + 1) * 50
        return render(
            request,
            "core/partials/asset_sentiment.html",
            {"sentiment": cached, "gauge_pct": gauge_pct},
        )

    total = (
        await asset.reddit_posts.acount()
        + await asset.hn_posts.acount()
        + await asset.news_articles.acount()
    )
    if total < SENTIMENT_MIN_POSTS:
        return render(
            request, "core/partials/asset_sentiment.html", {"insufficient": True}
        )

    # Fire-and-forget in a background thread on the web server itself,
    # keeping Celery workers free for heavy scraping/sync tasks.
    # The cache lock inside get_asset_sentiment prevents concurrent runs.
    analyse_sentiment.delay(asset.id)
    response = render(request, "core/partials/asset_sentiment.html", {"loading": True})
    response["HX-Trigger-After-Settle"] = '{"retrySentiment": true}'
    return response


async def report_card_financial_health(request, ticker):
    """Partial: report card financial health score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_financial_health.html",
            {"unavailable": True},
        )

    data_key, _, _ = financial_health_cache_keys(ticker)
    cached = await cache.aget(data_key)

    # Check if cached score is still valid (fingerprint matches current fundamentals)
    if cached:
        fundamental = await asset.fundamentals.afirst()
        if fundamental:
            if cached.get("source_hash") == financial_health_fingerprint(fundamental):
                filled_dots = int(round(cached["score"]))
                response = render(
                    request,
                    "core/partials/report_card_financial_health.html",
                    {"health": cached, "filled_dots": filled_dots},
                )
                response["HX-Trigger"] = "section-scored"
                return response

    has_fundamentals = await asset.fundamentals.aexists()
    if not has_fundamentals:
        return render(
            request,
            "core/partials/report_card_financial_health.html",
            {"unavailable": True},
        )

    analyse_financial_health.delay(asset.id)
    return render(
        request,
        "core/partials/report_card_financial_health.html",
        {"loading": True, "ticker": ticker, "poll_interval": REPORT_SECTION_POLL_INTERVAL_S},
    )


async def report_card_external_risk(request, ticker):
    """Partial: report card external risk score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_external_risk.html",
            {"unavailable": True},
        )

    data_key, fresh_key, _ = external_risk_cache_keys(ticker)
    cached = await cache.aget(data_key)

    if cached and await cache.aget(fresh_key):
        filled_dots = int(round(cached["score"]))
        response = render(
            request,
            "core/partials/report_card_external_risk.html",
            {"risk": cached, "filled_dots": filled_dots},
        )
        response["HX-Trigger"] = "section-scored"
        return response

    analyse_external_risk.delay(asset.id)
    return render(
        request,
        "core/partials/report_card_external_risk.html",
        {"loading": True, "ticker": ticker, "poll_interval": REPORT_SECTION_POLL_INTERVAL_S},
    )


async def report_card_valuation(request, ticker):
    """Partial: report card valuation score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_valuation.html",
            {"unavailable": True},
        )

    user_id = 0
    user_note = ""
    price_target = None
    if request.user.is_authenticated:
        user_asset = await UserAsset.objects.filter(
            user=request.user, asset=asset
        ).afirst()
        if user_asset:
            user_id = request.user.id
            user_note = user_asset.note
            if user_asset.price_target is not None:
                price_target = float(user_asset.price_target)

    data_key, _ = valuation_cache_keys(user_id, ticker)
    cached = await cache.aget(data_key)

    if cached:
        fundamental = await asset.fundamentals.afirst()
        latest_price = await asset.prices.afirst()
        if fundamental and latest_price:
            fp = valuation_fingerprint(
                fundamental, float(latest_price.close), user_note, price_target
            )
            if valuation_is_cache_valid(cached, fp):
                filled_dots = int(round(cached["score"]))
                response = render(
                    request,
                    "core/partials/report_card_valuation.html",
                    {"valuation": cached, "filled_dots": filled_dots},
                )
                response["HX-Trigger"] = "section-scored"
                return response

    has_fundamentals = await asset.fundamentals.aexists()
    if not has_fundamentals:
        return render(
            request,
            "core/partials/report_card_valuation.html",
            {"unavailable": True},
        )

    analyse_valuation.delay(asset.id, user_id, user_note, price_target)
    return render(
        request,
        "core/partials/report_card_valuation.html",
        {"loading": True, "ticker": ticker, "poll_interval": REPORT_SECTION_POLL_INTERVAL_S},
    )


async def report_card_product_flywheel(request, ticker):
    """Partial: report card product flywheel score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_product_flywheel.html",
            {"unavailable": True},
        )

    user_id = 0
    user_note = ""
    price_target = None
    if request.user.is_authenticated:
        user_asset = await UserAsset.objects.filter(
            user=request.user, asset=asset
        ).afirst()
        if user_asset:
            user_id = request.user.id
            user_note = user_asset.note
            if user_asset.price_target is not None:
                price_target = float(user_asset.price_target)

    data_key, _ = product_flywheel_cache_keys(user_id, ticker)
    cached = await cache.aget(data_key)

    if cached:
        fp = product_flywheel_fingerprint(user_note, price_target)
        if product_flywheel_is_cache_valid(cached, fp):
            filled_dots = int(round(cached["score"]))
            response = render(
                request,
                "core/partials/report_card_product_flywheel.html",
                {"flywheel": cached, "filled_dots": filled_dots},
            )
            response["HX-Trigger"] = "section-scored"
            return response

    analyse_product_flywheel.delay(asset.id, user_id, user_note, price_target)
    return render(
        request,
        "core/partials/report_card_product_flywheel.html",
        {"loading": True, "ticker": ticker, "poll_interval": REPORT_SECTION_POLL_INTERVAL_S},
    )


async def report_card_leadership(request, ticker):
    """Partial: report card leadership score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_leadership.html",
            {"unavailable": True},
        )

    user_id = 0
    user_note = ""
    price_target = None
    if request.user.is_authenticated:
        user_asset = await UserAsset.objects.filter(
            user=request.user, asset=asset
        ).afirst()
        if user_asset:
            user_id = request.user.id
            user_note = user_asset.note
            if user_asset.price_target is not None:
                price_target = float(user_asset.price_target)

    data_key, _ = leadership_cache_keys(user_id, ticker)
    cached = await cache.aget(data_key)

    if cached:
        fp = leadership_fingerprint(user_note, price_target)
        if leadership_is_cache_valid(cached, fp):
            filled_dots = int(round(cached["score"]))
            response = render(
                request,
                "core/partials/report_card_leadership.html",
                {"leadership": cached, "filled_dots": filled_dots},
            )
            response["HX-Trigger"] = "section-scored"
            return response

    analyse_leadership.delay(asset.id, user_id, user_note, price_target)
    return render(
        request,
        "core/partials/report_card_leadership.html",
        {"loading": True, "ticker": ticker, "poll_interval": REPORT_SECTION_POLL_INTERVAL_S},
    )


async def report_card_overall(request, ticker):
    """Partial: overall assessment synthesizing all 6 report card sections."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_overall.html",
            {"unavailable": True},
        )

    user_id = request.user.id if request.user.is_authenticated else 0

    # Gather all 6 section caches
    sections = {}

    # 1. Financial Health
    fh_key, _, _ = financial_health_cache_keys(ticker)
    cached_fh = await cache.aget(fh_key)
    if cached_fh and "score" in cached_fh:
        sections["financial_health"] = cached_fh

    # 2. Sentiment (normalise -1..1 → 0..5)
    sent_key, _, _ = sentiment_cache_keys(ticker)
    cached_sent = await cache.aget(sent_key)
    if cached_sent and "sentiment_score" in cached_sent:
        sections["sentiment"] = {
            "score": round((cached_sent["sentiment_score"] + 1) * 2.5, 1),
            "label": cached_sent.get("sentiment_label", ""),
            "brief": cached_sent.get("brief", ""),
            "key_themes": cached_sent.get("key_themes", []),
        }

    # 3. External Risk
    er_key, _, _ = external_risk_cache_keys(ticker)
    cached_er = await cache.aget(er_key)
    if cached_er and "score" in cached_er:
        sections["external_risk"] = cached_er

    # 4. Valuation
    val_key, _ = valuation_cache_keys(user_id, ticker)
    cached_val = await cache.aget(val_key)
    if cached_val and "score" in cached_val:
        sections["valuation"] = cached_val

    # 5. Product Flywheel
    fw_key, _ = product_flywheel_cache_keys(user_id, ticker)
    cached_fw = await cache.aget(fw_key)
    if cached_fw and "score" in cached_fw:
        sections["product_flywheel"] = cached_fw

    # 6. Leadership
    ld_key, _ = leadership_cache_keys(user_id, ticker)
    cached_ld = await cache.aget(ld_key)
    if cached_ld and "score" in cached_ld:
        sections["leadership"] = cached_ld

    # Need all 6 sections
    if len(sections) < 6:
        partial_total = round(sum(s.get("score", 0) for s in sections.values()), 1) if sections else None
        return render(
            request,
            "core/partials/report_card_overall.html",
            {
                "waiting": True,
                "ticker": ticker,
                "scored_count": len(sections),
                "report_card_total": partial_total,
            },
        )

    total_score = round(sum(s.get("score", 0) for s in sections.values()), 1)
    verdict = compute_verdict(total_score)

    # Check cache
    data_key, _ = overall_cache_keys(user_id, ticker)
    cached = await cache.aget(data_key)

    fp = overall_fingerprint(sections)

    if cached and overall_is_cache_valid(cached, fp):
        return render(
            request,
            "core/partials/report_card_overall.html",
            {
                "assessment": cached,
                "ticker": ticker,
                "report_card_total": total_score,
                "verdict": verdict,
            },
        )

    # Fire background agent
    analyse_overall.delay(asset.id, user_id, sections)
    return render(
        request,
        "core/partials/report_card_overall.html",
        {
            "loading": True,
            "ticker": ticker,
            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
            "report_card_total": total_score,
            "verdict": verdict,
        },
    )


async def asset_community(request, ticker):
    """Partial: reddit + HN + news articles. Fires background news sync."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/asset_community.html", {})

    fetch_asset_news.delay(asset.id)

    reddit_posts = [
        p async for p in asset.reddit_posts.all()[:ASSET_DETAIL_REDDIT_POSTS]
    ]
    hn_posts = [p async for p in asset.hn_posts.all()[:ASSET_DETAIL_HN_POSTS]]
    news_articles = [
        a async for a in asset.news_articles.all()[:ASSET_DETAIL_NEWS_ARTICLES]
    ]

    return render(
        request,
        "core/partials/asset_community.html",
        {
            "reddit_posts": reddit_posts,
            "hn_posts": hn_posts,
            "news_articles": news_articles,
        },
    )


async def _positive_day_stats(asset, now):
    """Compute positive-day % for multiple windows in a single DB round-trip."""
    sql = """
        WITH daily AS (
            SELECT DISTINCT ON ((timestamp::date))
                   timestamp, close
              FROM scraper_pricehistory
             WHERE asset_id = %s
             ORDER BY timestamp::date, timestamp DESC
        ),
        lagged AS (
            SELECT timestamp, close,
                   LAG(close) OVER (ORDER BY timestamp) AS prev_close
              FROM daily
        ),
        stats AS (
            SELECT timestamp,
                   CASE WHEN close >= prev_close THEN 1 ELSE 0 END AS up
              FROM lagged
             WHERE prev_close IS NOT NULL
        )
        SELECT days, total, positive FROM (VALUES
            ('30',   (SELECT COUNT(*) FROM stats WHERE timestamp >= %s),
                     (SELECT COUNT(*) FROM stats WHERE timestamp >= %s AND up = 1)),
            ('90',   (SELECT COUNT(*) FROM stats WHERE timestamp >= %s),
                     (SELECT COUNT(*) FROM stats WHERE timestamp >= %s AND up = 1)),
            ('365',  (SELECT COUNT(*) FROM stats WHERE timestamp >= %s),
                     (SELECT COUNT(*) FROM stats WHERE timestamp >= %s AND up = 1)),
            ('1825', (SELECT COUNT(*) FROM stats WHERE timestamp >= %s),
                     (SELECT COUNT(*) FROM stats WHERE timestamp >= %s AND up = 1)),
            ('all',  (SELECT COUNT(*) FROM stats),
                     (SELECT COUNT(*) FROM stats WHERE up = 1))
        ) AS t(days, total, positive);
    """
    cutoffs = [
        now - timedelta(days=d)
        for d in (30, 90, 365, 1825)
    ]
    params = [asset.id]
    for c in cutoffs:
        params.extend([c, c])

    def _run():
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    results = await sync_to_async(_run)()

    def _pct(key):
        total, positive = results.get(key, (0, 0))
        return round(positive / total * 100) if total > 0 else None

    return _pct("30"), _pct("90"), _pct("365"), _pct("1825"), _pct("all")


async def asset_prices(request, ticker):
    """Partial: recent prices table with daily change. Supports cursor-based pagination."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/asset_prices.html", {})

    before_param = request.GET.get("before")
    now = timezone.now()

    if before_param:
        try:
            upper_bound = datetime.fromisoformat(before_param)
        except ValueError:
            return render(request, "core/partials/asset_prices_page.html", {})
        if timezone.is_naive(upper_bound):
            upper_bound = timezone.make_aware(upper_bound)
    else:
        upper_bound = now

    cutoff = upper_bound - timedelta(days=PRICES_PAGE_DAYS)

    # Fetch prices in the window, one per day, newest first
    recent_prices_qs = [
        p
        async for p in asset.prices.filter(
            timestamp__gte=cutoff, timestamp__lt=upper_bound
        )
        .annotate(date=TruncDate("timestamp"))
        .order_by("-date", "-timestamp")
        .distinct("date")
    ]

    # Grab one extra price before the window for daily_change on the oldest row
    extra_price = await (
        asset.prices.filter(timestamp__lt=cutoff).order_by("-timestamp").afirst()
    )

    # Compute daily changes
    recent_prices = []
    for i, p in enumerate(recent_prices_qs):
        if i + 1 < len(recent_prices_qs):
            prev = recent_prices_qs[i + 1]
        elif extra_price:
            prev = extra_price
        else:
            prev = None

        if prev and prev.close:
            p.daily_change = float(p.close - prev.close)
            p.daily_change_pct = round(
                float((p.close - prev.close) / prev.close * 100), 2
            )
        else:
            p.daily_change = None
            p.daily_change_pct = None
        recent_prices.append(p)

    # Determine next cursor — midnight of the oldest date in this batch.
    # Using the truncated date (not raw timestamp) prevents duplicate rows
    # when multiple intraday prices exist for the same date.
    next_before = None
    if recent_prices:
        oldest_date = recent_prices[-1].date  # date from TruncDate annotation
        oldest_date_midnight = timezone.make_aware(
            datetime.combine(oldest_date, datetime.min.time())
        )
        has_older = await asset.prices.filter(
            timestamp__lt=oldest_date_midnight
        ).aexists()
        if has_older:
            next_before = oldest_date_midnight.isoformat()

    if before_param:
        # Subsequent page: just rows + sentinel
        return render(
            request,
            "core/partials/asset_prices_page.html",
            {
                "recent_prices": recent_prices,
                "next_before": next_before,
                "ticker": ticker,
            },
        )

    # Positive-day stats — single raw SQL query instead of loading full history.
    positive_30d, positive_90d, positive_1y, positive_5y, positive_all = (
        await _positive_day_stats(asset, now)
    )

    return render(
        request,
        "core/partials/asset_prices.html",
        {
            "recent_prices": recent_prices,
            "positive_30d": positive_30d,
            "positive_90d": positive_90d,
            "positive_1y": positive_1y,
            "positive_5y": positive_5y,
            "positive_all": positive_all,
            "next_before": next_before,
            "ticker": ticker,
        },
    )


CHART_RANGE_DAYS = {
    "1D": 1,
    "1W": 7,
    "1M": 30,
    "1Y": 365,
    "5Y": 1825,
}


@cache_page(PRICES_CACHE_TTL)
async def asset_chart_data(request, ticker):
    """JSON endpoint: price history for a specific chart range (?range=1W)."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()

    if not asset:
        return JsonResponse([], safe=False)

    range_key = request.GET.get("range", "1W").upper()
    now = timezone.now()

    if range_key == "ALL":
        # Hourly for last 7 days + daily for everything before
        hourly_cutoff = now - timedelta(days=7)
        daily_prices = [
            p
            async for p in asset.prices.filter(timestamp__lt=hourly_cutoff)
            .only("close", "timestamp")
            .annotate(date=TruncDate("timestamp"))
            .order_by("date", "-timestamp")
            .distinct("date")
        ]
        hourly_prices = [
            p
            async for p in asset.prices.filter(timestamp__gte=hourly_cutoff)
            .only("close", "timestamp")
            .order_by("timestamp")
        ]
        data = [
            {"close": float(p.close), "ts": int(p.timestamp.timestamp() * 1000)}
            for p in daily_prices
        ] + [
            {"close": float(p.close), "ts": int(p.timestamp.timestamp() * 1000)}
            for p in hourly_prices
        ]
    else:
        days = CHART_RANGE_DAYS.get(range_key, 7)
        cutoff = now - timedelta(days=days)

        if days <= 7:
            # Hourly granularity for 1D/1W
            qs = (
                asset.prices.filter(timestamp__gte=cutoff)
                .only("close", "timestamp")
                .order_by("timestamp")
            )
        else:
            # Daily granularity for 1M/1Y/5Y
            qs = (
                asset.prices.filter(timestamp__gte=cutoff)
                .only("close", "timestamp")
                .annotate(date=TruncDate("timestamp"))
                .order_by("date", "-timestamp")
                .distinct("date")
            )

        data = [
            {"close": float(p.close), "ts": int(p.timestamp.timestamp() * 1000)}
            async for p in qs
        ]

    return JsonResponse(data, safe=False)


@login_required
@require_POST
async def set_price_target(request, ticker):
    """HTMX endpoint: set or clear the user's price target for an asset."""
    ticker = ticker.upper()
    try:
        asset = await Asset.objects.aget(ticker=ticker)
    except Asset.DoesNotExist as err:
        raise Http404 from err

    raw = request.POST.get("price_target", "").strip()
    if raw:
        try:
            price_target = round(float(raw), 2)
            if price_target <= 0:
                raise ValueError
        except ValueError:
            return JsonResponse({"error": "Invalid price"}, status=400)
    else:
        price_target = None

    user_asset, _ = await UserAsset.objects.aget_or_create(
        user=request.user, asset=asset
    )
    user_asset.price_target = price_target
    await user_asset.asave(update_fields=["price_target"])

    return JsonResponse({"price_target": price_target})


@login_required
@require_POST
async def save_note(request, ticker):
    """HTMX endpoint: save the user's note for an asset."""
    ticker = ticker.upper()
    try:
        asset = await Asset.objects.aget(ticker=ticker)
    except Asset.DoesNotExist as err:
        raise Http404 from err

    note = request.POST.get("note", "").strip()

    user_asset, _ = await UserAsset.objects.aget_or_create(
        user=request.user, asset=asset
    )
    user_asset.note = note
    await user_asset.asave(update_fields=["note"])

    return JsonResponse({"ok": True})


async def asset_search(request):
    query = request.GET.get("q", "").strip()
    if len(query) < SEARCH_MIN_QUERY_LENGTH:
        return render(request, "core/partials/search_results.html", {"results": []})

    latest_close_sq = (
        PriceHistory.objects.filter(asset=OuterRef("pk"))
        .order_by("-timestamp")
        .values("close")[:1]
    )
    prev_close_sq = (
        PriceHistory.objects.filter(asset=OuterRef("pk"))
        .order_by("-timestamp")
        .values("close")[1:2]
    )

    assets = [
        a
        async for a in Asset.objects.filter(
            Q(ticker__icontains=query) | Q(name__icontains=query), is_active=True
        )
        .annotate(
            relevance=Case(
                When(ticker__iexact=query, then=Value(0)),
                When(ticker__istartswith=query, then=Value(1)),
                When(name__istartswith=query, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ),
            latest_close=Subquery(latest_close_sq),
            prev_close=Subquery(prev_close_sq),
        )
        .order_by("relevance", "ticker")[:SEARCH_MAX_RESULTS]
    ]

    # Batch-fetch sparkline data for all matched assets in one query
    asset_ids = [a.id for a in assets]
    sparkline_map = defaultdict(list)

    if asset_ids:
        sparkline_qs = (
            PriceHistory.objects.filter(asset_id__in=asset_ids)
            .annotate(date=TruncDate("timestamp"))
            .order_by("asset_id", "-date", "-timestamp")
            .distinct("asset_id", "date")
            .values_list("asset_id", "close", "date")
        )
        async for asset_id, close, _date in sparkline_qs:
            if len(sparkline_map[asset_id]) < SPARKLINE_DATA_POINTS:
                sparkline_map[asset_id].append(float(close))

        for asset_id in sparkline_map:
            sparkline_map[asset_id].reverse()

    results = []
    for asset in assets:
        closes = sparkline_map.get(asset.id, [])
        change_pct = pct_change(asset.latest_close, asset.prev_close)

        results.append(
            {
                "asset": asset,
                "latest_close": asset.latest_close,
                "price_change_pct": round(change_pct, 2)
                if change_pct is not None
                else None,
                "sparkline_svg": build_sparkline_svg(closes),
            }
        )

    # Fall back to Yahoo Finance search when local results are sparse
    yahoo_suggestions = []
    if len(results) < 3:
        local_tickers = {a.ticker for a in assets}
        yahoo_results = await sync_to_async(search_tickers)(query, max_results=6)
        for yq in yahoo_results:
            if yq["ticker"] not in local_tickers:
                yahoo_suggestions.append(yq)

    return render(
        request,
        "core/partials/search_results.html",
        {"results": results, "yahoo_suggestions": yahoo_suggestions},
    )


async def sign_up(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        form = await sync_to_async(SignUpForm)(request.POST)
        if await sync_to_async(form.is_valid)():
            cd = form.cleaned_data
            await sync_to_async(create_user)(
                first_name=cd["first_name"],
                last_name=cd["last_name"],
                username=cd["username"],
                email=cd["email"],
                password=cd["password1"],
            )
            await sync_to_async(sign_in_user)(
                request, username=cd["username"], password=cd["password1"]
            )
            return redirect("core:home")
    else:
        form = SignUpForm()

    return render(request, "core/auth/sign_up.html", {"form": form})


async def sign_in(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        form = await sync_to_async(SignInForm)(request, data=request.POST)
        if await sync_to_async(form.is_valid)():
            await sync_to_async(sign_in_user)(
                request,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            next_url = request.POST.get("next") or request.GET.get("next") or ""
            if not url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}
            ):
                next_url = "core:home"
            return redirect(next_url)
    else:
        form = SignInForm()

    return render(request, "core/auth/sign_in.html", {"form": form})


async def sign_out(request):
    if request.method == "POST":
        await sync_to_async(sign_out_user)(request)
    return redirect("core:home")


@login_required
async def profile(request):
    profile_saved = False
    password_changed = False

    is_post = request.method == "POST"
    profile_data = (
        request.POST if is_post and "update_profile" in request.POST else None
    )
    password_data = (
        request.POST if is_post and "change_password" in request.POST else None
    )

    profile_form = ProfileForm(profile_data, instance=request.user)
    password_form = TidalPasswordChangeForm(request.user, password_data)

    if profile_data and await sync_to_async(profile_form.is_valid)():
        cd = profile_form.cleaned_data
        await sync_to_async(update_profile)(
            request.user,
            first_name=cd["first_name"],
            last_name=cd["last_name"],
            currency=cd["currency"],
            timezone=cd["timezone"],
        )
        profile_saved = True
    elif password_data and await sync_to_async(password_form.is_valid)():
        await sync_to_async(password_form.save)()
        await sync_to_async(update_session_auth_hash)(request, request.user)
        password_changed = True
        password_form = TidalPasswordChangeForm(request.user)

    return render(
        request,
        "core/auth/profile.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "profile_saved": profile_saved,
            "password_changed": password_changed,
        },
    )
