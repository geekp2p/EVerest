import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Any, Dict
import itertools
import threading
from uuid import uuid4

from websockets import serve
from ocpp.routing import on
from ocpp.v16 import ChargePoint, call, call_result
from ocpp.v16.enums import (
    RegistrationStatus,
    AuthorizationStatus,
    Action,
    RemoteStartStopStatus,
    DataTransferStatus,
    ResetStatus,
    AvailabilityStatus,
    AvailabilityType,
)

from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel, Field, ConfigDict, AliasChoices, ValidationError
import uvicorn
from api import store
from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel, Field, ConfigDict, AliasChoices, ValidationError
import uvicorn
from api import store
from api.models import PendingSession
from services.vid_manager import VIDManager
from services.wallet import WalletService

logging.basicConfig(level=logging.INFO)

connected_cps: Dict[str, "CentralSystem"] = {}
_tx_counter = itertools.count(1)
vid_manager = VIDManager()
wallet = WalletService()


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO8601 timestamp and fall back to now on error."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()

def make_display_message_call(message_type: str, uri: str):
    payload = {"message_type": message_type, "uri": uri}
    if hasattr(call, "DisplayMessage"):
        DisplayMessageCls = getattr(call, "DisplayMessage")
        for attempt_kwargs in ("message", "payload", "content", "display"):
            try:
                return DisplayMessageCls(**{attempt_kwargs: payload})  # type: ignore
            except Exception:
                continue
    try:
        return call.DataTransfer("com.yourcompany.payment", "DisplayQRCode", json.dumps(payload))
    except Exception as e:
        logging.error(f"Failed to build DataTransfer fallback: {e}")
        raise


