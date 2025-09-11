"""Simple in-memory wallet service for tracking user balances."""

from __future__ import annotations

from typing import Dict


class WalletService:
    """Manage balances keyed by internal VIDs."""

    def __init__(self) -> None:
        self._balances: Dict[str, float] = {}

    def get_balance(self, vid: str) -> float:
        """Return the current balance for ``vid``."""
        return self._balances.get(vid, 0.0)

    def top_up(self, vid: str, amount: float) -> float:
        """Increase ``vid`` balance by ``amount`` and return the new balance."""
        self._balances[vid] = self.get_balance(vid) + amount
        return self._balances[vid]

    def deduct(self, vid: str, amount: float) -> float:
        """Decrease ``vid`` balance by ``amount`` if sufficient funds exist."""
        balance = self.get_balance(vid)
        if balance < amount:
            raise ValueError("insufficient funds")
        self._balances[vid] = balance - amount
        return self._balances[vid]