# API Endpoints

เอกสารนี้สรุป REST API หลักของ ChargeBridge พร้อมตัวอย่าง `curl` ที่สามารถใช้งานได้จริง (เปลี่ยน `HOST` เป็นโดเมน/IP ของเซิร์ฟเวอร์)

## สถานีและหัวชาร์จ
| Method | Path | อธิบาย | ตัวอย่าง |
|-------|------|--------|----------|
| `POST` | `/api/v1/stations` | เพิ่มสถานีใหม่ | `curl -X POST http://HOST:8080/api/v1/stations -H 'Content-Type: application/json' -d '{"name":"Demo","location":"BKK"}'`<br>`{"id":1,"name":"Demo","location":"BKK","connectors":[]}` |
| `GET` | `/api/v1/stations` | รายชื่อสถานีพร้อมสถานะโดยรวม | `curl http://HOST:8080/api/v1/stations`<br>`[{"id":1,"name":"Gresgying02","connectors":[{"id":1,"status":"Available"}]}]` |
| `GET` | `/api/v1/stations/{stationId}` | รายละเอียดสถานีและหัวชาร์จทุกตัว | `curl http://HOST:8080/api/v1/stations/1`<br>`{"id":1,"name":"Gresgying02","connectors":[{"id":1,"status":"Available"}]}` |
| `DELETE` | `/api/v1/stations/{stationId}` | ลบสถานีหนึ่ง | `curl -X DELETE http://HOST:8080/api/v1/stations/1`<br>`{"ok":true}` |
| `GET` | `/api/v1/status` | สถานะปัจจุบันของทุกหัวชาร์จที่เชื่อมต่อ | `curl http://HOST:8080/api/v1/status`<br>`{"connectors":[{"cpid":"Gresgying02","connectorId":1,"status":"Available"}]}` |
| `GET` | `/api/v1/overview` | รวมสถานะพร้อมข้อมูล pending/active (แสดง VID ที่สร้างอัตโนมัติเมื่อเสียบรถ) | `curl http://HOST:8080/api/v1/overview`<br>`{"connectors":[{"cpid":"Gresgying02","connectorId":1,"status":"Preparing","pending":{"vid":"VID:XYZ","mac":"AA:BB"}}]}` |
| `GET` | `/api/v1/health` | ตรวจสอบสถานะของเซิร์ฟเวอร์ | `curl http://HOST:8080/api/v1/health`<br>`{"ok":true,"time":"2024-01-01T00:00:00Z"}` |

