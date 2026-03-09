from agents import Agent, ModelSettings

from analyst.agents.tools import search_web
from analyst.llms import BYTEDANCE_SEED_2_0_MINI

description_agent = Agent(
    name="Company Description Writer",
    instructions=(
        "You are a financial data provider writing a brief company description. "
        "You MUST call the search_web tool first to get the latest information — "
        "do not rely on your training data.\n\n"
        "Rules:\n"
        "- Exactly 1-2 sentences. Hard limit. No exceptions.\n"
        "- Sentence 1: What the company does (core business in plain terms)\n"
        "- Sentence 2 (optional): One key fact about scale or market position\n"
        "- Never say 'As of [year]' — just state facts in present tense\n"
        "- Don't list every product — pick the 2-3 most important\n"
        "- Write in third person, present tense\n"
        "- No disclaimers, no hedging, no opinions\n"
        "- Style: Bloomberg terminal brief — terse, factual, no filler\n"
        "- Return ONLY the description text, nothing else\n\n"
        "Good example: 'Nvidia designs GPUs and AI accelerators powering data centers, "
        "gaming, and autonomous vehicles. The company commands over 80%% of the AI "
        "training chip market with a $3T+ market capitalization.'\n\n"
        "Bad example: 'Nvidia Corporation is a multinational technology company that "
        "designs graphics processing units and system-on-chip units for the gaming, "
        "professional visualization, data center, and automotive markets, alongside "
        "proprietary software platforms including CUDA and TensorRT.'"
    ),
    model=BYTEDANCE_SEED_2_0_MINI,
    model_settings=ModelSettings(temperature=0.2),
    tools=[search_web],
)
