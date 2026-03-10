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

    # Approximate path length for stroke-dasharray draw-in animation
    path_len = 0.0
    coords = [(float(p.split(",")[0]), float(p.split(",")[1])) for p in points]
    for j in range(1, len(coords)):
        dx = coords[j][0] - coords[j - 1][0]
        dy = coords[j][1] - coords[j - 1][1]
        path_len += (dx * dx + dy * dy) ** 0.5
    dash = round(path_len, 1)

    return mark_safe(
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'fill="none" xmlns="http://www.w3.org/2000/svg" class="sparkline">'
        f'<path d="{path_d}" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="stroke-dasharray:{dash};stroke-dashoffset:{dash}"/>'
        f"</svg>"
    )
