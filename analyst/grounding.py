"""Common grounding context appended to every agent prompt.

Appended (not prepended) so the task-specific data comes first — this
maximises KV-cache reuse when the same grounding block appears across
calls with different lead-in content.
"""

from django.utils import timezone


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
