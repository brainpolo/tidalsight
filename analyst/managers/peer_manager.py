import asyncio
import logging

from agents import RunConfig, Runner
from django.core.cache import cache

from analyst.agents.peer_discovery import PeerDiscovery, peer_discovery_agent
from analyst.agents.provider import get_model_provider
from analyst.app_behaviour import MAX_AGENT_TURNS, PEER_SYNC_LOCK_TTL, PEER_TARGET_COUNT
from scraper.managers.asset_manager import get_or_create_asset
from scraper.models import Asset

logger = logging.getLogger(__name__)


def sync_peers(asset: Asset) -> list[Asset]:
    if asset.peers.exists():
        return list(asset.peers.all())

    lock_key = f"sync:peers:{asset.ticker}"
    if not cache.add(lock_key, True, PEER_SYNC_LOCK_TTL):
        logger.info("Peer sync for %s already in progress, skipping", asset.ticker)
        return list(asset.peers.all())

    try:
        prompt = (
            f"Return {PEER_TARGET_COUNT} direct competitor/peer stock tickers for "
            f"{asset.ticker} ({asset.name}, {asset.get_asset_class_display()})."
        )

        config = RunConfig(
            model_provider=get_model_provider(),
            tracing_disabled=True,
        )
        result = asyncio.run(
            Runner.run(
                peer_discovery_agent,
                input=prompt,
                run_config=config,
                max_turns=MAX_AGENT_TURNS,
            )
        )
        discovery: PeerDiscovery = result.final_output

        valid_peers = []
        for ticker in discovery.tickers:
            ticker = ticker.upper().strip()
            if ticker == asset.ticker:
                continue
            try:
                peer = get_or_create_asset(ticker)
                valid_peers.append(peer)
            except ValueError, ConnectionError:
                logger.warning(
                    "Skipping invalid peer ticker %s for %s", ticker, asset.ticker
                )
                continue

        asset.peers.set(valid_peers)
        logger.info("Synced %d peers for %s", len(valid_peers), asset.ticker)
        return valid_peers
    except ConnectionError, RuntimeError, ValueError, TimeoutError:
        logger.exception("Failed to sync peers for %s", asset.ticker)
        return []
    finally:
        cache.delete(lock_key)
