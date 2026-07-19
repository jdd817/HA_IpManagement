# IP Management

A Home Assistant custom integration for tracking subnets on your home
network and seeing which registered devices are using an IP within each one.

- Define subnets as CIDR blocks, with an optional label/item type
  (e.g. "Cameras", "IoT"). Nesting is automatic — there's no parent field
  to set. If a subnet you add falls inside an existing one, it becomes that
  subnet's child; if it falls *between* two existing nested subnets, the
  hierarchy is re-inferred so the more specific one slots in underneath it.
- A sidebar link, **IP Management**, opens the *Utilized IPs* screen
  directly — a tree of your subnets (shown as CIDR + last-octet range)
  with the Home Assistant devices whose resolved IP falls inside each one.
- **Subnet Management** (add/edit/delete subnets) is reached from the
  3-dot menu on that screen — it is not a separate sidebar entry.

See [PLAN.md](PLAN.md) for the full architecture writeup.

## Installation

1. Copy `custom_components/ip_management` into your Home Assistant
   `config/custom_components/` directory (or add this repository as a
   custom HACS repository, category "Integration").
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **IP Management**.
   No configuration fields are needed; this just enables the sidebar panel.
4. Click **IP Management** in the sidebar to open the Utilized IPs screen,
   then use the 3-dot menu to add your first subnet.

## How device IPs are resolved

Home Assistant has no single canonical "device IP" field, so this
integration checks, in order of trust:

1. `device_tracker` entity attributes (`ip_address` / `ip`).
2. Config entry data (`host` / `ip_address` / `ip`) for the config entry
   that created the device.

Devices where neither source yields an IP show up under "Unmatched
devices" on the dashboard rather than being silently dropped. There is no
UI yet for manually overriding a device's subnet — see `storage.py`'s
`async_set_device_override`, which the websocket API exposes as
`ip_management/devices/set_override` for scripting/future UI work.

Each device row shows a small badge for which of the sources below found it.

## Manually assigning a device to an IP

Click any IP address on the dashboard — matched, unmatched, or marked
**⚠ unidentified** — to open a dialog for manually linking it to a
registered Home Assistant device. This works for every row, not just ones
discovery couldn't identify: if automatic matching ever gets an IP wrong,
you can correct it here.

The dialog's dropdown lists every device in Home Assistant, plus an
"Automatic (no manual assignment)" option. Pick a device and save to link
the IP to it; the row then shows a **🔗 manually linked** badge. Pick
"Automatic" and save to clear a manual link and let the normal
device_tracker/config-entry/scan matching take over again.

## Optional discovery (active scan + passive mDNS)

Both are off by default. Enable them from Settings → Devices & Services →
IP Management → **Configure**:

- **Active scan (ping sweep)** — pings every address in each subnet you've
  *registered in the panel and individually opted in* (see below — never a
  wider range, and including the subnet's network/broadcast addresses,
  since subnets here are arbitrary ranges rather than classful networks),
  then reads the system ARP/neighbor table to get a MAC address for
  whatever responds. Runs on a timer; the interval is configurable in the
  same options screen (default **24 hours**). Subnets larger than 512
  addresses are skipped (and logged) rather than scanned, so a mistakenly
  huge CIDR can't flood the network.

  Turning this on in Configure only enables the feature — it doesn't scan
  anything by itself. Each subnet also needs its own opt-in: open it in
  **Subnet Management** and check "Include in active scan". This lets you
  turn scanning on globally but limit it to just the subnets that actually
  need it (e.g. an IoT subnet) rather than sweeping everything you've
  registered.
- **Passive discovery (mDNS)** — listens for mDNS/Bonjour announcements
  (HomeKit, Chromecast, AirPlay, network printers, etc.) via Home Assistant's
  shared zeroconf instance. Sends no traffic of its own, so it isn't limited
  to registered subnets, but only sees devices that advertise under one of a
  curated list of service types (`const.ZEROCONF_SERVICE_TYPES`) — not a
  full network inventory.

Either result is matched back to an existing Home Assistant device by MAC
address when possible; otherwise it shows up as a newly-discovered,
unregistered device, marked with a **⚠ unidentified** badge so it's clear
at a glance that this is an IP that responded to a scan without Home
Assistant being able to say what device it actually is. **Neither ever
overrides `device_tracker`/config-entry data Home Assistant already has**
— they only fill in devices those sources couldn't find.

## Known limitations (v1)

- IPv4 only.
- Device-to-IP matching is heuristic, not guaranteed complete — see above.
- Anyone who can see the sidebar panel (any HA user, since
  `require_admin=True` restricts it to admins) can edit subnets; there is
  no finer-grained permission model.

## Development

```bash
python -m venv .venv
.venv/Scripts/activate   # or `source .venv/bin/activate` on macOS/Linux
pip install -r requirements_test.txt
pytest
```
