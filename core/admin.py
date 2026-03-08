from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from core.models import User


@admin.register(User)
class TidalUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
    fieldsets = (
        *UserAdmin.fieldsets,
        ("TidalSight", {"fields": ("watchlist", "currency", "timezone")}),
    )
    filter_horizontal = ("watchlist",)
