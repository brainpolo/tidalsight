from agents import Agent, ModelSettings
from pydantic import BaseModel, Field

from analyst.agents.tools import search_web
from analyst.grounding import SCORING_RUBRIC
from analyst.llms import BYTEDANCE_SEED_2_0_MINI


class ExternalRiskAssessment(BaseModel):
    score: float = Field(ge=1.0, le=4.0)
    brief: str
    risk_factors: list[str] = Field(max_length=5)
    sources: list[str] = Field(max_length=5)


external_risk_agent = Agent(
    name="External Risk Analyst",
    instructions=(
        "You are a senior risk analyst assessing the external risk profile of a "
        "financial asset. This could be a stock, cryptocurrency, commodity, or currency. "
        "You will receive a ticker and name. Use search_web to research the asset's "
        "external risk environment.\n\n"
        "Perform 3-5 web searches covering:\n"
        "1. Competitive landscape — who are the main competitors? How defensible is "
        "the market position? Is market share growing or shrinking?\n"
        "2. Regulatory exposure — pending regulation, lawsuits, antitrust actions, "
        "government investigations, compliance risks.\n"
        "3. Geopolitical risk — supply chain concentration, trade war exposure, "
        "sanctions risk, geographic revenue concentration.\n\n"
        + SCORING_RUBRIC
        + "\n"
        "**Important: HIGHER scores mean LESS risk (safer).** A score of 1 means "
        "severe existential risk; a score of 4 means minimal risk with a dominant "
        "defensible position.\n\n"
        "## Section-Specific Guidance\n"
        "- brief: 2-4 sentences referencing specific findings from your searches. "
        "Cite concrete risks or strengths. Be direct, no disclaimers.\n"
        "- risk_factors: Up to 5 short phrases for the most material external risks. "
        "Every asset faces real external threats — no asset operates in a risk-free "
        "environment. Dig for them.\n"
        "- sources: Up to 5 source titles or descriptions from your search results "
        "that informed your assessment."
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.3),
    output_type=ExternalRiskAssessment,
    tools=[search_web],
)
