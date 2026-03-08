from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import path, reverse_lazy

from core import views
from core.forms import TidalPasswordResetForm, TidalSetPasswordForm

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("strategy/", views.strategy, name="strategy"),
    path("watchlist/", views.home_watchlist, name="home_watchlist"),
    path("search/", views.asset_search, name="asset_search"),
    path("assets/<str:ticker>/", views.asset_detail, name="asset_detail"),
    path(
        "assets/<str:ticker>/watchlist/",
        views.toggle_watchlist,
        name="toggle_watchlist",
    ),
    path("assets/<str:ticker>/header/", views.asset_header, name="asset_header"),
    path(
        "assets/<str:ticker>/fundamentals/",
        views.asset_fundamentals,
        name="asset_fundamentals",
    ),
    path("assets/<str:ticker>/peers/", views.asset_peers, name="asset_peers"),
    path(
        "assets/<str:ticker>/sentiment/",
        views.asset_sentiment,
        name="asset_sentiment",
    ),
    path(
        "assets/<str:ticker>/community/", views.asset_community, name="asset_community"
    ),
    path("assets/<str:ticker>/prices/", views.asset_prices, name="asset_prices"),
    path(
        "assets/<str:ticker>/chart-data/",
        views.asset_chart_data,
        name="asset_chart_data",
    ),
    path(
        "assets/<str:ticker>/price-target/",
        views.set_price_target,
        name="set_price_target",
    ),
    path(
        "assets/<str:ticker>/note/",
        views.save_note,
        name="save_note",
    ),
    path("market-digest/", views.market_digest, name="market_digest"),
    path("trending/", views.trending_banner, name="trending_banner"),
    # Auth
    path("sign-up/", views.sign_up, name="sign_up"),
    path("sign-in/", views.sign_in, name="sign_in"),
    path("sign-out/", views.sign_out, name="sign_out"),
    path("profile/", views.profile, name="profile"),
    # Password reset
    path(
        "password-reset/",
        PasswordResetView.as_view(
            template_name="core/auth/password_reset.html",
            email_template_name="core/auth/password_reset_email.txt",
            form_class=TidalPasswordResetForm,
            success_url=reverse_lazy("core:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        PasswordResetDoneView.as_view(
            template_name="core/auth/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="core/auth/password_reset_confirm.html",
            form_class=TidalSetPasswordForm,
            success_url=reverse_lazy("core:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        PasswordResetCompleteView.as_view(
            template_name="core/auth/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