## การจัดการเซสชัน (เชื่อมต่อ OCPP)
| Method | Path | อธิบาย | ตัวอย่าง |
|-------|------|--------|----------|
| `POST` | `/api/v1/start` | สั่งเริ่มชาร์จผ่าน OCPP | `curl -X POST http://HOST:8080/api/v1/start -H 'Content-Type: application/json' -d '{"cpid":"Gresgying02","connectorId":1,"id_tag":"VID:FCA47A147858"}'`<br>`{"ok":true,"message":"RemoteStartTransaction sent"}` |
| `POST` | `/api/v1/stop` | สั่งหยุดชาร์จโดยใช้ `transactionId` หรือ `connectorId` | `curl -X POST http://HOST:8080/api/v1/stop -H 'Content-Type: application/json' -d '{"cpid":"Gresgying02","transactionId":1}'`<br>`{"ok":true,"transactionId":1,"message":"RemoteStopTransaction sent"}` |
| `POST` | `/charge/stop` | หยุดชาร์จโดยใช้ `connectorId` เท่านั้น | `curl -X POST http://HOST:8080/charge/stop -H 'Content-Type: application/json' -d '{"cpid":"Gresgying02","connectorId":1}'`<br>`{"ok":true,"transactionId":1,"message":"RemoteStopTransaction sent"}` |
| `POST` | `/api/v1/release` | ปลดล็อกหัวชาร์จ (กรณีไม่มีเซสชัน active) | `curl -X POST http://HOST:8080/api/v1/release -H 'Content-Type: application/json' -d '{"cpid":"Gresgying02","connectorId":1}'`<br>`{"ok":true,"message":"UnlockConnector sent"}` |
| `POST` | `/api/v1/availability` | เปลี่ยนสถานะ Available/Unavailable | `curl -X POST http://HOST:8080/api/v1/availability -H 'Content-Type: application/json' -d '{"cpid":"Gresgying02","connectorId":1,"available":true}'`<br>`{"ok":true,"status":"Accepted"}` |
| `POST` | `/api/v1/reset` | สั่งรีเซ็ตชาร์จเจอร์ (`type` = Hard/Soft) | `curl -X POST http://HOST:8080/api/v1/reset -H 'Content-Type: application/json' -d '{"cpid":"Gresgying02","type":"Soft"}'`<br>`{"ok":true,"status":"Accepted"}` |
| `GET` | `/api/v1/active` | เซสชันที่กำลังชาร์จอยู่ทั้งหมด | `curl http://HOST:8080/api/v1/active`<br>`{"sessions":[{"cpid":"Gresgying02","connectorId":1,"vehicleId":"VID:XYZ","mac":"AA:BB","transactionId":1}]}` |
| `GET` | `/api/v1/history` | เซสชันที่สิ้นสุดแล้ว | `curl http://HOST:8080/api/v1/history`<br>`{"sessions":[{"cpid":"Gresgying02","connectorId":1,"vehicleId":"VID:XYZ","mac":"AA:BB","transactionId":1,"energy":1200}]}` |
| `GET` | `/api/v1/pending` | เซสชันที่กำลังรอการเริ่มชาร์จ (ระบบสร้าง VID อัตโนมัติเมื่อเสียบรถ) | `curl http://HOST:8080/api/v1/pending`<br>`[{"station_id":"Gresgying02","connector_id":1,"id_tag":"VID:FCA47A147858","vid":"VID:FCA47A147858","mac":"AA:BB","created_at":"2024-01-01T00:00:00"}]` |

## In‑Memory Session (ไม่ส่ง OCPP)
| Method | Path | อธิบาย | ตัวอย่าง |
|-------|------|--------|----------|
| `POST` | `/api/v1/sessions/{connectorId}/start` | เริ่มชาร์จในหน่วยความจำ (ต้องระบุ `vehicleId`) | `curl -X POST http://HOST:8080/api/v1/sessions/1/start -H 'Content-Type: application/json' -d '{"vehicleId":"VID:FCA47A147858"}'`<br>`{"transactionId":42}` |
| `POST` | `/api/v1/sessions/{connectorId}/stop` | ยุติการชาร์จ (ต้องส่ง `kWhDelivered`) | `curl -X POST http://HOST:8080/api/v1/sessions/1/stop -H 'Content-Type: application/json' -d '{"kWhDelivered":5.3}'`<br>`{"session":{"id":42,"connector_id":1,"kWhDelivered":5.3,"status":"completed"}}` |
| `GET` | `/api/v1/sessions/{vehicleId}` | ดูสถานะและประวัติของรถคันหนึ่ง | `curl http://HOST:8080/api/v1/sessions/VID:FCA47A147858`<br>`{"current":null,"history":[{"id":42,"connector_id":1,"kWhDelivered":5.3}]}` |

## เครื่องมือจำลองการเสียบ/ถอดสาย (optional)
ใช้สำหรับทดลองเท่านั้น (ปกติรันบนพอร์ต 7071)
```bash
curl -X POST http://HOST:7071/plug/1     # จำลองการเสียบที่หัว 1
curl -X POST http://HOST:7071/unplug/1   # จำลองการถอดหัว 1
```

> **หมายเหตุ:** ตัวอย่างทั้งหมดไม่ต้องมีการตรวจสอบสิทธิ์ หากเปิดใช้งาน API Key ให้เพิ่ม `-H 'X-API-Key: <key>'`