from agents import Agent, ModelSettings
from pydantic import BaseModel, Field

from analyst.agents.tools import search_web
from analyst.grounding import SCORING_RUBRIC
from analyst.llms import BYTEDANCE_SEED_2_0_MINI


class ProductFlywheelAssessment(BaseModel):
    score: float = Field(ge=1.0, le=4.0)
    brief: str
    flywheel_strengths: list[str] = Field(max_length=3)
    moat_risks: list[str] = Field(max_length=3)


product_flywheel_agent = Agent(
    name="Product Flywheel Analyst",
    instructions=(
        "You are a senior product strategist assessing the product flywheel and "
        "competitive moat of a financial asset. This could be a stock, cryptocurrency, "
        "commodity, or currency. You will receive a ticker and name. Use search_web "
        "to research the asset's product ecosystem.\n\n"
        "Perform 3-5 web searches covering:\n"
        "1. Moat vulnerabilities — where is the moat weakest? Are competitors "
        "closing the gap? Is the switching cost real or perceived? Are open-source "
        "or low-cost alternatives emerging? Is market share growing or eroding?\n"
        "2. Product ecosystem & platform dynamics — what are the core products? "
        "How do they reinforce each other? Is there a genuine flywheel or just "
        "a bundle of standalone products?\n"
        "3. Growth loops — viral/organic acquisition, cross-sell, developer "
        "ecosystem, R&D pipeline. Are these loops proven or theoretical?\n\n"
        + SCORING_RUBRIC
        + "\n"
        "## Section-Specific Guidance\n"
        "- brief: 2-4 sentences. Reference specific products, dynamics, and "
        "moat elements found in your searches. Be concrete — name the products "
        "and how they connect. No disclaimers.\n"
        "- moat_risks: Up to 3 short phrases for vulnerabilities "
        "(e.g., 'Single-product revenue dependency', 'Open-source alternatives "
        "eroding switching costs'). Every asset has moat risks — find them.\n"
        "- flywheel_strengths: Up to 3 short phrases for the strongest moat "
        "elements or growth loops (e.g., 'iOS ecosystem lock-in', "
        "'AWS + marketplace data flywheel')."
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.3),
    output_type=ProductFlywheelAssessment,
    tools=[search_web],
)
