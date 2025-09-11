import asyncio
import json
import uuid
from datetime import datetime
import logging
import csv

import websockets

logger = logging.getLogger(__name__)


class OCPPClient:
    """Minimal OCPP client for interacting with charging stations.

    The client targets OCPP 1.6j by default but the WebSocket subprotocol
    can be adjusted to support newer revisions.  It was written with
    Gresgying 120–180 kW DC stations in mind yet keeps messaging
    generic so other vendors and models can be supported as well.
    """

    def __init__(
        self,
        uri: str,
        charge_point_id: str,
        ocpp_protocol: str = "ocpp1.6",
        charger_model: str = "Gresgying 120-180 kW DC",
    ) -> None:
        self.uri = uri
        self.charge_point_id = charge_point_id
        self.ocpp_protocol = ocpp_protocol
        self.charger_model = charger_model
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._listener_task: asyncio.Task | None = None
        self._active_tx: dict | None = None
        self._last_meter: int = 0

    async def connect(self) -> None:
        """Establish a WebSocket connection and announce the charge point."""
        self._ws = await websockets.connect(self.uri, subprotocols=[self.ocpp_protocol])
        await self.boot_notification()
        self._listener_task = asyncio.create_task(self._listen())

    async def close(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _listen(self) -> None:
        """Listen for incoming CALL messages and dispatch handlers."""
        assert self._ws is not None
        try:
            while True:
                raw = await self._ws.recv()
                msg = json.loads(raw)
                if not isinstance(msg, list) or len(msg) < 4:
                    continue
                if msg[0] != 2:
                    continue
                _, message_id, action, payload = msg
                handler = getattr(self, f"on_{action.lower()}", None)
                if handler:
                    resp_payload = await handler(payload)
                    response = [3, message_id, resp_payload]
                else:
                    response = [4, message_id, "NotImplemented", {}]
                await self._ws.send(json.dumps(response))
        except asyncio.CancelledError:
            pass
        except websockets.ConnectionClosed:
            pass

    async def _call(
        self, action: str, payload: dict, *, return_message_id: bool = False
    ) -> dict | tuple[dict, str]:
        """Send an OCPP CALL message and return the payload of the result.

        Parameters
        ----------
        action: str
            The OCPP action to invoke.
        payload: dict
            Payload for the request.
        return_message_id: bool, optional
            When ``True`` the generated message ID is returned along with the
            response payload.  This is useful for logging and debugging
            purposes.
        """

        if self._ws is None:
            raise RuntimeError("Client is not connected")

        message_id = str(uuid.uuid4())
        request = [2, message_id, action, payload]
        await self._ws.send(json.dumps(request))

        raw_response = await self._ws.recv()
        response = json.loads(raw_response)
        # OCPP result frames are of the form [3, message_id, payload]
        if return_message_id:
            return response[2], message_id
        return response[2]

    async def boot_notification(self) -> None:
        """Send a BootNotification and schedule periodic heartbeats."""
        payload = {
            "chargePointModel": self.charger_model,
            "chargePointVendor": "Unknown"
        }
        resp = await self._call("BootNotification", payload)
        interval = int(resp.get("interval", 0)) or 60
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))

    async def _heartbeat_loop(self, interval: int) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                await self._call("Heartbeat", {})
        except asyncio.CancelledError:
            pass

    async def authorize(self, id_tag: str) -> dict:
        """Send an Authorize request for the given idTag."""
        payload = {"idTag": id_tag}
        return await self._call("Authorize", payload)

    async def status_notification(
        self,
        connector_id: int,
        status: str,
        error_code: str = "NoError",
    ) -> dict:
        """Notify the central system about connector status changes."""
        payload = {
            "connectorId": connector_id,
            "status": status,
            "errorCode": error_code,
            "timestamp": datetime.utcnow().isoformat(),
        }
        return await self._call("StatusNotification", payload)

    async def start_transaction(
        self, connector_id: int, id_tag: str, meter_start: int
    ) -> dict:
        try:
            auth = await self.authorize(id_tag)
            status = auth.get("idTagInfo", {}).get("status")
            if status and status != "Accepted":
                return auth
        except Exception:
            logger.warning("Authorize failed; proceeding with StartTransaction")

        payload = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": meter_start,
            "timestamp": datetime.utcnow().isoformat(),
        }
        resp = await self._call("StartTransaction", payload)
        tx_id = resp.get("transactionId")
        if tx_id is not None:
            self._active_tx = {
                "id": tx_id,
                "id_tag": id_tag,
                "connector_id": connector_id,
            }
            self._last_meter = meter_start
            try:
                await self.status_notification(connector_id, "Charging")
            except Exception:
                logger.debug("StatusNotification failed", exc_info=True)
        return resp

    async def stop_transaction(
        self,
        transaction_id: int,
        id_tag: str,
        meter_stop: int,
        reason: str | None = None,
    ) -> dict:
        payload = {
            "transactionId": transaction_id,
            "idTag": id_tag,
            "meterStop": meter_stop,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if reason:
            payload["reason"] = reason
        try:
            connector_id = self._active_tx.get("connector_id", 1) if self._active_tx else 1
            await self.status_notification(connector_id, "Finishing")
        except Exception:
            logger.debug("StatusNotification failed", exc_info=True)
        resp = await self._call("StopTransaction", payload)
        if self._active_tx and self._active_tx.get("id") == transaction_id:
            self._active_tx = None
            try:
                connector_id = connector_id
                await self.status_notification(connector_id, "Available")
            except Exception:
                logger.debug("StatusNotification failed", exc_info=True)
        return resp

    async def send_meter_values(
        self,
        transaction_id: int,
        connector_id: int,
        sample: dict,
    ) -> dict:
        """Send a MeterValues message for the given sample."""

        entry = {
            "timestamp": sample.get("timestamp", datetime.utcnow().isoformat()),
            "sampledValue": [],
        }

        mapping = {
            "current": "Current.Import",
            "voltage": "Voltage",
            "soc": "SoC",
            "temperature": "Temperature",
            "energy": "Energy.Active.Import.Register",
        }

        for key, measurand in mapping.items():
            value = sample.get(key)
            if value is not None:
                entry["sampledValue"].append({"value": str(value), "measurand": measurand})
                if key == "energy":
                    try:
                        self._last_meter = int(value)
                    except Exception:
                        pass

        payload = {
            "transactionId": transaction_id,
            "connectorId": connector_id,
            "meterValue": [entry],
        }
        resp = await self._call("MeterValues", payload)
        return resp

    async def data_transfer(
        self,
        vendor_id: str,
        message_id: str,
        data: dict | str,
        *,
        debug: bool = False,
    ) -> dict:
        """Send a DataTransfer request and log useful metadata.

        Parameters
        ----------
        vendor_id: str
            Vendor identification.
        message_id: str
            Message identifier.
        data: dict | str
            Payload to be sent.  It will be serialized to JSON before
            transmission.
        debug: bool, optional
            When ``True`` the sanitized payload will be logged at debug level
            for troubleshooting.
        """

        serialized = json.dumps(data)
        payload = {
            "vendorId": vendor_id,
            "messageId": message_id,
            "data": serialized,
        }

        resp, req_id = await self._call(
            "DataTransfer", payload, return_message_id=True
        )
        status = resp.get("status")
        payload_size = len(serialized)
        logger.info(
            "DataTransfer req=%s vendor=%s message=%s size=%d status=%s",
            req_id,
            vendor_id,
            message_id,
            payload_size,
            status,
        )
        if debug:
            sanitized = serialized.replace("\n", " ")
            if len(sanitized) > 2000:
                sanitized = sanitized[:2000] + "..."  # truncate long payloads
            logger.debug("DataTransfer payload (sanitized): %s", sanitized)
        return resp

    async def send_csv_log(self, csv_path: str) -> dict:
        def sanitize(value: object) -> str:
            return str(value).strip()

        records = []
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(
                    {
                        "timestamp": sanitize(row.get("Timestamp", "")),
                        "sender": sanitize(row.get("sender", "")),
                        "title": sanitize(row.get("Title", "")),
                        "detail": sanitize(row.get("Detail", "")),
                    }
                )
        return await self.data_transfer(
            "com.yourco.logs", "CsvLog", records
        )

    async def on_remotestarttransaction(self, payload: dict) -> dict:
        """Handle a RemoteStartTransaction request by starting a transaction."""
        id_tag = payload.get("idTag")
        connector_id = payload.get("connectorId", 1)
        if not id_tag or self._active_tx:
            return {"status": "Rejected"}

        asyncio.create_task(
            self.start_transaction(connector_id, id_tag, self._last_meter)
        )
        return {"status": "Accepted"}

    async def on_remotestoptransaction(self, payload: dict) -> dict:
        """Handle a RemoteStopTransaction request by stopping the transaction."""
        tx_id = payload.get("transactionId")
        if not self._active_tx or (
            tx_id is not None and tx_id != self._active_tx.get("id")
        ):
            return {"status": "Rejected"}

        id_tag = self._active_tx.get("id_tag", "")
        asyncio.create_task(
            self.stop_transaction(self._active_tx["id"], id_tag, self._last_meter, reason="Remote")
        )
        return {"status": "Accepted"}

    async def on_reset(self, payload: dict) -> dict:
        """Handle a Reset request and simulate the reset process."""
        reset_type = payload.get("type")
        logger.info(f"← Reset request type={reset_type}")
        if reset_type not in ("Hard", "Soft"):
            return {"status": "Rejected"}

        reason = "HardReset" if reset_type == "Hard" else "SoftReset"
        if self._active_tx:
            await self.stop_transaction(
                self._active_tx["id"],
                self._active_tx.get("id_tag", ""),
                self._last_meter,
                reason=reason,
            )

        asyncio.create_task(self._perform_reset(reset_type))
        return {"status": "Accepted"}

    async def _perform_reset(self, reset_type: str) -> None:
        """Simulate a hard or soft reset of the client."""
        await asyncio.sleep(1)
        logger.info(f"Simulating {reset_type} reset")
        if reset_type == "Hard":
            await self.close()
            await asyncio.sleep(1)
            await self.connect()
        else:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None
            self._active_tx = None
            await self.boot_notification()

    async def on_changeavailability(self, payload: dict) -> dict:
        """Handle a ChangeAvailability request from the central system.

        The charge point simulates the transition by sending a corresponding
        StatusNotification for the targeted connector.  Only "Operative" and
        "Inoperative" types are recognized; any other value results in a
        rejection.
        """

        connector_id = int(payload.get("connectorId", 0))
        availability_type = payload.get("type")
        logger.info(
            f"\u2190 ChangeAvailability connector={connector_id} type={availability_type}"
        )
        if availability_type not in ("Operative", "Inoperative"):
            return {"status": "Rejected"}

        status = "Available" if availability_type == "Operative" else "Unavailable"
        try:
            await self.status_notification(connector_id, status)
        except Exception:
            logger.debug("StatusNotification failed", exc_info=True)
        return {"status": "Accepted"}