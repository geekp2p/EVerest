![Alt text](https://raw.githubusercontent.com/EVerest/EVerest/main/docs/img/everest_horizontal-color.svg)

[![OpenSSF Best Practices](https://bestpractices.coreinfrastructure.org/projects/6739/badge)](https://bestpractices.coreinfrastructure.org/projects/6739)

# What is it?

EVerest is a Linux Foundation backed open-source modular framework for setting
up a full stack environment for EV charging. The modular software architecture
fosters customizablility and lets you configure your dedicated charging
scenarios based on interchangeable modules. All communication is performed by
the lightweight and flexible MQTT message queueing service. EVerest will help
to speed the adoption to e-mobility by utilizing all the open-source advantages
for the EV charging world. It will also enable new features for local energy
management, PV-integration and many more!

# Table of Contents

- [Main Features](#main-features)
- [Build and Install](#build-and-install)
- [Dependencies](#dependencies)
- [Ubuntu Server Quick Start (EVSE Emulator + OCPP)](#ubuntu-server-quick-start-evse-emulator--ocpp)
- [Demonstrations](#demonstrations)
- [License](#license)
- [Documentation](#documentation)
- [Background](#background)
- [Governance](#governance)
- [Discussion and Development](#discussion-and-development)
- [Contributing to EVerest](#contributing-to-everest)

# Main Features

- IEC 6185
- DIN SPEC 70121
- ISO 15118: -2 and -20
- SAE J1772
- SAE J2847/2
- CHAdeMO (planned)
- GB/T (planned)
- MCS (planned)
- OCPP: 1.6, 2.0.1 and 2.1 (planned)
- Modbus
- Sunspec

For a more detailed view of the current, and planned features, please review the
EVerest [roadmap.](https://github.com/EVerest/everest/blob/main/tsc/ROADMAP.md)

# Build and Install

The source code and installation instructions are currently hosted within [everest-core.](https://github.com/EVerest/everest-core#readme)

# Dependencies

everest-core relies on EVerest Dependency Manager (EDM) to help orchestrate the
dependencies between the different repositories. Detailed EDM installation
instructions are found [here.](https://everest.github.io/nightly/dev_tools/edm.html#dependency-manager-for-everest)

## Full Stack Hardware Requirements

It is recommended to have at least 4GB of RAM available to build EVerest. More
CPU cores will optionally boost the build process, while requiring more RAM accordingly.

# Ubuntu Server Quick Start (EVSE Emulator + OCPP)

These steps prepare an Ubuntu Server for running the EVerest EV station emulator
with an OCPP client.

1. **Prepare the system**

   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y git curl wget unzip build-essential cmake ninja-build pkg-config
   ```

2. **Install Docker**

   ```bash
   sudo apt install -y ca-certificates curl gnupg lsb-release
   sudo mkdir -p /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt update
   sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
   sudo docker run hello-world
   ```

3. **Clone the dev environment and install EDM**

   ```bash
   git clone https://github.com/EVerest/everest-dev-environment.git ~/everest-dev-environment
   sudo apt install -y pipx
   pipx ensurepath && source ~/.bashrc
   pipx install ~/everest-dev-environment/dependency_manager
   edm --version
   ```

4. **Initialize a workspace and build EVerest Core**

   ```bash
   edm init --workspace ~/everest-ws
   sudo apt install -y libboost-all-dev libssl-dev libsqlite3-dev libcurl4-openssl-dev libcap2-dev libpcap-dev
   cd ~/everest-ws/everest-core
   mkdir -p build && cd build
   cmake -DCMAKE_POLICY_DEFAULT_CMP0167=OLD ..
   make -j"$(nproc)" install
   ```

5. **Install and test Mosquitto**

   ```bash
   sudo apt install -y mosquitto mosquitto-clients
   sudo systemctl enable --now mosquitto
   ss -ltnp | grep :1883
   mosquitto_sub -h 127.0.0.1 -p 1883 -t 'test' -v &
   mosquitto_pub -h 127.0.0.1 -p 1883 -t 'test' -m 'hello-everest'
   ```

6. **Configure OCPP**

   Create a custom OCPP configuration:

   ```bash
   mkdir -p ~/everest-ws/everest-core/config/ocpp
   cat > ~/everest-ws/everest-core/config/ocpp/config-docker.json <<'EOF'
   {
     "CentralSystemURI": "ws://45.136.236.186:9000/ocpp/CP001",
     "ChargePointId": "CP001",
     "SecurityProfile": 0,
     "AuthorizationKey": "",
     "HeartbeatInterval": 60,
     "MeterValueSampleInterval": 15,
     "ReconnectIntervalMsec": 5000,
     "ChargePointVendor": "EVerestSim",
     "ChargePointModel": "SIL-AC-1x32A",
     "FirmwareVersion": "2025.09"
   }
   EOF
   ```

   Point the OCPP module at this file by editing
   `~/everest-ws/everest-core/config/config-sil-ocpp.yaml` so the `ocpp`
   section reads:

   ```yaml
   ocpp:
     module: OCPP
     config_module:
       ChargePointConfigPath: /home/$USER/everest-ws/everest-core/config/ocpp/config-docker.json
   ```

   Then remove the ISO 15118 modules:

   ```bash
   sed -i '/^- \s*iso15118_car\s*$/d; /^- \s*iso15118_charger\s*$/d' \
     ~/everest-ws/everest-core/config/config-sil-ocpp.yaml
   ```

7. **Upgrade Python packages in the build virtual environment**

   ```bash
   ~/everest-ws/everest-core/build/venv/bin/python -m pip install --upgrade pip
   ~/everest-ws/everest-core/build/venv/bin/pip install 'pydantic<2' environs marshmallow cryptography
   ```

8. **Run the EVSE simulator**

   ```bash
   ~/everest-ws/everest-core/build/run-scripts/run-sil-ocpp.sh
   ```

   Logs are written to `/tmp/everest_ocpp_logs/`. A BootNotification from
   `CP001` should appear on the central system.

9. **Optional helper script**

   Create `~/everest-ws/everest-core/run-chargebridge-sim.sh` to launch the
   simulator with a custom ChargePoint ID:

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   CPID="${1:-ChargeBridge-SIM01}"
   CS_URI_BASE="ws://45.136.236.186:9000/ocpp"
   EVEREST_ROOT="$HOME/everest-ws/everest-core"
   BUILD_DIR="$EVEREST_ROOT/build"
   UCFG="$BUILD_DIR/dist/share/everest/modules/OCPP/user_config.json"
   [ -f "$UCFG.bak" ] || cp "$UCFG" "$UCFG.bak"
   python3 - "$UCFG" "$CPID" "$CS_URI_BASE" <<'PY'
import json, sys, pathlib
cfg = pathlib.Path(sys.argv[1])
cpid, base = sys.argv[2], sys.argv[3]
data = json.loads(cfg.read_text())
internal = data.setdefault("Internal", {})
security = data.setdefault("Security", {})
internal["CentralSystemURI"] = f"{base}/{cpid}"
internal["ChargePointId"] = cpid
security["SecurityProfile"] = 1
for k in ("CentralSystemURI", "ChargePointId", "SecurityProfile"):
    data.pop(k, None)
cfg.write_text(json.dumps(data, indent=2))
PY
   "$BUILD_DIR/run-scripts/run-sil-ocpp.sh"
   ```

   Make the script executable and run it:

   ```bash
   chmod +x ~/everest-ws/everest-core/run-chargebridge-sim.sh
   ~/everest-ws/everest-core/run-chargebridge-sim.sh LAB-CP-01
   ```

# Demonstrations

The current demos showcase the foundational layers of a charging solution that
could address interoperability and reliability issues in the industry. Check-out
the available demonstrations in the [US-JOET Repo](https://github.com/US-JOET/everest-demo).

# License

EVerest and its subprojects are licensed under the Apache License, Version 2.0.
See [LICENSE](https://github.com/EVerest/EVerest#:~:text=Version%202.0.%20See-,LICENSE,-for%20the%20full)
for the full license text.

# Documentation

The official EVerest documentation is hosted [here.](https://everest.github.io/nightly/)

# Background

The EVerest project was initiated by PIONIX GmbH to help with the
electrification of the mobility sector.

# Governance

EVerest is a project hosted by the [LF Energy Foundation.](https://lfenergy.org/)
This project's technical charter is located in [CHARTER.md](https://github.com/EVerest/EVerest/blob/main/tsc/CHARTER.md)