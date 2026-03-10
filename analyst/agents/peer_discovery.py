from agents import Agent, ModelSettings
from pydantic import BaseModel

from analyst.agents.tools import search_web, validate_ticker
from analyst.llms import BYTEDANCE_SEED_2_0_MINI


class PeerDiscovery(BaseModel):
    tickers: list[str]


peer_discovery_agent = Agent(
    name="Peer Discovery",
    instructions=(
        "You are a financial analyst. Given an asset, return 5-8 direct "
        "competitor/peer tickers. The asset class (Equity, Cryptocurrency, "
        "Commodity, or Currency) is stated in the prompt.\n\n"
        "Rules:\n"
        "- Use search_web to research the asset's competitors and peers.\n"
        "- Return tickers in uppercase without $ prefix.\n"
        "- Before including any ticker, call validate_ticker to confirm it is real.\n"
        "- Do not include the asset itself in the list.\n\n"
        "## Asset Class Peer Selection\n"
        "- **Equity**: Direct industry competitors with similar business models. "
        "Only publicly traded equities — no ETFs, indices, or mutual funds.\n"
        "- **Cryptocurrency**: Tokens/coins in the same category (e.g., L1 chains, "
        "DeFi protocols, stablecoins, L2 scaling). Use Yahoo Finance crypto "
        "tickers (e.g., ETH-USD, SOL-USD, ADA-USD).\n"
        "- **Commodity**: Related commodities or substitutes (e.g., gold peers: "
        "silver, platinum, palladium; crude oil peers: natural gas, Brent). "
        "Use Yahoo Finance commodity tickers.\n"
        "- **Currency**: Major currency pairs or economically linked currencies. "
        "Use Yahoo Finance forex tickers (e.g., EURUSD=X, GBPUSD=X)."
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.2),
    output_type=PeerDiscovery,
    tools=[search_web, validate_ticker],
)