class CentralSystem(ChargePoint):
    def __init__(self, id, connection):
        super().__init__(id, connection)
        self.active_tx: Dict[int, Dict[str, Any]] = {}
        self.pending_remote: Dict[int, str] = {}
        self.pending_start: Dict[int, Dict[str, Any]] = {}
        self.connector_status: Dict[int, str] = {}
        self.no_session_tasks: Dict[int, asyncio.Task] = {}
        self.completed_sessions: List[Dict[str, Any]] = []
        self.last_heartbeat: datetime | None = None
        self.last_vid: str | None = None
        self.last_mac: str | None = None

    async def remote_start(self, connector_id: int, id_tag: str):
        req = call.RemoteStartTransaction(
            id_tag=id_tag,
            connector_id=connector_id
        )
        logging.info(f"→ RemoteStartTransaction to {self.id} (connector={connector_id}, idTag={id_tag})")
        resp = await self.call(req)
        status = getattr(resp, "status", None)
        if status == RemoteStartStopStatus.accepted:
            self.pending_remote[int(connector_id)] = id_tag
        else:
            logging.warning(f"RemoteStartTransaction rejected: {status}")
        return status

    async def remote_stop(self, transaction_id: int):
        req = call.RemoteStopTransaction(transaction_id=transaction_id)
        logging.info(f"→ RemoteStopTransaction to {self.id} (tx={transaction_id})")
        resp = await self.call(req)
        status = getattr(resp, "status", None)
        if status != RemoteStartStopStatus.accepted:
            logging.warning(f"RemoteStopTransaction rejected: {status}")
        return status

    async def remote_reset(self, reset_type: str):
        req = call.Reset(type=reset_type)
        logging.info(f"→ Reset to {self.id} (type={reset_type})")
        resp = await self.call(req)
        status = getattr(resp, "status", None)
        if status != ResetStatus.accepted:
            logging.warning(f"Reset rejected: {status}")
        return status

    async def change_configuration(self, key: str, value: str):
        req = call.ChangeConfiguration(key=key, value=value)
        logging.info(f"→ ChangeConfiguration to {self.id} ({key}={value})")
        resp = await self.call(req)
        logging.info(f"← ChangeConfiguration.conf: {resp}")
        return getattr(resp, "status", None)

    async def unlock_connector(self, connector_id: int):
        req = call.UnlockConnector(connector_id=connector_id)
        logging.info(f"→ UnlockConnector to {self.id} (connector={connector_id})")
        resp = await self.call(req)
        logging.info(f"← UnlockConnector.conf: {resp}")
        return getattr(resp, "status", None)

    async def change_availability(self, connector_id: int, available: bool):
        req = call.ChangeAvailability(
            connector_id=connector_id,
            type=AvailabilityType.operative if available else AvailabilityType.inoperative,
        )
        logging.info(
            f"→ ChangeAvailability to {self.id} (connector={connector_id}, available={available})"
        )
        resp = await self.call(req)
        logging.info(f"← ChangeAvailability.conf: {resp}")
        return getattr(resp, "status", None)

    async def _no_session_watchdog(self, connector_id: int, timeout: int = 90):
        try:
            await asyncio.sleep(timeout)
            status = self.connector_status.get(connector_id)
            if status in ("Preparing", "Occupied") and connector_id not in self.active_tx:
                logging.info(
                    f"No session started for connector {connector_id} after {timeout}s → unlocking"
                )
                await self.unlock_connector(connector_id)
                self.pending_remote.pop(connector_id, None)
                self.pending_start.pop(connector_id, None)
        except asyncio.CancelledError:
            logging.debug(f"Watchdog for connector {connector_id} cancelled")
        finally:
            self.no_session_tasks.pop(connector_id, None)

    @on(Action.boot_notification)
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, **kwargs):
        logging.info(
            f"← BootNotification from vendor={charge_point_vendor}, model={charge_point_model}"
        )
        response = call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            interval=300,
            status=RegistrationStatus.accepted,
        )

        asyncio.create_task(self._post_boot_actions())

        return response

    async def _post_boot_actions(self) -> None:
        await asyncio.sleep(0)

        supported_keys: List[str] = []
        try:
            conf_resp = await asyncio.wait_for(
                self.call(call.GetConfiguration()), timeout=10
            )
            items: Any = []
            if hasattr(conf_resp, "configuration_key"):
                items = getattr(conf_resp, "configuration_key")
            elif hasattr(conf_resp, "configurationKey"):
                items = getattr(conf_resp, "configurationKey")
            elif isinstance(conf_resp, dict):
                items = (
                    conf_resp.get("configuration_key")
                    or conf_resp.get("configurationKey")
                    or []
                )
            for entry in items:
                if isinstance(entry, dict):
                    key_name = entry.get("key")
                else:
                    key_name = getattr(entry, "key", None)
                if key_name:
                    supported_keys.append(key_name)
        except asyncio.TimeoutError:
            logging.warning(
                "Timeout fetching GetConfiguration; proceeding without supported keys."
            )
        except Exception as e:
            logging.warning(f"Failed to fetch supported configuration keys: {e}")

        if "AuthorizeRemoteTxRequests" in supported_keys:
            cfg_req = call.ChangeConfiguration(
                key="AuthorizeRemoteTxRequests", value="true"
            )
            await self._send_change_configuration(cfg_req)

        qr_url = "https://your-domain.com/qr?order_id=TEST123"
        target_key = "QRcodeConnectorID1"
        if target_key in supported_keys:
            change_req = call.ChangeConfiguration(key=target_key, value=qr_url)
            await self._send_change_configuration(change_req)
        else:
            try:
                fallback = make_display_message_call(message_type="QRCode", uri=qr_url)
                await self._send_change_configuration(fallback)
            except Exception as e:
                logging.error(f"Failed to send fallback display message: {e}")

    async def _send_change_configuration(self, request_payload):
        try:
            resp = await self.call(request_payload)
            logging.info(f"→ ChangeConfiguration / Custom response: {resp}")
        except Exception as e:
            logging.error(f"!!! ChangeConfiguration/custom failed: {e}")

    @on(Action.authorize)
    async def on_authorize(self, id_tag, **kwargs):
        logging.info(f"← Authorize request, idTag={id_tag}")
        conn_id = int(kwargs.get("connector_id", 0) or 0)
        vid = vid_manager.get_or_create_vid("id_tag", id_tag) if id_tag else None
        info = self.pending_start.get(conn_id, {})
        temp_vid = info.get("vid")
        mac = info.get("mac") or self.last_mac
        if mac:
            mac_vid = vid_manager.get_or_create_vid("mac", mac)
            if vid and vid != mac_vid:
                vid_manager.link_temp_vid(mac_vid, vid)
            vid = vid or mac_vid
        if temp_vid and vid and temp_vid != vid:
            vid_manager.link_temp_vid(temp_vid, vid)
        elif temp_vid and not vid:
            vid = temp_vid
        info["vid"] = vid
        if mac:
            info["mac"] = mac
        self.pending_start[conn_id] = info
        store.pending[(self.id, conn_id)] = PendingSession(
            station_id=self.id, connector_id=conn_id, id_tag=id_tag, vid=vid, mac=mac
        )
        self.last_vid = vid
        self.last_mac = mac if mac else self.last_mac
        return call_result.Authorize(id_tag_info={"status": AuthorizationStatus.accepted})

    @on(Action.status_notification)
    async def on_status_notification(self, connector_id, error_code, status, **kwargs):
        logging.info(
            f"← StatusNotification: connector {connector_id} → status={status}, errorCode={error_code}"
        )
        c_id = int(connector_id)
        self.connector_status[c_id] = status
        if status == "Preparing":
            pending = store.pending.get((self.id, c_id))
            vid = pending.vid if pending and pending.vid else None
            mac = pending.mac if pending and pending.mac else None
            if not vid:
                vid = self.last_vid
            if not mac:
                mac = self.last_mac
            if mac:
                mac_vid = vid_manager.get_or_create_vid("mac", mac)
                if vid and vid != mac_vid:
                    vid_manager.link_temp_vid(mac_vid, vid)
                vid = vid or mac_vid
            if not vid:
                vid = vid_manager.get_or_create_vid(
                    "temp", f"{self.id}:{c_id}:{uuid4().hex}"
                )
            store.pending[(self.id, c_id)] = PendingSession(
                station_id=self.id,
                connector_id=c_id,
                id_tag=vid,
                vid=vid,
                mac=mac,
            )
            self.pending_start[c_id] = {"vid": vid, "mac": mac}
            self.last_vid = None
            self.last_mac = None
            store.pending.pop((self.id, 0), None)
        else:
            store.pending.pop((self.id, c_id), None)
            self.pending_start.pop(c_id, None)
        if status in ("Preparing", "Occupied"):
            if c_id not in self.active_tx and c_id not in self.no_session_tasks:
                self.no_session_tasks[c_id] = asyncio.create_task(
                    self._no_session_watchdog(c_id)
                )
        else:
            task = self.no_session_tasks.pop(c_id, None)
            if task:
                task.cancel()
        return call_result.StatusNotification()

    @on(Action.heartbeat)
    def on_heartbeat(self, **kwargs):
        logging.info("← Heartbeat received")
        self.last_heartbeat = datetime.utcnow()
        return call_result.Heartbeat(current_time=self.last_heartbeat.isoformat() + "Z")

    @on(Action.meter_values)
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        logging.info(f"← MeterValues from connector {connector_id}: {meter_value}")
        c_id = int(connector_id)
        session = self.active_tx.get(c_id)
        if session is not None:
            for entry in meter_value:
                sample = {"timestamp": entry.get("timestamp")}
                for sv in entry.get("sampledValue", []):
                    meas = sv.get("measurand")
                    try:
                        val = float(sv.get("value"))
                    except (TypeError, ValueError):
                        continue
                    if meas == "Current.Import":
                        sample["current"] = val
                    elif meas == "Voltage":
                        sample["voltage"] = val
                    elif meas == "SoC":
                        sample["soc"] = val
                    elif meas == "Temperature":
                        sample["temperature"] = val
                session.setdefault("meter_samples", []).append(sample)
                session["last_sample"] = sample
        return call_result.MeterValues()

    @on(Action.data_transfer)
    async def on_data_transfer(
        self,
        vendor_id,
        message_id=None,
        data=None,
        *,
        debug: bool = False,
        **kwargs,
    ):
        """Handle a DataTransfer message.

        Logs parsing issues, the number of accepted entries and the originating
        charge point ID.  When ``debug`` is ``True`` the (sanitized) payload is
        also emitted at debug level for troubleshooting.
        """

        cp_id = self.id
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
        except Exception as exc:
            logging.error("DataTransfer parse error from %s: %s", cp_id, exc)
            return call_result.DataTransfer(status=DataTransferStatus.rejected)

        count = 0
        if isinstance(parsed, list):
            count = len(parsed)
        elif parsed is not None:
            count = 1

        logging.info(
            "← DataTransfer from %s: vendorId=%s, messageId=%s, accepted=%d",
            cp_id,
            vendor_id,
            message_id,
            count,
        )

        if debug:
            serialized = json.dumps(parsed) if not isinstance(parsed, str) else parsed
            sanitized = serialized.replace("\n", " ")
            if len(sanitized) > 2000:
                sanitized = sanitized[:2000] + "..."
            logging.debug("Sanitized DataTransfer payload from %s: %s", cp_id, sanitized)

        vid = None
        mac = None
        if isinstance(parsed, dict):
            raw_vid = (
                parsed.get("vid")
                or parsed.get("vehicleId")
                or parsed.get("vehicle_id")
            )
            if raw_vid:
                vid = vid_manager.get_or_create_vid("vid", raw_vid)
            mac = parsed.get("mac") or parsed.get("macId") or parsed.get("mac_id")
        if not mac and vendor_id == "MacID" and isinstance(data, str):
            mac = data
        if mac:
            mac_vid = vid_manager.get_or_create_vid("mac", mac)
            if vid and vid != mac_vid:
                vid_manager.link_temp_vid(mac_vid, vid)
            vid = vid or mac_vid
            self.last_mac = mac
        if vid:
            self.last_vid = vid
            for (sid, cid), pending in list(store.pending.items()):
                if sid == self.id:
                    if pending.vid and pending.vid != vid:
                        vid_manager.link_temp_vid(pending.vid, vid)
                    pending.id_tag = vid
                    pending.vid = vid
                    if mac:
                        pending.mac = mac
                    ps = self.pending_start.setdefault(cid, {})
                    ps["vid"] = vid
                    if mac:
                        ps["mac"] = mac

        return call_result.DataTransfer(status=DataTransferStatus.accepted)

    @on(Action.start_transaction)
    async def on_start_transaction(
        self,
        connector_id,
        id_tag,
        meter_start,
        timestamp,
        reservation_id=None,
        **kwargs,
    ):
        expected = self.pending_remote.get(int(connector_id))
        if expected is not None and expected != id_tag:
            logging.warning(
                f"StartTransaction for connector {connector_id} received with unexpected idTag (expected={expected}, got={id_tag}); rejecting"
            )
            await self.unlock_connector(int(connector_id))
            self.pending_remote.pop(int(connector_id), None)
            self.pending_start.pop(int(connector_id), None)
            return call_result.StartTransaction(
                transaction_id=0,
                id_tag_info={"status": AuthorizationStatus.invalid},
            )

        pending = self.pending_start.pop(int(connector_id), None)
        self.pending_remote.pop(int(connector_id), None)
        store.pending.pop((self.id, int(connector_id)), None)

        tx_id = next(_tx_counter)
        info = {
            "transaction_id": tx_id,
            "id_tag": id_tag,
            "meter_start": meter_start,
            "start_time": _parse_timestamp(timestamp),
            "meter_samples": [],
        }
        if pending:
            if "vid" in pending:
                info["vid"] = pending["vid"]
            if "mac" in pending:
                info["mac"] = pending["mac"]
        if id_tag and "vid" not in info:
            info["vid"] = vid_manager.get_or_create_vid("id_tag", id_tag)
        if self.last_vid and "vid" not in info:
            info["vid"] = self.last_vid
            self.last_vid = None
        if self.last_mac and "mac" not in info:
            info["mac"] = self.last_mac
            self.last_mac = None
        if "mac" in info and "vid" not in info:
            info["vid"] = vid_manager.get_or_create_vid("mac", info["mac"])
        self.active_tx[int(connector_id)] = info
        task = self.no_session_tasks.pop(int(connector_id), None)
        if task:
            task.cancel()
        logging.info(
            f"← StartTransaction from {self.id}: connector={connector_id}, idTag={id_tag}, meterStart={meter_start}, vid={info.get('vid')}"
        )
        logging.info(f"→ Assign transactionId={tx_id}")
        vid = info.get("vid")
        if vid and wallet.get_balance(vid) <= 0:
            logging.info(f"Insufficient balance for {vid}; stopping transaction {tx_id}")
            asyncio.create_task(self.remote_stop(tx_id))
        return call_result.StartTransaction(
            transaction_id=tx_id,
            id_tag_info={"status": AuthorizationStatus.accepted},
        )

    @on(Action.stop_transaction)
    async def on_stop_transaction(self, transaction_id, meter_stop, timestamp, **kwargs):
        session_info = None
        c_id = None
        for conn_id, info in list(self.active_tx.items()):
            if info.get("transaction_id") == int(transaction_id):
                session_info = info
                c_id = conn_id
                self.active_tx.pop(conn_id, None)
                break
        logging.info(f"← StopTransaction from {self.id}: tx={transaction_id}, meterStop={meter_stop}")
        if session_info:
            start_time = session_info.get("start_time")
            stop_time = _parse_timestamp(timestamp)
            duration_secs = (stop_time - start_time).total_seconds() if start_time else 0
            meter_start = session_info.get("meter_start", meter_stop)
            energy = meter_stop - meter_start
            record = {
                "connectorId": c_id,
                "transactionId": int(transaction_id),
                "idTag": session_info.get("id_tag", ""),
                "vehicleId": session_info.get("vid"),
                "mac": session_info.get("mac"),
                "meterStart": meter_start,
                "meterStop": meter_stop,
                "energy": energy,
                "startTime": start_time.isoformat() if start_time else None,
                "stopTime": stop_time.isoformat(),
                "durationSecs": duration_secs,
                "samples": session_info.get("meter_samples", []),
            }
            self.completed_sessions.append(record)
            logging.info(f"Session summary: {record}")
        return call_result.StopTransaction(
            id_tag_info={"status": AuthorizationStatus.accepted}
        )


