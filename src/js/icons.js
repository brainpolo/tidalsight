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
    Activity,
    ArrowUpRight,
    Banknote,
    BookOpen,
    ChevronDown,
    ChevronUp,
    Coins,
    Compass,
    Download,
    Eye,
    ExternalLink,
    Gauge,
    Landmark,
    LogOut,
    Percent,
    Scale,
    Scissors,
    Search,
    Settings,
    Shield,
    Star,
    Target,
    TrendingDown,
    TrendingUp,
    User,
    Wallet,
} from "lucide";

const icons = {
    Activity,
    ArrowUpRight,
    Banknote,
    BookOpen,
    ChevronDown,
    ChevronUp,
    Coins,
    Compass,
    Download,
    Eye,
    ExternalLink,
    Gauge,
    Landmark,
    LogOut,
    Percent,
    Scale,
    Scissors,
    Search,
    Settings,
    Shield,
    Star,
    Target,
    TrendingDown,
    TrendingUp,
    User,
    Wallet,
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
