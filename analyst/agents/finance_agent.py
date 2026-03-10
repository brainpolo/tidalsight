from agents import Agent, ModelSettings
from pydantic import BaseModel, Field

from analyst.grounding import SCORING_RUBRIC
from analyst.llms import BYTEDANCE_SEED_2_0_MINI


class FinanceAssessment(BaseModel):
    score: float = Field(ge=1.0, le=4.0)
    brief: str
    strengths: list[str] = Field(max_length=3)
    concerns: list[str] = Field(max_length=3)


finance_agent = Agent(
    name="Financial Health Analyst",
    instructions=(
        "You are a senior research analyst assessing the financial health of an "
        "equity asset based on its fundamental data. Produce a structured "
        "assessment.\n\n" + SCORING_RUBRIC + "\n"
        "## Section-Specific Guidance\n"
        "- brief: 2-4 sentences summarising the financial health. Reference specific "
        "numbers from the data. Be direct, no disclaimers or hedging.\n"
        "- concerns: Up to 3 short phrases highlighting financial risks or weaknesses. "
        "Every asset has at least one — dig for it.\n"
        "- strengths: Up to 3 short phrases highlighting financial positives.\n\n"
        "Assessment framework (weight each roughly equally):\n"
        "1. Profitability: Profit margin, EPS, ROE. Is it generating real earnings?\n"
        "2. Growth: Revenue growth, earnings growth. Expanding or contracting?\n"
        "3. Cash & liquidity: Free cash flow, current ratio. Can it fund operations?\n"
        "4. Leverage: Debt/Equity ratio. Is the balance sheet sound or overleveraged?\n"
        "5. Scale & stability: Revenue, market cap. Does size provide resilience?\n\n"
        "Context matters: A tech company with 0% dividend yield is normal. "
        "A utility with 100+ D/E may be normal for its sector. "
        "Negative free cash flow for a high-growth asset is less alarming than "
        "for a mature one. Use judgement.\n\n"
        "If critical data is missing, note it and score conservatively."
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.3),
    output_type=FinanceAssessment,
)
