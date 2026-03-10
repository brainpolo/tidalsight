"""Common grounding context appended to every agent prompt.

Appended (not prepended) so the task-specific data comes first — this
maximises KV-cache reuse when the same grounding block appears across
calls with different lead-in content.
"""

from django.utils import timezone

# Shared rubric for all 6 scoring agents (included in agent instructions)
SCORING_RUBRIC = (
    "## Scoring Scale (1.0 – 4.0)\n"
    "All scores use a strict 1–4 scale with up to one decimal place.\n\n"
    "- 1.0–1.4: Critical — severe deficiency, clear red flag\n"
    "- 1.5–1.9: Weak — material concerns, below average\n"
    "- 2.0–2.4: Below average — some issues, leans negative\n"
    "- 2.5–2.9: Average — passable but unremarkable\n"
    "- 3.0–3.4: Good — solid, above average\n"
    "- 3.5–3.9: Strong — meaningfully above peers, rare\n"
    "- 4.0: Exceptional — top-decile, almost never warranted\n\n"
    "## Score Calibration (MANDATORY)\n"
    "Score like a ruthless skeptic — not a bear, not a bull, but someone who "
    "demands hard evidence for every point above or below the median. The median asset scores approximately 2.5. "
    "Most land between 2.0 and 3.0. Scores above 3.0 demand extraordinary "
    "evidence. Scores above 3.5 are top-decile — one or two per sector at most.\n\n"
    "Name recognition, market cap, popularity, and past performance are "
    "IRRELEVANT to the score. A trillion-dollar asset can score 1.5 on "
    "financial health if leverage is dangerous. A household name can score "
    "2.0 on product if competitors are closing the gap. A market leader can "
    "score low on risk during a regulatory crackdown. No asset — regardless "
    "of size, fame, or history — is above a low score.\n\n"
    "Every asset has real, material weaknesses. If your score is above 3.0, "
    "ask: is the evidence so strong that a ruthless skeptic would concede "
    "this dimension has no serious counterargument? If not, the score is too high. "
    "A report where every section is 3.0+ is a failure of analysis.\n"
)


# Deterministic label mapping per section — computed from score, never LLM-generated.
# Each list is (upper_bound_exclusive, label).
SECTION_LABELS: dict[str, list[tuple[float, str]]] = {
    "finance": [
        (1.5, "Critical"),
        (2.0, "Weak"),
        (3.0, "Fair"),
        (3.5, "Strong"),
        (999, "Excellent"),
    ],
    "sentiment": [
        (1.5, "Very Bearish"),
        (2.0, "Bearish"),
        (3.0, "Neutral"),
        (3.5, "Bullish"),
        (999, "Very Bullish"),
    ],
    "risk": [
        (1.5, "Critical"),
        (2.0, "Elevated"),
        (3.0, "Moderate"),
        (3.5, "Low"),
        (999, "Minimal"),
    ],
    "valuation": [
        (1.5, "Deeply Overvalued"),
        (2.0, "Overvalued"),
        (3.0, "Fair"),
        (3.5, "Undervalued"),
        (999, "Deeply Undervalued"),
    ],
    "product": [
        (1.5, "Absent"),
        (2.0, "Weak"),
        (3.0, "Developing"),
        (3.5, "Strong"),
        (999, "Exceptional"),
    ],
    "people": [
        (1.5, "Weak"),
        (2.0, "Concerning"),
        (3.0, "Capable"),
        (3.5, "Strong"),
        (999, "Exceptional"),
    ],
}


def compute_label(section: str, score: float) -> str:
    """Map a section score to its deterministic label."""
    for threshold, label in SECTION_LABELS[section]:
        if score < threshold:
            return label
    return SECTION_LABELS[section][-1][1]


def agent_grounding() -> str:
    today = timezone.now().date()
    return (
        "\n\n---\n"
        "## Grounding Context\n"
        f"- Current date: {today.strftime('%B %d, %Y')}\n"
        "\n"
        "## Response Standards\n"
        "- Be direct and specific. No disclaimers, no hedging, no filler.\n"
        "- Reference concrete numbers, names, and facts — not vague generalities.\n"
        "- Write in present tense unless referring to historical events.\n"
        "- Never say 'As of [year]' — state facts directly.\n"
        "- Professional tone: institutional research quality, not retail/blog style.\n"
        "- If you lack information, say so briefly rather than fabricating.\n"
    )
