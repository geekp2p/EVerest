from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .models import Station
from .store import create_station, get_station, list_stations

app = FastAPI(title="ChargeBridge API")

class StationIn(BaseModel):
    name: str
    location: Optional[str] = None

@app.post("/stations", response_model=Station)
def add_station(data: StationIn) -> Station:
    return create_station(data.name, data.location)

@app.get("/stations", response_model=List[Station])
def get_stations() -> List[Station]:
    return list_stations()

@app.get("/stations/{station_id}", response_model=Station)
def get_station_by_id(station_id: int) -> Station:
    station = get_station(station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station