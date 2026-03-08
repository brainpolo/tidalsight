from django.contrib.auth.models import AbstractUser
from django.db import models

from core.constants import CURRENCY_MAX_LENGTH, TIMEZONE_MAX_LENGTH, Currency, Timezone


class User(AbstractUser):
    watchlist = models.ManyToManyField("scraper.Asset", blank=True, related_name="watchers")
    currency = models.CharField(max_length=CURRENCY_MAX_LENGTH, choices=Currency.choices, default=Currency.USD)
    timezone = models.CharField(max_length=TIMEZONE_MAX_LENGTH, choices=Timezone.choices, default=Timezone.UTC)
