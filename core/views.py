import asyncio
import json
import logging
import random
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from asgiref.sync import sync_to_async
from django.contrib.auth import update_session_auth_hash
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.cache import cache
from django.db import connection
from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponseForbidden, JsonResponse
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
from analyst.managers.digest_manager import (
    DIGEST_DATA_KEY,
    DIGEST_FRESH_KEY,
    DIGEST_LOCK_KEY,
)
from analyst.managers.finance_manager import (
    _cache_keys as finance_cache_keys,
)
from analyst.managers.finance_manager import (
    _source_fingerprint as finance_fingerprint,
)
from analyst.managers.overall_assessment_manager import (
    _base_cache_keys as overall_base_cache_keys,
)
from analyst.managers.overall_assessment_manager import (
    _is_cache_valid as overall_is_cache_valid,
)
from analyst.managers.overall_assessment_manager import (
    _source_fingerprint as overall_fingerprint,
)
from analyst.managers.overall_assessment_manager import (
    _user_cache_keys as overall_user_cache_keys,
)
from analyst.managers.overall_assessment_manager import (
    compute_verdict,
    compute_weighted_score,
    expected_section_count,
    sections_for_asset,
)
from analyst.managers.people_manager import (
    _base_cache_keys as people_base_cache_keys,
)
from analyst.managers.people_manager import (
    _base_source_fingerprint as people_base_fingerprint,
)
from analyst.managers.people_manager import (
    _is_cache_valid as people_is_cache_valid,
)
from analyst.managers.people_manager import (
    _revision_cache_keys as people_revision_cache_keys,
)
from analyst.managers.personal_outlook_manager import _cache_keys as outlook_cache_keys
from analyst.managers.product_manager import (
    _base_cache_keys as product_base_cache_keys,
)
from analyst.managers.product_manager import (
    _base_source_fingerprint as product_base_fingerprint,
)
from analyst.managers.product_manager import (
    _is_cache_valid as product_is_cache_valid,
)
from analyst.managers.product_manager import (
    _revision_cache_keys as product_revision_cache_keys,
)
from analyst.managers.risk_manager import (
    _cache_keys as risk_cache_keys,
)
from analyst.managers.sentiment_manager import _cache_keys as sentiment_cache_keys
from analyst.managers.valuation_manager import (
    _base_cache_keys as valuation_base_cache_keys,
)
from analyst.managers.valuation_manager import (
    _base_source_fingerprint as valuation_base_fingerprint,
)
from analyst.managers.valuation_manager import (
    _is_cache_valid as valuation_is_cache_valid,
)
from analyst.managers.valuation_manager import (
    _revision_cache_keys as valuation_revision_cache_keys,
)
from analyst.tasks import (
    analyse_finance,
    analyse_overall,
    analyse_people,
    analyse_product,
    analyse_risk,
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
    SEARCH_RECENTS_LIMIT,
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
from core.managers.valuation_manager import compute_rsi, compute_valuations
from core.models import UserAsset
from core.sparkline import build_sparkline_svg
from core.utils import fetch_sparkline_map, pct_change, total_post_count
from scraper.clients.yfinance_client import search_tickers
from scraper.managers.asset_manager import get_or_create_asset
from scraper.models import Asset, AssetView, PriceHistory
from scraper.tasks import (
    fetch_asset_news,
    fetch_fundamentals_for_asset,
    refresh_asset_prices,
    sync_new_asset_prices,
)

logger = logging.getLogger(__name__)


async def _cached(key: str, compute, ttl: int = HOME_COUNTS_CACHE_TTL):
    value = await cache.aget(key)
    if value is None:
        value = await sync_to_async(compute)()
        await cache.aset(key, value, ttl)
    return value


@cache_page(60 * 60 * 24)
def pwa_manifest(request):
    return JsonResponse(
        {
            "name": "TidalSight",
            "short_name": "TidalSight",
            "description": (
                "Continuous intelligence from multi-agent AI"
                " across every major asset class."
            ),
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0d0c0a",
            "theme_color": "#0d0c0a",
            "icons": [
                {
                    "src": staticfiles_storage.url("favicon.webp"),
                    "sizes": "192x192",
                    "type": "image/webp",
                },
                {
                    "src": staticfiles_storage.url("icon-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                },
            ],
        },
        content_type="application/manifest+json",
    )


async def home(request):
    hour = timezone.localtime(timezone.now()).hour
    if hour < 12:
        greeting = random.choice(
            [
                "Good morning",
                "Top of the morning",
                "Welcome back",
            ]
        )
    elif hour < 18:
        greeting = random.choice(
            [
                "Good afternoon",
                "Good day",
                "Welcome back",
            ]
        )
    else:
        greeting = random.choice(
            [
                "Good evening",
                "Welcome back",
            ]
        )

    context = {
        "greeting": greeting,
        "asset_count": await _cached("home:asset_count", Asset.objects.count),
        "post_count": await _cached("home:post_count", total_post_count),
        "digest_refresh_interval": DIGEST_REFRESH_INTERVAL,
        "digest_date": timezone.now(),
    }

    # Recent tickers for the search pills (authenticated users)
    if request.user.is_authenticated:
        recent_tickers = [
            ticker
            async for ticker in Asset.objects.filter(asset_views__user=request.user)
            .annotate(last_viewed=Max("asset_views__viewed_at"))
            .order_by("-last_viewed")
            .values_list("ticker", flat=True)[:SEARCH_RECENTS_LIMIT]
        ]
        if recent_tickers:
            context["recent_tickers"] = recent_tickers

    return render(request, "core/home.html", context)


async def rankings(request):
    """Rankings page: assets ranked by report card score."""
    view = request.GET.get("view", "public")
    is_authenticated = request.user.is_authenticated
    if not is_authenticated:
        view = "public"

    ranked = [
        a
        async for a in Asset.objects.filter(is_active=True, report_card_score__gt=0)
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
        .order_by("-report_card_score", "ticker")
    ]

    if view == "yours" and is_authenticated:
        # Find assets where the user has notes or a price target
        personalized_asset_ids = set()
        async for ua in (
            UserAsset.objects.filter(user=request.user)
            .exclude(note="", price_target__isnull=True)
            .only("asset_id")
        ):
            personalized_asset_ids.add(ua.asset_id)

        if personalized_asset_ids:
            # Batch cache lookups for personalized overall scores
            ticker_asset_map = {
                a.ticker: a for a in ranked if a.id in personalized_asset_ids
            }
            cache_tasks = {}
            for ticker in ticker_asset_map:
                data_key, _ = overall_user_cache_keys(request.user.id, ticker)
                cache_tasks[ticker] = cache.aget(data_key)

            results = await asyncio.gather(*cache_tasks.values())
            for ticker, cached in zip(cache_tasks.keys(), results, strict=True):
                if cached and "score" in cached:
                    asset = ticker_asset_map[ticker]
                    asset.report_card_score = cached["score"]
                    if cached.get("target_price") is not None:
                        asset.target_price = cached["target_price"]
                    asset.is_personalized = True

            # Re-sort after overlaying personalized scores
            ranked.sort(key=lambda a: (-a.report_card_score, a.ticker))

    for i, asset in enumerate(ranked, 1):
        asset.rank = i
        asset.verdict = compute_verdict(asset.report_card_score)
        asset.daily_change = pct_change(asset.latest_close, asset.prev_close)
        if not hasattr(asset, "is_personalized"):
            asset.is_personalized = False
        if asset.target_price and asset.latest_close:
            asset.upside = float(
                (float(asset.target_price) - float(asset.latest_close))
                / float(asset.latest_close)
                * 100
            )
        else:
            asset.upside = None

    # Build score distribution - scores 8-28 (realistic range)
    score_buckets = []
    for s in range(8, 29):
        bucket_assets = [a for a in ranked if a.report_card_score == s]
        if s <= 12:
            verdict = "Strong Sell"
            css = "ss"
        elif s <= 16:
            verdict = "Sell"
            css = "s"
        elif s <= 21:
            verdict = "Hold"
            css = "h"
        elif s <= 25:
            verdict = "Buy"
            css = "b"
        else:
            verdict = "Strong Buy"
            css = "sb"
        score_buckets.append(
            {"score": s, "assets": bucket_assets, "verdict": verdict, "css": css}
        )
    max_bucket_count = max((len(b["assets"]) for b in score_buckets), default=1) or 1

    return render(
        request,
        "core/rankings.html",
        {
            "ranked_assets": ranked,
            "active_view": view,
            "score_buckets": score_buckets,
            "max_bucket_count": max_bucket_count,
        },
    )


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

    sparkline_map = await fetch_sparkline_map([a.id for a in watched])

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
    digest = await cache.aget(DIGEST_DATA_KEY)

    if digest:
        if digest.get("generated_at"):
            digest["generated_at"] = datetime.fromisoformat(digest["generated_at"])
        # If not fresh and no task running, kick off background regeneration
        is_fresh = await cache.aget(DIGEST_FRESH_KEY)
        if not is_fresh:
            is_locked = await cache.aget(DIGEST_LOCK_KEY)
            if not is_locked:
                from analyst.tasks import generate_market_digest

                generate_market_digest.delay()
        return render(request, "core/partials/market_digest.html", {"digest": digest})

    # No cached data — fire task if not already running, return polling skeleton
    is_locked = await cache.aget(DIGEST_LOCK_KEY)
    if not is_locked:
        from analyst.tasks import generate_market_digest

        generate_market_digest.delay()
    return render(request, "core/partials/market_digest.html", {"loading": True})


async def personal_outlook(request):
    """HTMX partial: personalised briefing based on user's watchlist."""
    user_id = request.user.id
    has_watchlist = await UserAsset.objects.filter(
        user_id=user_id, in_watchlist=True
    ).aexists()
    if not has_watchlist:
        return render(
            request, "core/partials/personal_outlook.html", {"no_watchlist": True}
        )

    data_key, fresh_key, lock_key = outlook_cache_keys(user_id)
    outlook = await cache.aget(data_key)

    if outlook:
        if outlook.get("generated_at"):
            outlook["generated_at"] = datetime.fromisoformat(outlook["generated_at"])
        # If not fresh and no task already running, kick off background regeneration
        is_fresh = await cache.aget(fresh_key)
        if not is_fresh:
            is_locked = await cache.aget(lock_key)
            if not is_locked:
                from analyst.tasks import generate_personal_outlook

                generate_personal_outlook.delay(user_id)
        return render(
            request, "core/partials/personal_outlook.html", {"outlook": outlook}
        )

    # No cached data — fire task only if not already running, return polling skeleton
    is_locked = await cache.aget(lock_key)
    if not is_locked:
        from analyst.tasks import generate_personal_outlook

        generate_personal_outlook.delay(user_id)
    return render(request, "core/partials/personal_outlook.html", {"loading": True})


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

    sparkline_map = await fetch_sparkline_map([a.id for a in assets])

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
        logger.warning("Asset unavailable: %s", ticker, exc_info=True)
        return render(
            request, "core/asset_unavailable.html", {"ticker": ticker}, status=503
        )

    # For new assets with no price data, dispatch background sync
    if not await asset.prices.aexists():
        sync_new_asset_prices.delay(asset.id)

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
            "report_section_poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
            "user_has_notes": bool(user_note or price_target is not None),
            "expected_section_count": expected_section_count(asset.asset_class),
            "verdict": compute_verdict(asset.report_card_score)
            if asset.report_card_score
            else None,
        },
    )


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

    refresh_asset_prices.delay(asset.id)

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

    fetch_fundamentals_for_asset.delay(asset.id)

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
            or (timezone.now() - asset.description_updated_at).days
            > DESCRIPTION_FRESHNESS_DAYS
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

    sparkline_map = await fetch_sparkline_map([p.id for p in peers])

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
        gauge_pct = ((cached["score"] - 1) / 3) * 100
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
        fetch_asset_news.delay(asset.id)
    else:
        analyse_sentiment.delay(asset.id)

    response = render(request, "core/partials/asset_sentiment.html", {"loading": True})
    response["HX-Trigger-After-Settle"] = '{"retrySentiment": true}'
    return response


async def report_card_sentiment(request, ticker):
    """Partial: report card sentiment tile. Polls until sentiment agent finishes."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/report_card_sentiment.html", {})

    data_key, fresh_key, lock_key = sentiment_cache_keys(ticker)
    cached = await cache.aget(data_key)

    if cached and await cache.aget(fresh_key):
        filled_dots = round(cached["score"])
        response = render(
            request,
            "core/partials/report_card_sentiment.html",
            {"sentiment": cached, "filled_dots": filled_dots, "ticker": ticker},
        )
        response["HX-Trigger"] = "section-scored"
        return response

    total = (
        await asset.reddit_posts.acount()
        + await asset.hn_posts.acount()
        + await asset.news_articles.acount()
    )

    if total < SENTIMENT_MIN_POSTS:
        # Kick off targeted news fetch so sources accumulate for this asset
        fetch_asset_news.delay(asset.id)
    elif not await cache.aget(lock_key):
        analyse_sentiment.delay(asset.id)

    # Always poll — either waiting for sources to arrive or for agent to finish
    response = render(
        request,
        "core/partials/report_card_sentiment.html",
        {
            "loading": True,
            "ticker": ticker,
            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
        },
    )
    response["HX-Trigger-After-Settle"] = '{"pollReportCardSentiment": true}'
    return response


async def report_card_finance(request, ticker):
    """Partial: report card financial health score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_finance.html",
            {"unavailable": True},
        )

    data_key, _, lock_key = finance_cache_keys(ticker)
    cached = await cache.aget(data_key)
    fundamental = await asset.fundamentals.afirst()

    # Serve cached score when valid (fingerprint matches) or when we have any cached score (show immediately, refresh in background if stale)
    if cached and "score" in cached:
        fingerprint_ok = fundamental and cached.get(
            "source_hash"
        ) == finance_fingerprint(fundamental)
        if fingerprint_ok:
            filled_dots = round(cached["score"])
            response = render(
                request,
                "core/partials/report_card_finance.html",
                {"health": cached, "filled_dots": filled_dots, "ticker": ticker},
            )
            response["HX-Trigger"] = "section-scored"
            return response
        # Cached data exists but fingerprint mismatch (e.g. fundamentals updated): show cache immediately so user doesn't wait 10-30s
        filled_dots = round(cached["score"])
        response = render(
            request,
            "core/partials/report_card_finance.html",
            {"health": cached, "filled_dots": filled_dots, "ticker": ticker},
        )
        response["HX-Trigger"] = "section-scored"
        if fundamental and not await cache.aget(lock_key):
            analyse_finance.delay(asset.id)  # refresh in background
        return response

    if not fundamental:
        # Kick off fundamentals fetch so finance can proceed once data arrives
        fetch_fundamentals_for_asset.delay(asset.id)
    elif not await cache.aget(lock_key):
        analyse_finance.delay(asset.id)

    # Always poll — either waiting for fundamentals or for agent to finish
    return render(
        request,
        "core/partials/report_card_finance.html",
        {
            "loading": True,
            "ticker": ticker,
            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
        },
    )


