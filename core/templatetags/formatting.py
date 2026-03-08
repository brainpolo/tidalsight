from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django import template

register = template.Library()

SUFFIXES = [
    (Decimal("1e12"), "T"),
    (Decimal("1e9"), "B"),
    (Decimal("1e6"), "M"),
    (Decimal("1e3"), "K"),
]


@register.filter
def abbreviate(value):
    if value is None:
        return ""
    try:
        value = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return value

    negative = value < 0
    value = abs(value)

    for threshold, suffix in SUFFIXES:
        if value >= threshold:
            abbreviated = value / threshold
            formatted = f"{abbreviated:,.2f}".rstrip("0").rstrip(".")
            result = f"${formatted}{suffix}"
            return f"-{result}" if negative else result

    result = f"${value:,.2f}"
    return f"-{result}" if negative else result


@register.filter
def domain(url):
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return host.removeprefix("www.")
