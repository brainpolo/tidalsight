import json
from pathlib import Path

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()

_manifest: dict[str, dict] | None = None


def _load_manifest() -> dict[str, dict]:
    global _manifest
    if _manifest is None:
        manifest_path = (
            Path(settings.STATICFILES_DIRS[0]) / "dist" / ".vite" / "manifest.json"
        )
        with open(manifest_path) as f:
            _manifest = json.load(f)
    return _manifest


@register.simple_tag
def vite_asset(entry: str) -> str:
    """Render <script> and <link> tags for a Vite production build entry."""
    manifest = _load_manifest()
    chunk = manifest[entry]
    static_url = settings.STATIC_URL + "dist/"
    tags = []

    if "css" in chunk:
        for css_file in chunk["css"]:
            tags.append(f'<link rel="stylesheet" href="{static_url}{css_file}">')

    tags.append(f'<script type="module" src="{static_url}{chunk["file"]}"></script>')
    return mark_safe("\n    ".join(tags))
