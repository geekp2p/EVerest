from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ChargingSession(BaseModel):
    id: int
    connector_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    kwh_delivered: Optional[float] = None
    status: str = "active"


class Connector(BaseModel):
    id: int
    station_id: int
    type: str
    status: str = "available"
    charging_sessions: List[ChargingSession] = Field(default_factory=list)


class Station(BaseModel):
    id: int
    name: str
    location: Optional[str] = None
    connectors: List[Connector] = Field(default_factory=list)


class PendingSession(BaseModel):
    station_id: str
    connector_id: int
    id_tag: Optional[str] = None
    vid: Optional[str] = None
    mac: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)