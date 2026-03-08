from django.contrib.auth.models import AbstractUser
from django.db import models

from core.constants import CURRENCY_MAX_LENGTH, TIMEZONE_MAX_LENGTH, Currency, Timezone


class User(AbstractUser):
    currency = models.CharField(
        max_length=CURRENCY_MAX_LENGTH, choices=Currency.choices, default=Currency.USD
    )
    timezone = models.CharField(
        max_length=TIMEZONE_MAX_LENGTH, choices=Timezone.choices, default=Timezone.UTC
    )


class UserAsset(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_assets")
    asset = models.ForeignKey(
        "scraper.Asset", on_delete=models.CASCADE, related_name="user_assets"
    )
    in_watchlist = models.BooleanField(default=True)
    note = models.TextField(blank=True, default="")
    price_target = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "asset")

    def __str__(self):
        return f"{self.user.username} → {self.asset.ticker}"
