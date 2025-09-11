from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from ocpp_client import OCPPClient


@dataclass
class ChargingSession:
    """Track a charging session and communicate via OCPP."""

    ocpp: OCPPClient
    connector_id: int = 1
    id_tag: str = "GUEST"
    transaction_id: int | None = None
    meter_start: int | None = None
    samples: list[dict] = field(default_factory=list)
    sample_interval: float = 10.0
    _meter_task: asyncio.Task | None = None

    async def start(self, meter_start: int) -> dict:
        """Begin a charging session and record the starting meter value."""
        self.meter_start = meter_start
        await self.ocpp.connect()
        response = await self.ocpp.start_transaction(
            self.connector_id, self.id_tag, self.meter_start
        )
        self.transaction_id = response.get("transactionId")
        self._meter_task = asyncio.create_task(self._meter_loop())
        return response

    async def stop(self, meter_stop: int) -> dict:
        """Stop an active charging session and send the final meter value."""
        if self.transaction_id is None:
            raise RuntimeError("Session not started")
        response = await self.ocpp.stop_transaction(
            self.transaction_id, self.id_tag, meter_stop
        )
        if self._meter_task:
            self._meter_task.cancel()
            self._meter_task = None
        await self.ocpp.close()
        return response

    async def _meter_loop(self) -> None:
        try:
            while self.transaction_id is not None:
                sample = self._read_sample()
                self.samples.append(sample)
                await self.ocpp.send_meter_values(
                    self.transaction_id, self.connector_id, sample
                )
                await asyncio.sleep(self.sample_interval)
        except asyncio.CancelledError:
            pass

    def _read_sample(self) -> dict:
        """Read current, voltage, state of charge and temperature.

        This is a placeholder implementation and should be replaced with actual
        hardware interactions.  Values are reported as floats and a timestamp in
        ISO8601 format is included.
        """

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "current": 0.0,
            "voltage": 0.0,
            "soc": 0.0,
            "temperature": 0.0,
        }