# CAN Bus Setup Guide

This document explains how to configure two independent CAN interfaces on a Raspberry Pi 5:

* **can0** – ODrive S1 via Waveshare MCP2515 CAN HAT (SPI) at 250 kbps
* **can1** – Moteus R4.11 via MJBots FDCAN‑USB adapter at 500 kbps

---

## 1) Prerequisites

```bash
sudo apt update
sudo apt install can-utils   # provides candump, cansend, slcand
```

Ensure SPI is enabled in `raspi-config` (Interface Options → SPI).

---

## 2) Configure can0 (MCP2515 HAT)

1. **Enable Device-Tree overlays**
   Add to `/boot/firmware/config.txt`:

   ```ini
   dtparam=spi=on
   dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
   dtoverlay=can0-socketcan
   ```

   Adjust `interrupt=` GPIO pin if different.

2. **Reboot**

   ```bash
   sudo reboot
   ```

3. **Bring up interface**

   ```bash
   sudo ip link set can0 up type can bitrate 250000
   ```

4. **Verify**

   ```bash
   ip -details link show can0
   candump can0 -n 5
   ```

   * Should show `state UP`, `ERROR-ACTIVE`, bitrate 250000
   * candump should display ODrive heartbeat (ID 0x01) etc.

5. **Automate on boot**
   Create `/etc/systemd/system/can0.service`:

   ```ini
   [Unit]
   Description=Activate can0 (MCP2515 HAT)
   After=network.target

   [Service]
   Type=oneshot
   ExecStart=/usr/bin/ip link set can0 up type can bitrate 250000
   RemainAfterExit=yes

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable can0.service
   ```


---

## 3) Configure can1 (FDCAN-USB Adapter)

1. **Identify adapter by-id**

   ```bash
   ls -l /dev/serial/by-id | grep fdcanusb
   # e.g. usb-mjbots_fdcanusb_E6F9844A-if00 -> ../../ttyACM1
   ```

2. **Bridge via slcand**

   ```bash
   sudo slcand -o -c -s6 /dev/serial/by-id/usb-mjbots_fdcanusb_E6F9844A-if00 slcan0
   ```

   * `-s6` → 500 kbps

3. **Rename & bring up**

   ```bash
   sudo ip link set slcan0 down
   sudo ip link set slcan0 name can1
   sudo ip link set can1 up type can bitrate 500000
   ```

4. **Verify**

   ```bash
   ip -details link show can1
   candump can1 -n 5
   ```

   * Should show `state UP`, `ERROR-ACTIVE`, bitrate 500000

5. **Automate on boot**
   Create `/etc/systemd/system/slcan0.service`:

   ```ini
[Unit]
Description=Bridge MJBots FDCAN-USB → can1
After=network.target

[Service]
Type=forking
ExecStartPre=/bin/sh -c '\
  i=0; \
  while [ $i -lt 30 ] && [ ! -e /dev/serial/by-id/usb-mjbots_fdcanusb_E6F9844A-if00 ]; do \
    i=$((i+1)); sleep 0.1; \
  done; \
  [ -e /dev/serial/by-id/usb-mjbots_fdcanusb_E6F9844A-if00 ] \
'
ExecStart=/usr/bin/slcand -o -c -s6 \
  /dev/serial/by-id/usb-mjbots_fdcanusb_E6F9844A-if00 can1
ExecStartPost=/bin/sh -c 'sleep 0.1 && ip link set can1 up type can bitrate 500000'
ExecStop=/usr/bin/ip link set can1 down
KillMode=control-group
Restart=on-failure
TimeoutStartSec=15
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable slcan0.service
   ```

---

## 4) Testing Both Buses

* **Loopback test on each**:

  ```bash
  candump can0 &
  cansend can0 123#deadbeef

  candump can1 &
  cansend can1 123#deadbeef
  ```
* **Error counters**:

  ```bash
  watch -n1 'ip -stats link show can0 | grep berr-counter'
  watch -n1 'ip -stats link show can1 | grep berr-counter'
  ```

If both interfaces come up, show frames, and have zero errors, your CAN topology is correctly configured.
