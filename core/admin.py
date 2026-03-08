from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from core.models import User, UserAsset


class UserAssetInline(admin.TabularInline):
    model = UserAsset
    extra = 0
    autocomplete_fields = ("asset",)


@admin.register(User)
class TidalUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
    fieldsets = (
        *UserAdmin.fieldsets,
        ("TidalSight", {"fields": ("currency", "timezone")}),
    )
    inlines = (UserAssetInline,)
