/**
 * Lucide icon registry.
 *
 * Only icons imported here are included in the bundle.
 * Add new icons: import { IconName } from "lucide";
 * then add to the `icons` object below.
 *
 * Usage in templates: <i data-lucide="icon-name" class="size-4"></i>
 */
import { createIcons } from "lucide";

// ── Icon registry (tree-shaken) ──────────────────────────────────────
import {
    ArrowUpRight,
    ChevronDown,
    Compass,
    Download,
    ExternalLink,
    LogOut,
    Search,
    Settings,
    Shield,
    Star,
    TrendingDown,
    TrendingUp,
    User,
} from "lucide";

const icons = {
    ArrowUpRight,
    ChevronDown,
    Compass,
    Download,
    ExternalLink,
    LogOut,
    Search,
    Settings,
    Shield,
    Star,
    TrendingDown,
    TrendingUp,
    User,
};

// ── Initial render ───────────────────────────────────────────────────
createIcons({ icons });

// ── Re-render on HTMX swaps ─────────────────────────────────────────
let pending = false;
document.body.addEventListener("htmx:afterSettle", () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
        createIcons({ icons });
        pending = false;
    });
});
