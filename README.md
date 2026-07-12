# IP Management

A Home Assistant custom integration for tracking subnets on your home
network and seeing which registered devices are using an IP within each one.

- Define subnets as CIDR blocks, with an optional label/item type
  (e.g. "Cameras", "IoT"), and nest subnets inside one another.
- A sidebar link, **IP Management**, opens the *Utilized IPs* screen
  directly — a tree of your subnets (shown as CIDR + last-octet range)
  with the Home Assistant devices whose resolved IP falls inside each one.
- **Subnet Management** (add/edit/delete/nest subnets) is reached from the
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
