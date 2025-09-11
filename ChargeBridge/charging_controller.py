"""Orchestrator for charging sessions.

central.py coordinates the high-level flow while delegating OCPP
communication and meter handling to dedicated modules.  This layout keeps
responsibilities separated and makes the system easier to extend for other
charging networks.  The demo focuses on Gresgying 120–180 kW DC chargers
but the code paths remain compatible with other vendors and OCPP versions.
"""

import asyncio
from charging_session import ChargingSession
from ocpp_client import OCPPClient


async def run_demo() -> None:
    """Demonstrate starting and stopping a charging session."""
    client = OCPPClient(
        "ws://45.136.236.186:9000/ocpp/CP_1",
        "CP_1",
        ocpp_protocol="ocpp1.6",
        charger_model="Gresgying 120-180 kW DC",
    )
    session = ChargingSession(client, connector_id=1, id_tag="DEMO")

    # In a real system meter values would be retrieved from the charger.
    start_response = await session.start(meter_start=0)
    print("StartTransaction response:", start_response)

    # ... charging takes place ...
    stop_response = await session.stop(meter_stop=100)
    print("StopTransaction response:", stop_response)


if __name__ == "__main__":
    asyncio.run(run_demo())