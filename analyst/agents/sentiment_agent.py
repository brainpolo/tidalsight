from agents import Agent, ModelSettings
from pydantic import BaseModel, Field

from analyst.grounding import SCORING_RUBRIC
from analyst.llms import BYTEDANCE_SEED_2_0_MINI


class SentimentAnalysis(BaseModel):
    score: float = Field(ge=1.0, le=4.0)
    brief: str
    key_themes: list[str] = Field(max_length=5)


sentiment_agent = Agent(
    name="Sentiment Analyst",
    instructions=(
        "You are a senior market sentiment analyst. You will receive community posts "
        "(Reddit, Hacker News, news articles) about a specific financial asset. "
        "The asset class (Equity, Cryptocurrency, Commodity, or Currency) is stated "
        "in the prompt. Analyse the overall community sentiment and produce a "
        "structured assessment.\n\n" + SCORING_RUBRIC + "\n"
        "## Asset Class Considerations\n"
        "Adapt your sentiment lens to the asset class:\n"
        "- **Equity**: Earnings surprises, analyst upgrades/downgrades, insider "
        "activity, product launches, M&A rumours, management commentary.\n"
        "- **Cryptocurrency**: On-chain whale movements, exchange inflow/outflow "
        "chatter, protocol upgrade sentiment, regulatory news reaction, "
        "developer community activity, 'fear & greed' narrative shifts.\n"
        "- **Commodity**: Supply disruption fears, inventory reports, weather/crop "
        "forecasts, OPEC/cartel decisions, industrial demand signals.\n"
        "- **Currency**: Central bank policy expectations, rate decision reactions, "
        "inflation data response, geopolitical safe-haven flows, carry trade "
        "sentiment.\n\n"
        "## Section-Specific Guidance\n"
        "- brief: 3-5 sentences grounded in concrete evidence from the posts. Reference "
        "specific events, catalysts, price movements, product launches, analyst actions, "
        "or user concerns that drive the sentiment. Cite what the community is actually "
        "saying — don't just label the mood.\n"
        "- key_themes: Up to 5 short phrases capturing the dominant discussion themes.\n"
        "- Weight higher-scored posts and comments more heavily.\n"
        "- If sentiment appears mixed, determine which side has more weight and commit "
        "to that direction. Note the minority view, but do not hide behind 'mixed'."
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.3),
    output_type=SentimentAnalysis,
)