async def report_card_risk(request, ticker):
    """Partial: report card external risk score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_risk.html",
            {"unavailable": True},
        )

    data_key, fresh_key, lock_key = risk_cache_keys(ticker)
    cached = await cache.aget(data_key)

    if cached and await cache.aget(fresh_key):
        filled_dots = round(cached["score"])
        response = render(
            request,
            "core/partials/report_card_risk.html",
            {"risk": cached, "filled_dots": filled_dots, "ticker": ticker},
        )
        response["HX-Trigger"] = "section-scored"
        return response

    if not await cache.aget(lock_key):
        analyse_risk.delay(asset.id)
    return render(
        request,
        "core/partials/report_card_risk.html",
        {
            "loading": True,
            "ticker": ticker,
            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
        },
    )


class _UserContext(NamedTuple):
    user_id: int
    note: str
    price_target: float | None


async def _get_user_context(request, asset) -> _UserContext:
    """Return user context for the current user + asset."""
    if not request.user.is_authenticated:
        return _UserContext(0, "", None)
    user_asset = await UserAsset.objects.filter(user=request.user, asset=asset).afirst()
    if not user_asset:
        return _UserContext(0, "", None)
    price_target = (
        float(user_asset.price_target) if user_asset.price_target is not None else None
    )
    return _UserContext(request.user.id, user_asset.note, price_target)


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

    user_id, user_note, price_target = await _get_user_context(request, asset)

    view_mode = request.GET.get("view", "")
    force_base = view_mode == "base"

    wants_revision = not force_base and (user_note or price_target is not None)

    # Check revision cache first if user has notes
    cached = None
    if wants_revision:
        rev_key, rev_lock_key = valuation_revision_cache_keys(user_id, ticker)
        cached = await cache.aget(rev_key)

    base_key, base_lock_key = valuation_base_cache_keys(ticker)
    if not cached:
        cached = await cache.aget(base_key)

    if cached:
        # Revised entries are validated by the Celery task; serve directly
        if cached.get("is_revised"):
            filled_dots = round(cached["score"])
            response = render(
                request,
                "core/partials/report_card_valuation.html",
                {
                    "valuation": cached,
                    "filled_dots": filled_dots,
                    "view_mode": view_mode,
                    "ticker": ticker,
                },
            )
            response["HX-Trigger"] = "section-scored"
            return response

        # Base entries: check fingerprint against current fundamentals
        fundamental = await asset.fundamentals.afirst()
        latest_price = await asset.prices.afirst()
        if fundamental and latest_price:
            rsi = await sync_to_async(compute_rsi)(asset)
            fp = valuation_base_fingerprint(fundamental, float(latest_price.close), rsi)
            if valuation_is_cache_valid(cached, fp):
                # Base is valid — but if user wants a revision, dispatch it
                if wants_revision:
                    if not await cache.aget(rev_lock_key):
                        analyse_valuation.delay(
                            asset.id, user_id, user_note, price_target
                        )
                    return render(
                        request,
                        "core/partials/report_card_valuation.html",
                        {
                            "loading": True,
                            "ticker": ticker,
                            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
                            "view_mode": view_mode,
                        },
                    )
                filled_dots = round(cached["score"])
                response = render(
                    request,
                    "core/partials/report_card_valuation.html",
                    {
                        "valuation": cached,
                        "filled_dots": filled_dots,
                        "view_mode": view_mode,
                        "ticker": ticker,
                    },
                )
                response["HX-Trigger"] = "section-scored"
                return response

    has_fundamentals = await asset.fundamentals.aexists()
    if not has_fundamentals:
        # Kick off fundamentals fetch so valuation can proceed once data arrives
        fetch_fundamentals_for_asset.delay(asset.id)
    elif not await cache.aget(base_lock_key):
        analyse_valuation.delay(asset.id, user_id, user_note, price_target)

    # Always poll — either waiting for fundamentals or for agent to finish
    return render(
        request,
        "core/partials/report_card_valuation.html",
        {
            "loading": True,
            "ticker": ticker,
            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
            "view_mode": view_mode,
        },
    )


async def report_card_product(request, ticker):
    """Partial: report card product flywheel score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_product.html",
            {"unavailable": True},
        )

    user_id, user_note, price_target = await _get_user_context(request, asset)

    view_mode = request.GET.get("view", "")
    force_base = view_mode == "base"

    wants_revision = not force_base and (user_note or price_target is not None)

    # Check revision cache first if user has notes
    cached = None
    if wants_revision:
        rev_key, rev_lock_key = product_revision_cache_keys(user_id, ticker)
        cached = await cache.aget(rev_key)

    base_key, base_lock_key = product_base_cache_keys(ticker)
    if not cached:
        cached = await cache.aget(base_key)

    if cached:
        if cached.get("is_revised"):
            filled_dots = round(cached["score"])
            response = render(
                request,
                "core/partials/report_card_product.html",
                {
                    "flywheel": cached,
                    "filled_dots": filled_dots,
                    "view_mode": view_mode,
                    "ticker": ticker,
                },
            )
            response["HX-Trigger"] = "section-scored"
            return response
        else:
            fp = product_base_fingerprint()
            if product_is_cache_valid(cached, fp):
                if wants_revision:
                    if not await cache.aget(rev_lock_key):
                        analyse_product.delay(
                            asset.id, user_id, user_note, price_target
                        )
                    return render(
                        request,
                        "core/partials/report_card_product.html",
                        {
                            "loading": True,
                            "ticker": ticker,
                            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
                            "view_mode": view_mode,
                        },
                    )
                filled_dots = round(cached["score"])
                response = render(
                    request,
                    "core/partials/report_card_product.html",
                    {
                        "flywheel": cached,
                        "filled_dots": filled_dots,
                        "view_mode": view_mode,
                        "ticker": ticker,
                    },
                )
                response["HX-Trigger"] = "section-scored"
                return response

    if not await cache.aget(base_lock_key):
        analyse_product.delay(asset.id, user_id, user_note, price_target)
    return render(
        request,
        "core/partials/report_card_product.html",
        {
            "loading": True,
            "ticker": ticker,
            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
            "view_mode": view_mode,
        },
    )


