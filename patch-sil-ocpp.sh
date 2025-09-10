#!/usr/bin/env bash
set -euo pipefail

YAML="${HOME}/everest-ws/everest-core/config/config-sil-ocpp.yaml"
OCPP_JSON="${HOME}/everest-ws/everest-core/config/ocpp/config-docker.json"

if [[ ! -f "$YAML" ]]; then
  echo "ERROR: YAML not found: $YAML" >&2
  exit 1
fi

# 1) สำรองไฟล์เดิม
TS="$(date +%Y%m%d-%H%M%S)"
cp -a "$YAML" "${YAML}.bak.${TS}"

# 2) แพตช์ YAML: ลบ iso15118_* ทั้งบล็อก + อ้างอิง และตัดคีย์ hlc:/ev: ที่กลวง
python3 - <<'PY'
import os, re, pathlib

yaml_path = pathlib.Path(os.path.expanduser("~/everest-ws/everest-core/config/config-sil-ocpp.yaml"))
lines = yaml_path.read_text().splitlines()

def indent(s: str) -> int:
    return len(s) - len(s.lstrip(' '))

out = []
i = 0
n = len(lines)

while i < n:
    line = lines[i]

    # ลบทั้งบล็อก iso15118_car: หรือ iso15118_charger:
    if re.match(r'^\s*iso15118_(?:car|charger):\s*$', line):
        base = indent(line)
        i += 1
        while i < n and (lines[i].strip() == '' or indent(lines[i]) > base):
            i += 1
        continue

    # ลบคีย์ hlc:/ev: ทั้งบล็อกถ้าข้างในอ้างถึง iso15118_* เท่านั้น
    m = re.match(r'^(\s*)(hlc|ev):\s*$', line)
    if m:
        key_indent = indent(line)
        j = i + 1
        only_iso = True
        saw_child = False
        while j < n and (lines[j].strip() == '' or indent(lines[j]) > key_indent):
            if lines[j].strip():
                saw_child = True
                if not re.search(r'iso15118_(?:car|charger)', lines[j]):
                    only_iso = False
            j += 1
        if saw_child and only_iso:
            # ข้ามทั้งบล็อกคีย์นี้
            i = j
            continue
        else:
            # เก็บคีย์ไว้ แต่จะกรองรายการ iso15118_* ด้านล่างทีละบรรทัด
            out.append(line)
            i += 1
            continue

    # ลบทุกบรรทัดที่ยังมีการอ้างอิงถึง iso15118_*
    if re.search(r'iso15118_(?:car|charger)', line):
        i += 1
        continue

    out.append(line)
    i += 1

# แทนที่ /home/$USER ด้วยโฮมจริง (Everest ไม่ขยายตัวแปรใน YAML)
text = "\n".join(out) + "\n"
home = os.path.expanduser("~")
text = text.replace("/home/$USER", home)

yaml_path.write_text(text)
PY

# 3) แจ้งผลการลบ
if grep -nE 'iso15118_(car|charger)' "$YAML" >/dev/null 2>&1; then
  echo "WARN: ยังพบ iso15118_* ในไฟล์ ${YAML} โปรดตรวจสอบด้วยตนเอง" >&2
else
  echo "OK: ลบ iso15118_car/iso15118_charger และอ้างอิงทั้งหมดแล้ว"
fi

# 4) สร้างไฟล์ OCPP config ขั้นต่ำถ้ายังไม่มี (ให้แก้ CentralSystemURI ภายหลัง)
if [[ ! -f "$OCPP_JSON" ]]; then
  mkdir -p "$(dirname "$OCPP_JSON")"
  cat > "$OCPP_JSON" <<'JSON'
{
  "Core": {
    "ChargePointId": "EVSE_SIM_01",
    "CentralSystemURI": "ws://127.0.0.1:9000/ocpp",
    "AuthorizeRemoteTxRequests": true,
    "HeartbeatIntervalS": 30,
    "MeterValueSampleIntervalS": 10,
    "Connectors": [
      { "id": 1, "txAllowed": true },
      { "id": 2, "txAllowed": true }
    ]
  },
  "Websocket": {
    "PingIntervalS": 30,
    "ConnectionTimeoutS": 30
  },
  "Security": {
    "UseTLS": false,
    "VerifyServer": false
  },
  "Logging": {
    "EnableMessageLogging": false
  }
}
JSON
  echo "OK: สร้าง ${OCPP_JSON} แล้ว (ปรับ CentralSystemURI ให้ตรง CSMS ของคุณได้)"
else
  echo "SKIP: พบไฟล์ ${OCPP_JSON} อยู่แล้ว"
fi

echo "DONE. Backup: ${YAML}.bak.${TS}"
