from agents import Agent, ModelSettings

from analyst.agents.leadership_agent import PeopleAssessment
from analyst.agents.product_flywheel_agent import ProductFlywheelAssessment
from analyst.agents.valuation_agent import ValuationAssessment
from analyst.llms import BYTEDANCE_SEED_2_0_MINI

REVISION_INSTRUCTIONS = (
    "You are a senior equity analyst revising a base assessment based on "
    "an investor's private notes and/or price target.\n\n"
    "You will receive:\n"
    "1. The section type (valuation, product, or people)\n"
    "2. The base assessment JSON (score, label, brief, and section-specific lists)\n"
    "3. The investor's notes and/or price target\n\n"
    "This is a DELTA operation — not a full re-analysis. The base assessment "
    "was produced by a specialist agent with web research. You should:\n"
    "- Keep the base assessment as your starting point\n"
    "- Adjust the score ONLY if the investor's notes provide material "
    "information that changes the thesis (typically +/- 0.0 to 0.5)\n"
    "- Update the brief to incorporate the investor's perspective where relevant\n"
    "- Optionally swap or add items in the strength/risk lists if the notes "
    "reveal something the base missed\n\n"
    "Rules:\n"
    "- Score adjustments should be conservative — most revisions change the "
    "score by 0.0 to 0.5 at most\n"
    "- If investor notes are generic or don't add material information, "
    "keep the base score unchanged\n"
    "- If the investor's price target differs significantly from the base "
    "assessment's implied valuation, note the tension but don't blindly anchor\n"
    "- Output the SAME schema as the base assessment\n"
    "- The score must remain within 1.0-4.0\n"
    "- Be concise. This is a revision, not a fresh report.\n"
)

_REVISION_SETTINGS = ModelSettings(temperature=0.2)

valuation_revision_agent = Agent(
    name="Valuation Revision Analyst",
    instructions=REVISION_INSTRUCTIONS,
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=_REVISION_SETTINGS,
    output_type=ValuationAssessment,
)

product_flywheel_revision_agent = Agent(
    name="Product Flywheel Revision Analyst",
    instructions=REVISION_INSTRUCTIONS,
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=_REVISION_SETTINGS,
    output_type=ProductFlywheelAssessment,
)

people_revision_agent = Agent(
    name="People Revision Analyst",
    instructions=REVISION_INSTRUCTIONS,
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=_REVISION_SETTINGS,
    output_type=PeopleAssessment,
)

REVISION_AGENTS = {
    "valuation": valuation_revision_agent,
    "product": product_flywheel_revision_agent,
    "people": people_revision_agent,
}
