import asyncio
import json
import logging

from agents import RunConfig, Runner

from analyst.agents.provider import get_model_provider
from analyst.agents.revision_agent import REVISION_AGENTS
from analyst.app_behaviour import MAX_AGENT_TURNS
from analyst.grounding import agent_grounding, compute_label
from analyst.utils import asset_label
from scraper.models import Asset

logger = logging.getLogger(__name__)

# Meta fields to strip from the base assessment before sending to revision agent
_META_FIELDS = {"source_hash", "generated_at", "is_revised"}


def _build_revision_prompt(
    section_name: str,
    base_assessment: dict,
    user_note: str,
    price_target: float | None,
    asset: Asset,
) -> str:
    base_clean = {k: v for k, v in base_assessment.items() if k not in _META_FIELDS}

    lines = [
        f"# Revision Request: {section_name.replace('_', ' ').title()}",
        f"**Asset**: {asset_label(asset)}\n",
        f"## Base Assessment\n```json\n{json.dumps(base_clean, indent=2)}\n```\n",
    ]
    if user_note:
        lines.append(f"## Investor's Notes\n{user_note}\n")
    if price_target is not None:
        lines.append(f"## Investor's Price Target: ${price_target:,.2f}\n")
    lines.append(
        "Revise the assessment above based on the investor context. "
        "Output the same schema with any adjustments."
    )
    return "\n".join(lines)


def revise_assessment(
    section_name: str,
    base_assessment: dict,
    user_note: str,
    price_target: float | None,
    asset: Asset,
) -> dict:
    """Run lightweight revision agent to adjust a base assessment with user context."""
    agent = REVISION_AGENTS[section_name]

    prompt = _build_revision_prompt(
        section_name, base_assessment, user_note, price_target, asset
    )

    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    data = result.final_output.model_dump()
    data["label"] = compute_label(section_name, data["score"])
    return data
