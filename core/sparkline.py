from django.utils.safestring import mark_safe


def build_sparkline_svg(closes: list[float], width: int = 80, height: int = 24) -> str:
    """Generate an inline SVG sparkline from a list of close prices."""
    if len(closes) < 2:
        return ""

    min_val = min(closes)
    max_val = max(closes)
    val_range = max_val - min_val or 1

    padding = 1
    chart_h = height - 2 * padding

    points = []
    for i, close in enumerate(closes):
        x = round(i / (len(closes) - 1) * width, 2)
        y = round(padding + chart_h - ((close - min_val) / val_range) * chart_h, 2)
        points.append(f"{x},{y}")

    is_up = closes[-1] >= closes[0]
    color = "#22c55e" if is_up else "#ef4444"
    path_d = "M" + "L".join(points)

    return mark_safe(
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'fill="none" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{path_d}" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )
