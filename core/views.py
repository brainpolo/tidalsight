import json
from collections import defaultdict
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
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

from analyst.app_behaviour import DIGEST_REFRESH_INTERVAL
from analyst.managers.digest_manager import get_market_digest
from analyst.managers.peer_manager import sync_peers
from core.app_behaviour import (
    ASSET_DETAIL_FAVICON_SIZE,
    ASSET_DETAIL_HN_POSTS,
    ASSET_DETAIL_NEWS_ARTICLES,
    ASSET_DETAIL_RECENT_PRICES_DAYS,
    ASSET_DETAIL_REDDIT_POSTS,
    DEFAULT_CHART_RANGE,
    HOME_COUNTS_CACHE_TTL,
    PEERS_CACHE_TTL,
    PRICES_CACHE_TTL,
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
from core.sparkline import build_sparkline_svg
from core.utils import pct_change, total_post_count
from scraper.managers.asset_manager import (
    get_or_create_asset,
    sync_all_prices,
    sync_full_prices_async,
    sync_fundamentals,
    sync_quick_prices,
)
from scraper.managers.brave_news_manager import sync_asset_news_async
from scraper.models import Asset, AssetView, PriceHistory


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
    watched = [
        a
        async for a in request.user.watchlist.filter(is_active=True)
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
        sync_full_prices_async(asset, ticker)

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

    is_watched = (
        request.user.is_authenticated
        and await request.user.watchlist.filter(pk=asset.pk).aexists()
    )

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

    if await request.user.watchlist.filter(pk=asset.pk).aexists():
        await request.user.watchlist.aremove(asset)
        is_watched = False
    else:
        await request.user.watchlist.aadd(asset)
        is_watched = True

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

    peers_before = await sync_to_async(sync_peers)(asset)
    if not peers_before and not await asset.peers.aexists():
        # Still syncing in another request — tell HTMX to retry
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

    peer_data = []
    for peer in peers:
        change_pct = pct_change(peer.latest_close, peer.prev_close)
        peer_data.append(
            {
                "asset": peer,
                "latest_close": peer.latest_close,
                "price_change_pct": round(change_pct, 2)
                if change_pct is not None
                else None,
            }
        )

    if peer_data:
        await cache.aset(cache_key, peer_data, PEERS_CACHE_TTL)

    return render(request, "core/partials/asset_peers.html", {"peers": peer_data})


async def asset_community(request, ticker):
    """Partial: reddit + HN + news articles. Fires background news sync."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/asset_community.html", {})

    sync_asset_news_async(asset)

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


@cache_page(PRICES_CACHE_TTL)
async def asset_prices(request, ticker):
    """Partial: recent prices table with daily change."""
    ticker = ticker.upper()
    asset = await Asset.objects.filter(ticker=ticker).afirst()
    if not asset:
        return render(request, "core/partials/asset_prices.html", {})

    cutoff = timezone.now() - timedelta(days=ASSET_DETAIL_RECENT_PRICES_DAYS)
    recent_prices_qs = [
        p
        async for p in asset.prices.filter(timestamp__gte=cutoff)
        .annotate(date=TruncDate("timestamp"))
        .order_by("-date", "-timestamp")
        .distinct("date")
    ]
    recent_prices = []
    for i, p in enumerate(recent_prices_qs):
        prev = recent_prices_qs[i + 1] if i + 1 < len(recent_prices_qs) else None
        if prev and prev.close:
            p.daily_change = float(p.close - prev.close)
            p.daily_change_pct = round(
                float((p.close - prev.close) / prev.close * 100), 2
            )
        else:
            p.daily_change = None
            p.daily_change_pct = None
        recent_prices.append(p)
    days_with_change = [p for p in recent_prices if p.daily_change is not None]
    positive_days = sum(1 for p in days_with_change if p.daily_change >= 0)
    positive_day_pct = (
        round(positive_days / len(days_with_change) * 100) if days_with_change else None
    )

    return render(
        request,
        "core/partials/asset_prices.html",
        {
            "recent_prices": recent_prices,
            "positive_day_pct": positive_day_pct,
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

    return render(request, "core/partials/search_results.html", {"results": results})


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
