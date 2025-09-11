from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

# NOTE: In-memory storage is used for now. Replace with a proper
# database layer in the future.


@dataclass
class ChargingSession:
    id: int
    connector_id: int
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    kwh_delivered: Optional[float] = None
    status: str = "active"


@dataclass
class Connector:
    id: int
    station_id: int
    type: str
    status: str = "available"
    charging_sessions: List[ChargingSession] = field(default_factory=list)


@dataclass
class Station:
    id: int
    name: str
    location: Optional[str] = None
    connectors: List[Connector] = field(default_factory=list)


class InMemoryDB:
    """Simple in-memory store for stations, connectors and sessions.

    This is a placeholder until a real database is integrated.
    """

    def __init__(self) -> None:
        self.stations: Dict[int, Station] = {}
        self.connectors: Dict[int, Connector] = {}
        self.sessions: Dict[int, ChargingSession] = {}
        self._station_id = 0
        self._connector_id = 0
        self._session_id = 0

    def add_station(self, name: str, location: Optional[str] = None) -> Station:
        self._station_id += 1
        station = Station(id=self._station_id, name=name, location=location)
        self.stations[station.id] = station
        return station

    def add_connector(self, station_id: int, type: str, status: str = "available") -> Connector:
        self._connector_id += 1
        connector = Connector(id=self._connector_id, station_id=station_id, type=type, status=status)
        self.connectors[connector.id] = connector
        self.stations[station_id].connectors.append(connector)
        return connector

    def add_charging_session(self, connector_id: int, started_at: Optional[datetime] = None) -> ChargingSession:
        self._session_id += 1
        session = ChargingSession(
            id=self._session_id,
            connector_id=connector_id,
            started_at=started_at or datetime.utcnow(),
        )
        self.sessions[session.id] = session
        self.connectors[connector_id].charging_sessions.append(session)
        return session


db = InMemoryDB()