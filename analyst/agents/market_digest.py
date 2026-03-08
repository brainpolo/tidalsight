from pydantic import BaseModel
from agents import Agent, ModelSettings

from analyst.agents.tools import validate_ticker
from analyst.llms import BYTEDANCE_SEED_2_0_LITE


class MarketDigest(BaseModel):
    headline: str
    themes: list[str]
    sentiment: str
    sentiment_reason: str


market_digest_agent = Agent(
    name="Market Digest",
    instructions=(
        "You are a senior market strategist writing a daily briefing for institutional clients. "
        "You will receive a list of recent social media posts discussing financial markets. "
        "Synthesise them into a concise market digest.\n\n"
        "Rules:\n"
        "- headline: One punchy sentence capturing the dominant market theme right now.\n"
        "- themes: 3-5 bullet points on the most discussed topics, tickers, or sectors. Each one sentence.\n"
        "- sentiment: Exactly one of: Bullish, Bearish, or Mixed.\n"
        "- sentiment_reason: One sentence explaining why.\n"
        "- Write in present tense.\n"
        "- No disclaimers, no hedging, no filler.\n"
        "- Reference specific tickers with $ prefix when mentioned.\n"
        "- Before referencing any ticker, call validate_ticker to confirm it is real. Never include unvalidated tickers."
    ),
    model=BYTEDANCE_SEED_2_0_LITE,
    model_settings=ModelSettings(temperature=0.4),
    output_type=MarketDigest,
    tools=[validate_ticker],
)
