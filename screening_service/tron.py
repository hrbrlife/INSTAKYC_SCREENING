from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import httpx

from .config import Settings


@dataclass
class TronReputation:
    address: str
    risk: str
    score: int
    reasons: List[str]
    stats: Dict[str, float]
    raw: Dict[str, object]


class TronReputationClient:
    """Thin wrapper around the public TronScan API with deterministic scoring."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _http_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.settings.http_user_agent:
            headers["User-Agent"] = self.settings.http_user_agent
        return headers

    async def fetch_account(self, address: str) -> Dict[str, object]:
        async with httpx.AsyncClient(
            timeout=self.settings.tron_timeout, headers=self._http_headers()
        ) as client:
            response = await client.get(
                str(self.settings.tron_account_url), params={"address": address}
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Unexpected Tron API payload")
            return data

    async def reputation(self, address: str) -> TronReputation:
        address = address.strip()
        if not address:
            raise ValueError("Address is required")
        payload = await self.fetch_account(address)
        return self._score_payload(address, payload)

    def _score_payload(self, address: str, payload: Dict[str, object]) -> TronReputation:
        score = 0
        reasons: List[str] = []

        tx_count = int(payload.get("totalTransactionCount") or 0)
        if tx_count > 50000:
            score += 50
            reasons.append("Extremely high transaction volume")
        elif tx_count > 10000:
            score += 30
            reasons.append("High transaction volume")
        elif tx_count > 1000:
            score += 15
            reasons.append("Active address with many transfers")

        trx_balance = _normalise_trx(payload.get("balance"))
        if trx_balance > 1_000_000:
            score += 25
            reasons.append("TRX balance exceeds 1M tokens")
        elif trx_balance > 100_000:
            score += 10
            reasons.append("TRX balance exceeds 100k tokens")

        token_balances = payload.get("trc20token_balances") or []
        if isinstance(token_balances, list):
            high_liquidity_tokens = sum(
                1
                for token in token_balances
                if isinstance(token, dict)
                and float(token.get("amount") or 0) > 100_000
            )
            if high_liquidity_tokens:
                score += 15
                reasons.append("Large holdings in TRC-20 assets")

        if payload.get("allowExchange") is False:
            score += 10
            reasons.append("Exchange permissions disabled")

        if payload.get("witness"):
            score += 20
            reasons.append("Witness account")

        if payload.get("addressTagLogo"):
            score += 10
            reasons.append("Address is tagged in TronScan")

        recent_in = len(payload.get("transactions_in") or [])
        recent_out = len(payload.get("transactions_out") or [])
        if recent_in + recent_out > 20:
            score += 10
            reasons.append("High short-term transaction activity")

        risk = "low"
        if score >= 60:
            risk = "high"
        elif score >= 30:
            risk = "medium"

        stats = {
            "transaction_count": tx_count,
            "trx_balance": trx_balance,
            "recent_in": recent_in,
            "recent_out": recent_out,
            "trc20_tokens": len(token_balances) if isinstance(token_balances, list) else 0,
        }

        return TronReputation(
            address=address,
            risk=risk,
            score=score,
            reasons=reasons,
            stats=stats,
            raw=payload,
        )


def _normalise_trx(raw: object) -> float:
    if raw is None:
        return 0.0
    try:
        if isinstance(raw, str):
            raw = float(raw)
        return float(raw) / 1_000_000
    except (TypeError, ValueError):
        return 0.0
