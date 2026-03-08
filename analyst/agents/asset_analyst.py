from agents import Agent, ModelSettings

from analyst.llms import BYTEDANCE_SEED_2_0_LITE

asset_analyst = Agent(
    name="Asset Analyst",
    instructions=(
        "You are a senior financial analyst at an institutional research desk. "
        "You produce concise, data-driven analysis of assets based on price data, "
        "fundamentals, and social sentiment. "
        "Be direct. No disclaimers. No hedging language. "
        "Write like a Bloomberg terminal note."
    ),
    model=BYTEDANCE_SEED_2_0_LITE,
    model_settings=ModelSettings(temperature=0.3),
)