async def report_card_people(request, ticker):
    """Partial: report card people score. Runs agent in background if not cached."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_people.html",
            {"unavailable": True},
        )

    user_id, user_note, price_target = await _get_user_context(request, asset)

    view_mode = request.GET.get("view", "")
    force_base = view_mode == "base"

    wants_revision = not force_base and (user_note or price_target is not None)

    # Check revision cache first if user has notes
    cached = None
    if wants_revision:
        rev_key, rev_lock_key = people_revision_cache_keys(user_id, ticker)
        cached = await cache.aget(rev_key)

    base_key, base_lock_key = people_base_cache_keys(ticker)
    if not cached:
        cached = await cache.aget(base_key)

    if cached:
        if cached.get("is_revised"):
            filled_dots = round(cached["score"])
            response = render(
                request,
                "core/partials/report_card_people.html",
                {
                    "people": cached,
                    "filled_dots": filled_dots,
                    "view_mode": view_mode,
                    "ticker": ticker,
                },
            )
            response["HX-Trigger"] = "section-scored"
            return response
        else:
            fp = people_base_fingerprint()
            if people_is_cache_valid(cached, fp):
                if wants_revision:
                    if not await cache.aget(rev_lock_key):
                        analyse_people.delay(asset.id, user_id, user_note, price_target)
                    return render(
                        request,
                        "core/partials/report_card_people.html",
                        {
                            "loading": True,
                            "ticker": ticker,
                            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
                            "view_mode": view_mode,
                        },
                    )
                filled_dots = round(cached["score"])
                response = render(
                    request,
                    "core/partials/report_card_people.html",
                    {
                        "people": cached,
                        "filled_dots": filled_dots,
                        "view_mode": view_mode,
                        "ticker": ticker,
                    },
                )
                response["HX-Trigger"] = "section-scored"
                return response

    if not await cache.aget(base_lock_key):
        analyse_people.delay(asset.id, user_id, user_note, price_target)
    return render(
        request,
        "core/partials/report_card_people.html",
        {
            "loading": True,
            "ticker": ticker,
            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
            "view_mode": view_mode,
        },
    )


async def report_card_overall(request, ticker):
    """Partial: overall assessment synthesizing all report card sections."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(
            request,
            "core/partials/report_card_overall.html",
            {"unavailable": True},
        )

    user_id = request.user.id if request.user.is_authenticated else 0

    view_mode = request.GET.get("view", "")
    force_base = view_mode == "base"

    # Determine if user has notes (for toggle visibility + revision lookups)
    user_has_notes = False
    if request.user.is_authenticated:
        user_asset = await UserAsset.objects.filter(
            user=request.user, asset=asset
        ).afirst()
        if user_asset and (user_asset.note or user_asset.price_target is not None):
            user_has_notes = True

    use_revisions = user_has_notes and not force_base

    # Determine which sections apply to this asset class
    hygiene_keys, motivator_keys = sections_for_asset(asset.asset_class)
    all_keys = set(hygiene_keys + motivator_keys)
    expected = expected_section_count(asset.asset_class)

    # Gather section caches
    sections = {}

    # Financial Health (equity only)
    if "finance" in all_keys:
        fh_key, _, _ = finance_cache_keys(ticker)
        cached_fh = await cache.aget(fh_key)
        if cached_fh and "score" in cached_fh:
            sections["finance"] = cached_fh

    # Sentiment
    sent_key, _, _ = sentiment_cache_keys(ticker)
    cached_sent = await cache.aget(sent_key)
    if cached_sent and "score" in cached_sent:
        sections["sentiment"] = cached_sent

    # Risk
    er_key, _, _ = risk_cache_keys(ticker)
    cached_er = await cache.aget(er_key)
    if cached_er and "score" in cached_er:
        sections["risk"] = cached_er

    # Valuation — check revision cache if user has notes, fall back to base
    cached_val = None
    if use_revisions:
        rev_key, _ = valuation_revision_cache_keys(user_id, ticker)
        cached_val = await cache.aget(rev_key)
    if not cached_val:
        base_key, _ = valuation_base_cache_keys(ticker)
        cached_val = await cache.aget(base_key)
    if cached_val and "score" in cached_val:
        sections["valuation"] = cached_val

    # Product — check revision cache if user has notes, fall back to base
    cached_fw = None
    if use_revisions:
        rev_key, _ = product_revision_cache_keys(user_id, ticker)
        cached_fw = await cache.aget(rev_key)
    if not cached_fw:
        base_key, _ = product_base_cache_keys(ticker)
        cached_fw = await cache.aget(base_key)
    if cached_fw and "score" in cached_fw:
        sections["product"] = cached_fw

    # People (equity only) — check revision cache if user has notes, fall back to base
    if "people" in all_keys:
        cached_ppl = None
        if use_revisions:
            rev_key, _ = people_revision_cache_keys(user_id, ticker)
            cached_ppl = await cache.aget(rev_key)
        if not cached_ppl:
            base_key, _ = people_base_cache_keys(ticker)
            cached_ppl = await cache.aget(base_key)
        if cached_ppl and "score" in cached_ppl:
            sections["people"] = cached_ppl

    # Need all expected sections
    if len(sections) < expected:
        partial_total = (
            compute_weighted_score(sections, asset.asset_class) if sections else None
        )
        return render(
            request,
            "core/partials/report_card_overall.html",
            {
                "waiting": True,
                "ticker": ticker,
                "scored_count": len(sections),
                "expected_count": expected,
                "report_card_total": partial_total,
                "view_mode": view_mode,
            },
        )

    total_score = compute_weighted_score(sections, asset.asset_class)
    verdict = compute_verdict(total_score)

    # Check overall cache — use user key if revisions exist, base otherwise
    has_revisions = any(
        sections.get(key, {}).get("is_revised", False) for key in motivator_keys
    )

    if has_revisions:
        data_key, lock_key = overall_user_cache_keys(user_id, ticker)
    else:
        data_key, lock_key = overall_base_cache_keys(ticker)
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
                "view_mode": view_mode,
            },
        )

    # Fire background agent
    if not await cache.aget(lock_key):
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
            "view_mode": view_mode,
        },
    )


