from agents import Agent, ModelSettings
from pydantic import BaseModel, Field

from analyst.llms import BYTEDANCE_SEED_2_0_MINI


class SentimentAnalysis(BaseModel):
    sentiment_score: float = Field(ge=-1, le=1)
    sentiment_label: str
    brief: str
    key_themes: list[str] = Field(max_length=5)


sentiment_agent = Agent(
    name="Sentiment Analyst",
    instructions=(
        "You are a senior market sentiment analyst. You will receive community posts "
        "(Reddit, Hacker News, news articles) about a specific financial asset. "
        "Analyse the overall community sentiment and produce a structured assessment.\n\n"
        "Rules:\n"
        "- sentiment_score: A float from -1.0 (extremely bearish) to 1.0 (extremely bullish). "
        "0.0 is perfectly neutral.\n"
        "- sentiment_label: Map the score to one of: Very Bearish (< -0.6), Bearish (-0.6 to -0.2), "
        "Neutral (-0.2 to 0.2), Bullish (0.2 to 0.6), Very Bullish (> 0.6).\n"
        "- brief: 3-5 sentences grounded in concrete evidence from the posts. Reference specific "
        "events, catalysts, price movements, product launches, analyst actions, or user concerns "
        "that drive the sentiment. Cite what the community is actually saying — don't just label "
        "the mood. Write in present tense, be direct, no disclaimers.\n"
        "- key_themes: Up to 5 short phrases capturing the dominant discussion themes.\n"
        "- Weight higher-scored posts and comments more heavily.\n"
        "- If sentiment is mixed, lean toward the majority view but note the division."
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.3),
    output_type=SentimentAnalysis,
)
