# TODO (Alice)

Tasks for OCPP server enhancements compatible with existing `ChargeBridge` modules.

## 1. BootNotification and Heartbeat
- [ ] On client connect, send `BootNotification` with station metadata.
- [ ] Schedule periodic `Heartbeat` every `HeartbeatInterval` seconds.
- [ ] Reconnect automatically if no `Heartbeat` ack within `ConnectionTimeOut`.

## 2. Authorize prior to StartTransaction
- [ ] Before starting a session, call `Authorize` with the incoming `idTag`.
- [ ] Deny transaction when `AllowOfflineTxForUnknownId` is `false` and central system is unreachable.

## 3. MeterValues streaming
- [ ] Sample `Energy.Active.Import.Register`, `Current.Import`, `Voltage`, `Power.Active.Import`, `SoC`, `Temperature` every `MeterValueSampleInterval`.
- [ ] Send `MeterValues` during active sessions and record them to persistent storage.

## 4. Vendor-specific DataTransfer
- [ ] Implement handler to parse and respond to `DataTransfer` messages.
- [ ] Provide helper to send vendor-specific payloads (e.g., map MacID to VID).

## 5. Extend session data model
- [ ] Store additional sensor values (current, voltage, temperature, SoC) within session records.

---

### Codex commands for developers
Use the following shell commands while working under `ChargeBridge`:

```bash
# run unit tests
pytest

# launch central system mock
python ChargeBridge/central_server/main.py

# start local client for manual testing
python ChargeBridge/ocpp_client.py
```