from datetime import datetime
from itertools import count
from typing import Any, Dict, List, Optional, Tuple

from .models import ChargingSession, Connector, PendingSession, Station

stations: Dict[int, Station] = {}
sessions: Dict[int, ChargingSession] = {}
sessions_history: List[Dict[str, Any]] = []
_connectors: Dict[int, Connector] = {}
pending: Dict[Tuple[str, int], PendingSession] = {}

_station_seq = count(1)
_connector_seq = count(1)
_session_seq = count(1)

def create_station(name: str, location: Optional[str] = None) -> Station:
    station = Station(id=next(_station_seq), name=name, location=location)
    stations[station.id] = station
    return station

def list_stations() -> List[Station]:
    return list(stations.values())

def get_station(station_id: int) -> Optional[Station]:
    return stations.get(station_id)

def delete_station(station_id: int) -> bool:
    return stations.pop(station_id, None) is not None

def add_connector(station_id: int, type: str, status: str = "available") -> Connector:
    connector = Connector(id=next(_connector_seq), station_id=station_id, type=type, status=status)
    _connectors[connector.id] = connector
    stations[station_id].connectors.append(connector)
    return connector

def get_connector(connector_id: int) -> Optional[Connector]:
    return _connectors.get(connector_id)

def start_session(connector_id: int) -> ChargingSession:
    session = ChargingSession(
        id=next(_session_seq), connector_id=connector_id, started_at=datetime.utcnow()
    )
    sessions[session.id] = session
    _connectors[connector_id].charging_sessions.append(session)
    return session

def end_session(session_id: int, kwh_delivered: Optional[float] = None) -> Optional[ChargingSession]:
    session = sessions.get(session_id)
    if session:
        session.ended_at = datetime.utcnow()
        session.kwh_delivered = kwh_delivered
        session.status = "completed"
    return session

def delete_session(session_id: int) -> bool:
    return sessions.pop(session_id, None) is not None