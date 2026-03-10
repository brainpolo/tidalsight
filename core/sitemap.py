from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from scraper.models import Asset


class StaticSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return ["core:home", "core:strategy", "core:rankings"]

    def location(self, item):
        return reverse(item)


class AssetSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Asset.objects.filter(is_active=True).order_by("ticker")

    def lastmod(self, obj):
        return obj.report_card_updated_at

    def location(self, obj):
        return reverse("core:asset_detail", kwargs={"ticker": obj.ticker})
