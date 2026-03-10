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
    BarChart3,
    Banknote,
    BookOpen,
    ChevronDown,
    ChevronUp,
    ClipboardCheck,
    Coins,
    Compass,
    Download,
    Droplets,
    Eye,
    ExternalLink,
    Flame,
    Gauge,
    HeartPulse,
    Landmark,
    LogOut,
    MessageCircle,
    PenLine,
    Percent,
    RefreshCw,
    Rocket,
    Scale,
    Scissors,
    Search,
    Settings,
    Shield,
    ShieldAlert,
    ShieldCheck,
    Star,
    Target,
    TrendingDown,
    Trophy,
    TrendingUp,
    User,
    Users,
    Wallet,
} from "lucide";

const icons = {
    Activity,
    ArrowUpRight,
    BarChart3,
    Banknote,
    BookOpen,
    ChevronDown,
    ChevronUp,
    ClipboardCheck,
    Coins,
    Compass,
    Download,
    Droplets,
    Eye,
    ExternalLink,
    Flame,
    Gauge,
    HeartPulse,
    Landmark,
    LogOut,
    MessageCircle,
    PenLine,
    Percent,
    RefreshCw,
    Rocket,
    Scale,
    Scissors,
    Search,
    Settings,
    Shield,
    ShieldAlert,
    ShieldCheck,
    Star,
    Target,
    TrendingDown,
    Trophy,
    TrendingUp,
    User,
    Users,
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