DEFAULT_ID_TAG = "DEMO_IDTAG"
API_KEY = "changeme-123"

app = FastAPI(title="OCPP Central Control API", version="1.0.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logging.info(f">>> {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logging.info(f"<<< {request.method} {request.url.path} -> {response.status_code}")
        return response
    except Exception:
        logging.exception("Handler crashed")
        raise


@app.get("/api/v1/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}

class StationIn(BaseModel):
    name: str
    location: str | None = None


@app.post("/api/v1/stations")
@app.post("/stations", include_in_schema=False)
def add_station(data: StationIn):
    station = store.create_station(data.name, data.location)
    return station.model_dump()


@app.get("/api/v1/stations")
@app.get("/stations", include_in_schema=False)
def get_stations():
    return [station.model_dump() for station in store.stations.values()]


@app.get("/api/v1/stations/{station_id}")
@app.get("/stations/{station_id}", include_in_schema=False)
def get_station(station_id: int):
    station = store.get_station(station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    return station.model_dump()

@app.delete("/api/v1/stations/{station_id}")
def delete_station(station_id: int):
    if not store.delete_station(station_id):
        raise HTTPException(status_code=404, detail="Station not found")
    return {"ok": True}

class StartReq(BaseModel):
    cpid: str
    connectorId: int
    id_tag: str | None = Field(default=None, alias="idTag")
    transactionId: int | None = None
    timestamp: str | None = None
    vid: str | None = None
    mac: str | None = None
    kv: str | None = None
    kvMap: Dict[str, str] | None = None
    hash: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class StopReq(BaseModel):
    cpid: str
    transactionId: int | None = None
    connectorId: int | None = None
    idTag: str | None = None
    timestamp: str | None = None
    vid: str | None = None
    kv: str | None = None
    kvMap: Dict[str, str] | None = None
    hash: str | None = None


class StopByConnectorReq(BaseModel):
    cpid: str
    connectorId: int


class ReleaseReq(BaseModel):
    cpid: str
    connectorId: int


class ResetReq(BaseModel):
    cpid: str
    type: str


class AvailabilityReq(BaseModel):
    cpid: str
    connectorId: int
    available: bool


class SessionStartReq(BaseModel):
    vehicleId: str


class SessionStopReq(BaseModel):
    kWhDelivered: float


class ActiveSession(BaseModel):
    cpid: str
    connectorId: int
    stationId: int | None = None
    idTag: str | None = None
    vehicleId: str | None = None
    mac: str | None = None
    transactionId: int | None = None


class UserIdentifier(BaseModel):
    vid: str | None = None
    mac: str | None = None
    user_id: str | None = None
    phone: str | None = None
    app_id: str | None = None
    transaction_id: str | None = None
    qr_id: str | None = None

    def first(self) -> tuple[str, str]:
        for field, value in self.model_dump(exclude_none=True).items():
            return field, value
        raise ValueError("No identifier provided")


class WalletReq(BaseModel):
    identifier: UserIdentifier
    amount: float


class CompletedSession(BaseModel):
    """Summary of a finished charging transaction."""

    cpid: str
    connectorId: int
    idTag: str
    vehicleId: str | None = None
    mac: str | None = None
    transactionId: int
    meterStart: int
    meterStop: int
    energy: int
    startTime: str
    stopTime: str
    durationSecs: float
    samples: List[Dict[str, Any]] = Field(default_factory=list)


class ConnectorStatus(BaseModel):
    cpid: str
    connectorId: int
    status: str


class ConnectorOverview(BaseModel):
    cpid: str
    connectorId: int
    status: str
    pending: PendingSession | None = None
    active: Dict[str, Any] | None = None


def require_key(x_api_key: str | None):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")


@app.post("/api/v1/start")
async def api_start(req: StartReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    try:
        id_tag = req.id_tag or DEFAULT_ID_TAG
        info = {"id_tag": id_tag}
        vid = None
        if req.vid:
            vid = vid_manager.get_or_create_vid("vid", req.vid)
        if req.mac:
            mac_vid = vid_manager.get_or_create_vid("mac", req.mac)
            info["mac"] = req.mac
            if vid and vid != mac_vid:
                vid_manager.link_temp_vid(mac_vid, vid)
            vid = vid or mac_vid
        if vid:
            info["vid"] = vid
        cp.pending_start[int(req.connectorId)] = info
        status = await cp.remote_start(req.connectorId, id_tag)
        if status != RemoteStartStopStatus.accepted:
            cp.pending_start.pop(int(req.connectorId), None)
            raise HTTPException(status_code=409, detail=f"RemoteStart rejected: {status}")
        store.pending.pop((req.cpid, int(req.connectorId)), None)
        return {"ok": True, "message": "RemoteStartTransaction sent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/stop")
async def api_stop(req: StopReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    try:
        tx_id = req.transactionId
        if tx_id is not None:
            if not any(
                session.get("transaction_id") == tx_id
                for session in cp.active_tx.values()
            ):
                raise HTTPException(status_code=404, detail="No matching active transaction")
        elif req.connectorId is not None:
            session = cp.active_tx.get(req.connectorId)
            if session:
                tx_id = session.get("transaction_id")
        if tx_id is None:
            raise HTTPException(status_code=404, detail="No matching active transaction")
        status = await cp.remote_stop(tx_id)
        if status != RemoteStartStopStatus.accepted:
            raise HTTPException(status_code=409, detail=f"RemoteStop rejected: {status}")
        return {"ok": True, "transactionId": tx_id, "message": "RemoteStopTransaction sent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/charge/stop")
async def api_stop_by_connector(req: StopByConnectorReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    session = cp.active_tx.get(req.connectorId)
    if session is None:
        raise HTTPException(status_code=404, detail="No active transaction for this connector")
    tx_id = session["transaction_id"]
    try:
        status = await cp.remote_stop(tx_id)
        if status != RemoteStartStopStatus.accepted:
            raise HTTPException(status_code=409, detail=f"RemoteStop rejected: {status}")
        return {"ok": True, "transactionId": tx_id, "message": "RemoteStopTransaction sent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/release")
async def api_release(req: ReleaseReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    if req.connectorId in cp.active_tx:
        raise HTTPException(status_code=400, detail="Connector has active transaction")
    task = cp.no_session_tasks.pop(req.connectorId, None)
    if task:
        task.cancel()
    cp.pending_remote.pop(req.connectorId, None)
    cp.pending_start.pop(req.connectorId, None)
    try:
        await cp.unlock_connector(req.connectorId)
        return {"ok": True, "message": "UnlockConnector sent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/availability")
async def api_change_availability(req: AvailabilityReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    try:
        status = await cp.change_availability(req.connectorId, req.available)
        if status not in (AvailabilityStatus.accepted, AvailabilityStatus.scheduled):
            raise HTTPException(status_code=409, detail=f"ChangeAvailability rejected: {status}")
        value = status.value if hasattr(status, "value") else status
        return {"ok": True, "status": value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/availability")
async def api_change_availability(req: AvailabilityReq):
    cp = connected_cps.get(req.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{req.cpid}' not connected")
    try:
        status = await cp.change_availability(req.connectorId, req.available)
        if status not in (AvailabilityStatus.accepted, AvailabilityStatus.scheduled):
            raise HTTPException(status_code=409, detail=f"ChangeAvailability rejected: {status}")
        value = status.value if hasattr(status, "value") else status
        return {"ok": True, "status": value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/reset")
async def api_reset(request: Request):
    payload: Dict[str, Any]
    try:
        payload = await request.json()
    except Exception:
        form = await request.form()
        payload = dict(form) if form else dict(request.query_params)

    try:
        data = ResetReq(**payload)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    cp = connected_cps.get(data.cpid)
    if not cp:
        raise HTTPException(status_code=404, detail=f"ChargePoint '{data.cpid}' not connected")
    if data.type not in ("Hard", "Soft"):
        raise HTTPException(status_code=400, detail="invalid reset type")
    try:
        status = await cp.remote_reset(data.type)
        if status != ResetStatus.accepted:
            raise HTTPException(status_code=409, detail=f"Reset rejected: {status}")
        return {"ok": True, "status": status.value if hasattr(status, 'value') else status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/pending")
def list_pending():
    return [p.model_dump() for p in store.pending.values()]

@app.get("/api/v1/active")
def api_active_sessions():
    sessions: list[ActiveSession] = []
    for cpid, cp in connected_cps.items():
        for conn_id, info in cp.active_tx.items():
            station_id = None
            conn = store.get_connector(conn_id)
            if conn is not None:
                station_id = getattr(conn, "station_id", getattr(conn, "stationId", None))
            sessions.append(
                ActiveSession(
                    cpid=cpid,
                    connectorId=conn_id,
                    stationId=station_id,
                    idTag=info.get("id_tag"),
                    vehicleId=info.get("vid"),
                    mac=info.get("mac"),
                    transactionId=info.get("transaction_id"),
                    lastSample=info.get("last_sample"),
                )
            )
    return {"sessions": [s.dict() for s in sessions]}


@app.get("/api/v1/history")
async def api_session_history():
    sessions: list[CompletedSession] = []
    for cpid, cp in connected_cps.items():
        for record in cp.completed_sessions:
            sessions.append(CompletedSession(cpid=cpid, **record))
    return {"sessions": [s.dict() for s in sessions]}


@app.post("/api/v1/sessions/{connector_id}/start")
def api_start_session(connector_id: int, req: SessionStartReq):
    connector = store.get_connector(connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    if getattr(connector, "status", None) != "Available":
        raise HTTPException(status_code=409, detail="Connector not available")
    connector.status = "Charging"
    tx_id = next(_tx_counter)
    session = {
        "id": tx_id,
        "connector_id": connector_id,
        "vehicleId": req.vehicleId,
        "status": "active",
        "started_at": datetime.utcnow().isoformat() + "Z",
    }
    store.sessions[tx_id] = session
    try:
        connector.charging_sessions.append(session)
    except Exception:
        pass
    return {"transactionId": tx_id}


@app.post("/api/v1/sessions/{connector_id}/stop")
def api_stop_session(connector_id: int, req: SessionStopReq):
    connector = store.get_connector(connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    active_id = None
    active_session = None
    for sid, session in list(store.sessions.items()):
        conn = session.get("connector_id") if isinstance(session, dict) else getattr(session, "connector_id", None)
        status = session.get("status") if isinstance(session, dict) else getattr(session, "status", None)
        if conn == connector_id and status == "active":
            active_id = sid
            active_session = session
            break
    if active_session is None:
        raise HTTPException(status_code=404, detail="Active session not found")
    finished_at = datetime.utcnow().isoformat() + "Z"
    if isinstance(active_session, dict):
        active_session["finishedAt"] = finished_at
        active_session["kWhDelivered"] = req.kWhDelivered
        active_session["status"] = "completed"
    else:
        setattr(active_session, "finishedAt", finished_at)
        setattr(active_session, "kWhDelivered", req.kWhDelivered)
        setattr(active_session, "status", "completed")
    connector.status = "Available"
    store.sessions_history.append(active_session)
    if active_id is not None:
        store.sessions.pop(active_id, None)
    return {"session": active_session}


@app.get("/api/v1/sessions/{vehicle_id}")
def get_sessions_for_vehicle(vehicle_id: str):
    """Return current and past sessions for the given vehicle ID."""

    current = None
    history = []

    def _to_dict(obj):
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()  # type: ignore[call-arg]
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return obj

    for session in store.sessions.values():
        vid = None
        if isinstance(session, dict):
            vid = session.get("vehicleId") or session.get("vehicle_id")
            status = session.get("status")
        else:
            vid = getattr(session, "vehicleId", getattr(session, "vehicle_id", None))
            status = getattr(session, "status", None)

        if vid != vehicle_id:
            continue

        session_dict = _to_dict(session)
        if status == "active" or (isinstance(session_dict, dict) and session_dict.get("status") == "active"):
            current = session_dict
        else:
            history.append(session_dict)

    return {"current": current, "history": history}


@app.get("/api/v1/status")
async def api_connector_status():
    statuses: list[ConnectorStatus] = []
    for cpid, cp in connected_cps.items():
        for conn_id, status in cp.connector_status.items():
            statuses.append(ConnectorStatus(cpid=cpid, connectorId=conn_id, status=status))
    return {"connectors": [s.dict() for s in statuses]}


@app.get("/api/v1/overview")
def api_overview():
    connectors: list[ConnectorOverview] = []
    for cpid, cp in connected_cps.items():
        for conn_id, status in cp.connector_status.items():
            pending = store.pending.get((cpid, conn_id))
            active = cp.active_tx.get(conn_id)
            active_info = None
            if active:
                start_time = active.get("start_time")
                if isinstance(start_time, datetime):
                    start_time = start_time.isoformat()
                active_info = {
                    "transactionId": active.get("transaction_id"),
                    "idTag": active.get("id_tag"),
                    "vehicleId": active.get("vid"),
                    "mac": active.get("mac"),
                    "startTime": start_time,
                    "meterStart": active.get("meter_start"),
                    "lastSample": active.get("last_sample"),
                }
            connectors.append(
                ConnectorOverview(
                    cpid=cpid,
                    connectorId=conn_id,
                    status=status,
                    pending=pending,
                    active=active_info,
                )
            )
    return {"connectors": [c.model_dump() for c in connectors]}


@app.post("/api/v1/identify")
def api_identify(identifier: UserIdentifier):
    field, value = identifier.first()
    vid = vid_manager.get_or_create_vid(field, value)
    return {"vid": vid}


@app.post("/api/v1/wallet/topup")
def api_wallet_topup(req: WalletReq):
    field, value = req.identifier.first()
    vid = vid_manager.get_or_create_vid(field, value)
    balance = wallet.top_up(vid, req.amount)
    return {"vid": vid, "balance": balance}


@app.post("/api/v1/wallet/charge")
def api_wallet_charge(req: WalletReq):
    field, value = req.identifier.first()
    vid = vid_manager.get_or_create_vid(field, value)
    try:
        balance = wallet.deduct(vid, req.amount)
    except ValueError:
        raise HTTPException(status_code=402, detail="Insufficient balance")
    return {"vid": vid, "balance": balance}


async def run_http_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, loop="asyncio", log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    async def handler(websocket, path=None):
        if path is None:
            try:
                path = websocket.request.path
            except AttributeError:
                path = websocket.path if hasattr(websocket, "path") else ""
        cp_id = path.rsplit('/', 1)[-1] if path else "UNKNOWN"
        logging.info(f"[Central] New connection for Charge Point ID: {cp_id}")

        central = CentralSystem(cp_id, websocket)
        connected_cps[cp_id] = central
        try:
            await central.start()
        finally:
            connected_cps.pop(cp_id, None)
            logging.info(f"[Central] Disconnected: {cp_id}")

    def console_thread(loop: asyncio.AbstractEventLoop):
        while True:
            try:
                cmd = input().strip()
            except EOFError:
                return
            if not cmd:
                continue
            parts = cmd.split()
            if parts[0] == "ls":
                print("Connected CPs:", ", ".join(connected_cps.keys()) or "(none)")
                continue
            if parts[0] == "map" and len(parts) == 2:
                cp = connected_cps.get(parts[1])
                if not cp:
                    print("No such CP")
                else:
                    print(f"{parts[1]} active_tx:", cp.active_tx)
                continue
            if parts[0] == "config" and len(parts) >= 4:
                cpid, key, value = parts[1], parts[2], " ".join(parts[3:])
                cp = connected_cps.get(cpid)
                if not cp:
                    print("No such CP")
                    continue
                asyncio.run_coroutine_threadsafe(cp.change_configuration(key, value), loop)
                continue
            if parts[0] == "start" and len(parts) >= 4:
                cpid, connector, idtag = parts[1], int(parts[2]), " ".join(parts[3:])
                cp = connected_cps.get(cpid)
                if not cp:
                    print("No such CP")
                    continue
                asyncio.run_coroutine_threadsafe(cp.remote_start(connector, idtag), loop)
                continue
            if parts[0] == "stop" and len(parts) == 3:
                cpid, num = parts[1], int(parts[2])
                cp = connected_cps.get(cpid)
                if not cp:
                    print("No such CP")
                    continue
                session = cp.active_tx.get(num)
                if session:
                    txid = session.get("transaction_id", num)
                    asyncio.run_coroutine_threadsafe(cp.remote_stop(txid), loop)
                    continue
                tx_match = None
                for info in cp.active_tx.values():
                    if info.get("transaction_id") == num:
                        tx_match = num
                        break
                if tx_match is not None:
                    asyncio.run_coroutine_threadsafe(cp.remote_stop(tx_match), loop)
                else:
                    asyncio.run_coroutine_threadsafe(cp.unlock_connector(num), loop)
                continue
            if parts[0] == "avail" and len(parts) == 4:
                cpid, connector, state = parts[1], int(parts[2]), parts[3].lower()
                cp = connected_cps.get(cpid)
                if not cp:
                    print("No such CP")
                    continue
                available = state in ("1", "true", "available", "operational", "operative")
                asyncio.run_coroutine_threadsafe(
                    cp.change_availability(connector, available), loop
                )
                continue
            print("Unknown command. Examples: start CP_123 1 TESTTAG | stop CP_123 42 | ls | map CP_123")

    loop = asyncio.get_running_loop()
    threading.Thread(target=console_thread, args=(loop,), daemon=True).start()

    api_task = asyncio.create_task(run_http_api())

    async with serve(
        handler,
        host='0.0.0.0',
        port=9000,
        subprotocols=['ocpp1.6']
    ):
        logging.info("⚡ Central listening on ws://0.0.0.0:9000/ocpp/<ChargePointID> | HTTP :8080")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
