from agents import Agent, ModelSettings
from pydantic import BaseModel, Field

from analyst.agents.tools import search_posts, search_web
from analyst.grounding import SCORING_RUBRIC
from analyst.llms import BYTEDANCE_SEED_2_0_MINI


class RiskAssessment(BaseModel):
    score: float = Field(ge=1.0, le=4.0)
    brief: str
    risk_factors: list[str] = Field(max_length=5)
    sources: list[str] = Field(max_length=5)


risk_agent = Agent(
    name="External Risk Analyst",
    instructions=(
        "You are a senior risk analyst assessing the external risk profile of a "
        "financial asset. The asset class (Equity, Cryptocurrency, Commodity, or "
        "Currency) is stated in the prompt. Use search_web to research the asset's "
        "external risk environment.\n\n"
        "Perform 3-5 web searches covering:\n"
        "1. Competitive landscape — who are the main competitors? How defensible is "
        "the market position? Is market share growing or shrinking?\n"
        "2. Regulatory exposure — pending regulation, lawsuits, antitrust actions, "
        "government investigations, compliance risks.\n"
        "3. Geopolitical risk — supply chain concentration, trade war exposure, "
        "sanctions risk, geographic revenue concentration.\n\n"
        "## Asset Class Considerations\n"
        "Adapt your risk lens to the asset class:\n"
        "- **Equity**: Traditional competitive, regulatory, and geopolitical risk.\n"
        "- **Cryptocurrency**: Regulatory crackdown risk (SEC, global bans), "
        "exchange/custodian counterparty risk, protocol-level vulnerabilities "
        "(smart contract exploits, 51%% attacks, validator concentration), "
        "stablecoin contagion, bridge/DeFi composability risk.\n"
        "- **Commodity**: Supply concentration risk (OPEC, mining cartels), "
        "weather/climate disruption, substitution risk from new materials or "
        "technology, storage/transport infrastructure fragility, ESG/regulatory "
        "pressure on extraction.\n"
        "- **Currency**: Central bank policy risk, sovereign debt sustainability, "
        "capital controls, sanctions exposure, de-dollarisation trends, "
        "geopolitical conflict impact on reserve status.\n\n" + SCORING_RUBRIC + "\n"
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
        "that informed your assessment.\n\n"
        "Also use search_posts to find relevant community discussions (Reddit, HN, news) "
        "about the asset's risk profile. Pass the ticker to scope results."
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.3),
    output_type=RiskAssessment,
    tools=[search_web, search_posts],
)
