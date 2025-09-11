# Event Test Scenarios (Remote)

## คำสั่งทั่วไป
ตรวจสอบสถานะหัวชาร์จและจัดการสถานีพื้นฐาน

```bash
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/status
curl -X POST http://45.136.236.186:8080/api/v1/stations -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d '{"name":"Demo","location":"TheMansion"}'
curl -X POST http://45.136.236.186:8080/api/v1/reset -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d '{"cpid":"Gresgying02","type":"Soft"}'
curl -X DELETE http://45.136.236.186:8080/api/v1/stations/1 -H "X-API-Key: changeme-123"
```

## เหตุการณ์ที่ 1 – รถคันที่ 1 (idTag: VID:FCA47A147858) ใช้หัว Connector 1
```bash
curl -X POST http://45.136.236.186:7071/plug/1
curl -X POST http://45.136.236.186:8080/api/v1/start -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":1,\"id_tag\":\"VID:FCA47A147858\"}"
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/active
curl -X POST http://45.136.236.186:8080/api/v1/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"transactionId\":1}"
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/active
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/history
curl -X POST http://45.136.236.186:8080/charge/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":1}"
curl -X POST http://45.136.236.186:8080/api/v1/release -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":1}"
curl -X POST http://45.136.236.186:7071/unplug/1
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/health
```

## เหตุการณ์ที่ 2 – รถคันที่ 2 (idTag: VID:FCA47A147859) ใช้หัว Connector 2
```bash
curl -X POST http://45.136.236.186:7071/plug/2
curl -X POST http://45.136.236.186:8080/api/v1/start -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":2,\"id_tag\":\"VID:FCA47A147859\"}"
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/active
curl -X POST http://45.136.236.186:8080/api/v1/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"transactionId\":2}"
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/active
@@ -36,26 +36,26 @@ curl -X POST http://45.136.236.186:8080/charge/stop -H "Content-Type: applicatio
curl -X POST http://45.136.236.186:8080/api/v1/release -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":2}"
curl -X POST http://45.136.236.186:7071/unplug/2
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/health
```

## เหตุการณ์ที่ 3 – รถคันที่ 3 (idTag: VID:FCA47A147860 และ VID:FCA47A147861) ใช้หัว Connector 1 และ 2
```bash
curl -X POST http://45.136.236.186:7071/plug/1
curl -X POST http://45.136.236.186:7071/plug/2
curl -X POST http://45.136.236.186:8080/api/v1/start -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":1,\"id_tag\":\"VID:FCA47A147860\"}"
curl -X POST http://45.136.236.186:8080/api/v1/start -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":2,\"id_tag\":\"VID:FCA47A147861\"}"
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/active
curl -X POST http://45.136.236.186:8080/api/v1/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"transactionId\":3}"
curl -X POST http://45.136.236.186:8080/api/v1/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"transactionId\":4}"
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/active
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/history
curl -X POST http://45.136.236.186:8080/charge/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":1}"
curl -X POST http://45.136.236.186:8080/charge/stop -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":2}"
curl -X POST http://45.136.236.186:8080/api/v1/release -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":1}"
curl -X POST http://45.136.236.186:8080/api/v1/release -H "Content-Type: application/json" -H "X-API-Key: changeme-123" -d "{\"cpid\":\"Gresgying02\",\"connectorId\":2}"
curl -X POST http://45.136.236.186:7071/unplug/1
curl -X POST http://45.136.236.186:7071/unplug/2
curl -H "X-API-Key: changeme-123" http://45.136.236.186:8080/api/v1/health
```

> หมายเหตุ: ปรับค่า transactionId ให้ตรงกับที่ GET /api/v1/active รายงานในแต่ละเหตุการณ์ และหากมีปัญหาหยุดไม่สำเร็จให้ใช้ /charge/stop ตามด้วย /release ก่อนสั่ง unplug เสมอ