SECTION_TEMPLATES = {
    "sentiment": "core/partials/report_card_sentiment.html",
    "finance": "core/partials/report_card_finance.html",
    "risk": "core/partials/report_card_risk.html",
    "valuation": "core/partials/report_card_valuation.html",
    "product": "core/partials/report_card_product.html",
    "people": "core/partials/report_card_people.html",
    "overall": "core/partials/report_card_overall.html",
}


@require_POST
async def regenerate_report_card(request, ticker, section):
    """Staff-only: clear cache and re-dispatch analysis for a report card section."""
    if not request.user.is_staff:
        return HttpResponseForbidden()

    if section not in SECTION_TEMPLATES:
        raise Http404

    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker, is_active=True).afirst()
    if not asset:
        raise Http404

    # Clear cache keys per section
    if section == "sentiment":
        keys = list(sentiment_cache_keys(ticker))
        await cache.adelete_many(keys)
        analyse_sentiment.delay(asset.id)
    elif section == "finance":
        keys = list(finance_cache_keys(ticker))
        await cache.adelete_many(keys)
        analyse_finance.delay(asset.id)
    elif section == "risk":
        keys = list(risk_cache_keys(ticker))
        await cache.adelete_many(keys)
        analyse_risk.delay(asset.id)
    elif section == "valuation":
        keys = list(valuation_base_cache_keys(ticker))
        await cache.adelete_many(keys)
        analyse_valuation.delay(asset.id, 0, "", None)
    elif section == "product":
        keys = list(product_base_cache_keys(ticker))
        await cache.adelete_many(keys)
        analyse_product.delay(asset.id, 0, "", None)
    elif section == "people":
        keys = list(people_base_cache_keys(ticker))
        await cache.adelete_many(keys)
        analyse_people.delay(asset.id, 0, "", None)
    elif section == "overall":
        keys = list(overall_base_cache_keys(ticker))
        await cache.adelete_many(keys)
        # No task dispatch — return waiting state, let polling handle it

    template = SECTION_TEMPLATES[section]

    if section == "overall":
        return render(
            request,
            template,
            {
                "waiting": True,
                "ticker": ticker,
                "expected_count": expected_section_count(asset.asset_class),
            },
        )

    return render(
        request,
        template,
        {
            "loading": True,
            "ticker": ticker,
            "poll_interval": REPORT_SECTION_POLL_INTERVAL_S,
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

    # Merge into a single chronological feed
    mentions = []
    for p in reddit_posts:
        mentions.append(
            {
                "type": "reddit",
                "title": p.title,
                "url": p.url,
                "date": p.posted_at,
                "score": p.score,
                "num_comments": p.num_comments,
                "subreddit": p.subreddit,
                "author": p.author,
            }
        )
    for p in hn_posts:
        mentions.append(
            {
                "type": "hn",
                "title": p.title,
                "url": p.url,
                "date": p.posted_at,
                "score": p.score,
                "num_comments": p.num_comments,
                "author": p.author,
            }
        )
    for a in news_articles:
        mentions.append(
            {
                "type": "news",
                "title": a.title,
                "url": a.url,
                "date": a.posted_at,
                "source": a.source,
            }
        )
    _min_dt = datetime.min.replace(tzinfo=UTC)
    mentions.sort(key=lambda m: m["date"] or _min_dt, reverse=True)

    return render(
        request,
        "core/partials/asset_community.html",
        {"mentions": mentions},
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
    cutoffs = [now - timedelta(days=d) for d in (30, 90, 365, 1825)]
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
    (
        positive_30d,
        positive_90d,
        positive_1y,
        positive_5y,
        positive_all,
    ) = await _positive_day_stats(asset, now)

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


async def _clear_revision_caches(user_id: int, ticker: str) -> None:
    """Clear all motivator revision caches and user overall cache for a user+ticker."""
    keys = []
    for cache_fn in (
        valuation_revision_cache_keys,
        product_revision_cache_keys,
        people_revision_cache_keys,
    ):
        data_key, lock_key = cache_fn(user_id, ticker)
        keys.extend([data_key, lock_key])
    # Also clear the user-specific overall cache so it regenerates with new revisions
    overall_data, overall_lock = overall_user_cache_keys(user_id, ticker)
    keys.extend([overall_data, overall_lock])
    await cache.adelete_many(keys)


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

    await _clear_revision_caches(request.user.id, ticker)

    return JsonResponse({"price_target": price_target})


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

    await _clear_revision_caches(request.user.id, ticker)

    return JsonResponse({"ok": True})


async def asset_search(request):
    query = request.GET.get("q", "").strip()
    if len(query) < SEARCH_MIN_QUERY_LENGTH:
        # Empty query — show recently viewed assets for authenticated users
        if request.user.is_authenticated:
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
                    asset_views__user=request.user, is_active=True
                )
                .annotate(
                    last_viewed=Max("asset_views__viewed_at"),
                    latest_close=Subquery(latest_close_sq),
                    prev_close=Subquery(prev_close_sq),
                )
                .order_by("-last_viewed")[:SEARCH_RECENTS_LIMIT]
            ]
            if assets:
                sparkline_map = await fetch_sparkline_map([a.id for a in assets])
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
                return render(
                    request,
                    "core/partials/search_results.html",
                    {"results": results, "is_recents": True},
                )
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

    sparkline_map = await fetch_sparkline_map([a.id for a in assets])

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
