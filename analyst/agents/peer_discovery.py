from agents import Agent, ModelSettings
from pydantic import BaseModel

from analyst.agents.tools import search_web, validate_ticker
from analyst.llms import BYTEDANCE_SEED_2_0_MINI


class PeerDiscovery(BaseModel):
    tickers: list[str]


peer_discovery_agent = Agent(
    name="Peer Discovery",
    instructions=(
        "You are a financial analyst. Given an asset, return 5-8 direct competitor/peer "
        "stock tickers that trade on major US exchanges.\n\n"
        "Rules:\n"
        "- Use search_web to research the company's competitors and industry peers.\n"
        "- Only return publicly traded equities. No ETFs, no indices, no mutual funds.\n"
        "- Return tickers in uppercase without $ prefix.\n"
        "- Before including any ticker, call validate_ticker to confirm it is real.\n"
        "- Do not include the asset itself in the list.\n"
        "- Focus on companies in the same industry/sector with similar business models."
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.2),
    output_type=PeerDiscovery,
    tools=[search_web, validate_ticker],
)
