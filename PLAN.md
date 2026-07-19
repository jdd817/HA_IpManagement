# IP Management — Home Assistant Custom Integration Plan

## 1. Goal

A custom Home Assistant integration ("IP Management") that lets a user define
subnets (with an item/category label, e.g. "Cameras", "IoT", "Trusted"),
supports nesting subnets inside one another, and displays:

- A **sidebar panel** listing all subnets (as CIDR blocks + last-octet ranges)
  together with the Home Assistant devices/entities whose IP address falls
  inside each one.
- A **Subnet Management screen**, reachable from the 3-dot overflow menu on
  the main panel, for creating/editing/deleting/nesting subnets.

This is a native HA custom integration (`custom_components/ip_management/`),
not a standalone web app — it runs inside HA's process, uses HA's storage,
auth, and frontend-panel APIs, and is installable like any other
HACS-style custom component.

## 2. High-Level Architecture

```
custom_components/ip_management/
├── __init__.py            # setup, storage init, ws-api + panel registration
├── manifest.json
├── config_flow.py         # single-instance "Add Integration" flow, plus the
│                           # options flow (discovery toggles/interval, §5)
├── const.py
├── storage.py              # Subnet CRUD over HA's Store helper
├── subnet_utils.py          # ipaddress-based CIDR/range/nesting logic
├── device_matcher.py         # discovers device/entity IPs, maps to subnets
├── active_scanner.py          # optional: ping-sweeps registered subnets (§5)
├── passive_scanner.py          # optional: mDNS listening (§5)
├── coordinator.py               # DataUpdateCoordinator scheduling active_scanner
├── websocket_api.py               # ws commands consumed by the frontend panel
└── www/                             # frontend bundle (panel + mgmt screen)
    └── ip-management-panel.js

tests/
├── test_config_flow.py
├── test_subnet_utils.py
├── test_storage.py
├── test_device_matcher.py
├── test_active_scanner.py
├── test_passive_scanner.py
├── test_coordinator.py
└── test_websocket_api.py
```

### Backend building blocks

- **Storage**: `homeassistant.helpers.storage.Store` persisting a flat list of
  subnet records to `.storage/ip_management.subnets` as JSON. Flat storage
  (each record has a `parent_id`) rather than a nested tree on disk — the
  tree is derived at read time, which keeps re-parenting a subnet a
  single-field update.
- **Config entry**: one config-flow with no fields, purely so the integration
  shows up under Settings → Devices & Services and can be added/removed
  through the normal HA UI. All real configuration happens in the custom
  panel, not the config flow.
- **Websocket API** (`websocket_api.py`): the frontend panel is a
  privileged frontend-served script, so it talks to the backend via HA's
  websocket commands rather than REST. Commands:
  - `ip_management/subnets/list` → full subnet list with computed CIDR
    metadata
  - `ip_management/subnets/save` → create/update (validates the CIDR;
    nesting is inferred automatically, see §3 — there is no parent field
    to pass in)
  - `ip_management/subnets/delete`
  - `ip_management/devices/list` → devices/entities with a resolved IP and
    the most-specific subnet id they match
- **Panel registration**: `async_register_panel` (via
  `homeassistant.components.panel_custom`) registers a custom element served
  from `www/ip-management-panel.js`, with `sidebar_title="IP Management"`
  and an `mdi:lan` icon. **The sidebar link itself opens the Utilized IPs
  screen (§5) directly** — that is the panel's default/landing route.
  Subnet management is *not* a separate sidebar entry; it's a second
  internal route within the same custom element, reached only via the
  3-dot menu on the Utilized IPs screen, and navigating there swaps the
  panel's content in place (URL changes under the same sidebar item, e.g.
  `/ip-management/dashboard` → `/ip-management/subnets`).

## 3. Data Model

```python
Subnet:
  id: str                 # uuid
  cidr: str                # e.g. "192.168.10.0/24"
  parent_id: str | None    # system-computed; see below — never user-set
  label: str                # e.g. "Cameras", "IoT devices"
  item_type: str             # free-form category/tag shown in the UI
  notes: str | None
  active_scan_enabled: bool   # opt-in per subnet; default False — see §5
  created_at / updated_at
```

**Nesting is fully automatic — there is no parent field in the UI or the
save API.** `parent_id` is derived, on every save or delete, purely from
CIDR containment (`subnet_utils.infer_parent_ids`, applied in
`SubnetStore._recompute_hierarchy`):

- Each subnet's parent is the most specific *other* subnet that strictly
  contains its CIDR (smallest qualifying supernet wins). A subnet with no
  containing subnet has `parent_id = None` (top level).
- The full hierarchy is recomputed from scratch on every save/delete rather
  than patching just the affected subnet. That's what makes "insert a
  subnet between two existing ones" work for free: if a new subnet `mid`
  is added between an existing `grandparent` and `child` (i.e.
  `child ⊂ mid ⊂ grandparent`), recomputing finds `mid` as `child`'s new
  most-specific container and re-parents it automatically, no special-case
  code needed. Likewise, deleting a subnet re-parents its former children
  to whatever now most-specifically contains them (typically its own former
  parent).
- Validation is limited to `cidr` parsing as a valid `IPv4Network` (v6 out
  of scope for v1, see §7) — there's no "child outside parent" error case
  to guard against since nothing user-supplied describes the relationship.
- Sibling/overlapping CIDRs that don't nest (neither strictly contains the
  other) simply end up with no parent/child relationship between them;
  overlap warnings remain a future nice-to-have, not implemented in v1.

Derived/display fields (computed on read, never stored):

- **CIDR block string** — the raw `cidr` field, e.g. `192.168.10.0/24`.
- **Last-octet range** — computed from prefix length: for a `/24` that's
  `.0–.255`; for a `/28` starting at `.16` that's `.16–.31`; for anything
  with prefix < 24 (spans multiple third-octet blocks) the UI shows the
  full first/last host instead of just an octet range, since "last octet"
  stops being meaningful.
- **Depth / tree path** — used to render indentation in both the dashboard
  and management screen.

## 4. Matching Devices to Subnets

Home Assistant has no single canonical "device IP" field, so
`device_matcher.py` gathers candidates from a couple of built-in sources and
picks the best one per device:

1. `device_tracker` entities — `attributes.ip` / `attributes.ip_address`.
2. Config entry data — many integrations store `CONF_HOST` as an IP in
   `entry.data["host"]`; matched back to the device(s) created by that
   entry via the device registry.

Each candidate IP is matched to the **most specific** subnet that contains
it (smallest prefix-length-wins, i.e. a `/32` beats a `/24`). Devices with no
resolvable IP are listed in an "Unmatched devices" section in the UI rather
than silently dropped, with a manual override to associate a device with a
subnet directly (stored as an entry in the same storage file, keyed by
device_id) — this covers the integrations that don't expose IP anywhere.
`websocket_api.ws_list_devices` also folds in whatever the optional
active/passive scanners found (§5) as a *gap-fill only* on top of these two
sources — see §5 for how that merge is ordered.

This heuristic nature is a known limitation and should be called out to the
user up front rather than promised as 100% automatic (see open questions).

## 5. Active & Passive Discovery

Two optional features, both off by default, toggled via the config entry's
**options flow** (Settings → Devices & Services → IP Management →
Configure — `config_flow.IPManagementOptionsFlow`). Neither is exposed in
the custom panel itself; HA already renders a native options dialog for any
integration with an options flow, so no extra frontend work was needed for
the toggles themselves.

### Active scan (ping sweep)

- **Two-level opt-in.** The options-flow toggle only turns the coordinator
  on at all; it does *not* imply scanning every registered subnet. Each
  subnet also has its own `active_scan_enabled` flag (set from the Subnet
  Management form, default `False`), and `coordinator.scannable_subnets()`
  filters the store down to just those before a scan runs. This lets a user
  enable active scanning globally but restrict it to, say, just the IoT
  subnet, rather than sweeping every registered CIDR.
- **Scope**: only CIDRs the user has both registered as a subnet *and*
  opted in as above — never a wider network. `active_scanner.hosts_to_scan(cidr, max_hosts)`
  enumerates *every* address in the block, including the network and
  broadcast addresses (e.g. both `.32` and `.47` for a `/28` starting at
  `.32`) — subnets here are arbitrary user-defined ranges, not classful
  networks, and `subnet_utils.display_range` already shows the full range
  including those bookend addresses as part of the subnet, so the scan
  needs to match. Returns `None` (skip + log) if the block is more than
  `MAX_ACTIVE_SCAN_HOSTS_PER_SUBNET` (512) addresses, so an accidentally
  huge CIDR (e.g. a /8) can't turn into a network flood.
- **Mechanism**: `asyncio.create_subprocess_exec` to the system `ping`
  binary (bounded to `PING_CONCURRENCY` concurrent pings via a semaphore) —
  not raw ICMP sockets, which need root/`CAP_NET_RAW` that HA OS/Supervised
  containers typically don't grant custom integrations. Whatever responds is
  then correlated to a MAC address by reading the system ARP/neighbor table
  (`ip neigh show`, falling back to `arp -a`; Windows uses `arp -a` with its
  own output format) — `active_scanner.py`'s `parse_*_output` functions are
  pure and independently unit tested against sample output.
- **Scheduling**: `coordinator.ActiveScanCoordinator`, a
  `homeassistant.helpers.update_coordinator.DataUpdateCoordinator`, whose
  `update_interval` comes from the options flow's
  `active_scan_interval_hours` field (**default 24 hours**). Changing
  options triggers `hass.config_entries.async_reload` (via
  `entry.add_update_listener`), which is the simplest way to pick up a new
  interval or a toggle flip — no live coordinator-mutation logic needed.

### Passive discovery (mDNS)

- **Mechanism**: `passive_scanner.PassiveScanner` wraps a `zeroconf`
  library `AsyncServiceBrowser` bound to **Home Assistant's own shared
  zeroconf instance** (`homeassistant.components.zeroconf.async_get_async_instance`)
  rather than opening a second mDNS engine. It browses a curated, fixed list
  of common home/IoT service types (`const.ZEROCONF_SERVICE_TYPES` — HomeKit,
  Chromecast, AirPlay, printers, etc.), *not* a full dynamic
  service-type enumeration (that requires a separate `_services._dns-sd._udp`
  meta-query phase, deemed unnecessary complexity for v1).
- **Why not hook into HA's own `dhcp`/`zeroconf` discovery flows instead**:
  those components exist to trigger *other* integrations' config flows for
  service types/hostname patterns declared in advance via their manifests —
  there's no stable public "give me every device HA has passively seen" feed
  to subscribe to. Running our own listener on the shared instance is the
  supported extension point; duplicating a whole separate mDNS engine would
  waste sockets and duplicate HA's own traffic.
- **Threading note**: `AsyncServiceBrowser`'s handler callbacks run on the
  HA event loop (confirmed against the installed `zeroconf` library's own
  source/docstrings), so `hass.async_create_task(...)` can be called
  directly from the `add_service`/`update_service` callback without needing
  `call_soon_threadsafe`.
- Since this only *listens*, it isn't scoped to registered subnets and has
  no host-count cap — there's no outbound traffic to bound.

### Merging into device_matcher

Both scanners produce a `device_matcher.DiscoveredHost(ip, mac, name)` —
kept independent of device-registry lookups so neither scanner needs to
know about HA's registries. `DeviceMatcher.resolve_scan_result(host, source)`
turns one into a `DeviceIpInfo`: if `host.mac` matches an existing device
registry connection (`dr.CONNECTION_NETWORK_MAC`), it's attributed to that
real device (merging with, not duplicating, anything device_tracker/config
entry already found, and `DeviceIpInfo.device_matched = True`); otherwise
it gets a synthetic `scan:<ip>` id and `device_matched = False`, so it
still shows up as a newly-discovered device but is flagged as one HA
couldn't actually identify — the panel renders this as an "unidentified"
badge (see §6) rather than presenting it as an ordinary named device.
`device_tracker`/`config_entry` results always have `device_matched = True`
(the dataclass default), since they're derived from a real device_id by
construction.

`websocket_api.ws_list_devices` builds the merged set itself: start from
`DeviceMatcher.async_get_device_ips()` (device_tracker + config_entry),
then `dict.setdefault(...)` in resolved active-scan and passive-scan
results — `setdefault` is what guarantees scan results only *fill gaps* and
can never override a device HA's higher-trust sources already resolved.
`DeviceMatcher.async_match_devices_to_subnets` takes this pre-merged dict
via an optional `device_ips` parameter (defaulting to its own
`async_get_device_ips()` when omitted, so existing callers/tests are
unaffected).

### Manually assigning a device to any IP

Automatic resolution (device_tracker, config_entry, and scan MAC
correlation) doesn't always get it right — a device may not be in HA's
registry at all, may sit under a MAC HA never saw, or may simply be
misidentified. For that, `SubnetStore` keeps a second, separate mapping —
`ip_device_links: dict[ip_address, device_id]` — distinct from the existing
`device_overrides: dict[device_id, subnet_id]` (that one reassigns which
*subnet* a known device belongs to; this one assigns which *device* an *IP*
belongs to, and works for any IP, not just ones a scan couldn't identify).

The override is applied centrally rather than per-source:
`DeviceMatcher.apply_manual_ip_links(device_ips, ip_device_links)` runs
**last**, after device_tracker, config_entry, and both scanners have already
been merged into a single `device_ips` dict — so a manual assignment can
correct *any* IP's device attribution regardless of which source originally
resolved it. A link to a device_id no longer in the registry (e.g. deleted
from HA) is ignored, leaving that IP's existing resolution untouched. A
successful override produces `device_matched = True` plus
`DeviceIpInfo.manually_assigned = True`, which the panel uses to show a
distinct "manually linked" badge, as opposed to the plain source badge a
device_tracker/config_entry/MAC-based match gets.
`resolve_scan_result(host, source)` itself is unaware of manual links —
it still only does MAC correlation — keeping the two concerns separate.

The websocket command `ip_management/devices/assign_ip` (`ip_address`,
`device_id` — `None` clears the link) is the only way to set/clear this
mapping; `ws_list_devices` calls `apply_manual_ip_links` with
`store.ip_device_links` as the final step before matching devices to
subnets. The frontend gets the device list to populate the assignment
dialog's dropdown from HA's own core websocket command
`config/device_registry/list` rather than a custom backend endpoint, since
it just needs id/name for every registered device, not anything
IP-Management-specific.

## 6. UI/UX Flows

### Utilized IPs screen (the sidebar link itself)

- Tree/table of subnets, nested rows indented to match `parent_id` chains.
- Each row: label, item_type badge, CIDR block, last-octet range, device
  count.
- Expand a row → list of matched devices (name, entity/device link back
  into HA, resolved IP, and a small badge showing which source found it —
  tracker/config/active scan/mDNS). Entries with `device_matched: false`
  (an IP a scan found but couldn't tie to a real HA device — see §5) get an
  additional warning-styled "unidentified" badge, shown wherever a device
  row appears (this list and the "Unmatched devices" section below) — a
  distinct concept from "unmatched" (which is about subnet membership, not
  device identity), so the two badges use different wording on purpose.
- Every device row's IP address is clickable (in both this list and the
  "Unmatched devices" section) and opens a modal **assign-device dialog** —
  works the same whether the row is already matched, unidentified, or
  previously manually linked, since the manual override applies to any IP
  (see §5's manual assignment subsection). The dialog's `<select>` is
  populated from every HA device (via the core `config/device_registry/list`
  command) plus an "Automatic (no manual assignment)" option; it's
  pre-selected to the current manual link if one exists, otherwise
  "Automatic" even if a device is already shown for that row via some other
  source. Saving calls `ip_management/devices/assign_ip`; picking
  "Automatic" sends `device_id: null`, clearing any existing manual link.
  A manually-linked row shows a "manually linked" badge instead of (or
  alongside, if unidentified) the usual source badge — this is a per-IP
  link, so re-running discovery won't need it reassigned as long as the IP
  doesn't move to a different device.
- Top-right 3-dot (`ha-icon-button` with `mdi:dots-vertical`) opens a menu
  with a single primary action: **"Manage subnets"** → switches the panel's
  internal route to the management screen (no new sidebar entry).

### Subnet management screen

- Flat/nested list with inline edit + delete per row, and an "Add subnet"
  action.
- Form fields: CIDR (validated live using the same `subnet_utils` logic,
  mirrored in JS or validated via a debounced websocket call), label, item
  type, notes, and an "Include in active scan" checkbox (`active_scan_enabled`,
  off by default — see §5's two-level opt-in). No parent-subnet field —
  nesting is inferred automatically from the CIDR (see §3), and the list
  below the form still shows the resulting hierarchy via indentation.
- Subnets opted into active scanning show a small badge in both this list
  and the dashboard tree, so it's visible at a glance which subnets are
  covered.
- Back button / breadcrumb returns to the main dashboard.

### Frontend implementation notes

- Implemented (see `custom_components/ip_management/www/ip-management-panel.js`)
  as a dependency-free vanilla `HTMLElement`/Shadow DOM custom element rather
  than `LitElement` — for two views and a handful of components a build step
  (esbuild + `lit` dependency) added more moving parts than it saved, and a
  hand-written file ships as-is with no build/CI step required to keep the
  static asset in sync with source.
- Served as a static path (`/ip_management_static/`) registered in
  `__init__.py`, loaded via `panel_custom.async_register_panel`.

## 7. Suggested Build Order

1. Repo/project scaffolding, `manifest.json`, minimal `config_flow.py` that
   shows up as an installable integration doing nothing yet.
2. `subnet_utils.py` + unit tests (CIDR parsing, nesting validation,
   last-octet range computation) — pure Python, no HA dependency, fastest
   to get right first.
3. `storage.py` CRUD over `Store`, with unit tests.
4. `websocket_api.py` wiring subnet CRUD to the storage layer.
5. Minimal frontend: sidebar panel showing the subnet tree only (no
   devices yet), confirming panel registration + websocket plumbing works
   end-to-end.
6. Subnet management screen + 3-dot navigation.
7. `device_matcher.py` + "devices in this subnet" expansion in the
   dashboard, plus the manual-override path for unmatched devices.
8. Polish: overlap warnings, empty states, HACS packaging metadata.
9. Active/passive discovery (§5): options flow, `active_scanner.py` +
   `coordinator.py`, `passive_scanner.py`, then the `websocket_api.py`
   gap-fill merge and the source badge in the frontend — added after the
   core panel was already working end-to-end, since both are additive and
   off by default.

## 8. Open Questions / Assumptions

- **IPv4 only for v1** — confirm this is acceptable; IPv6 nesting/CIDR
  math is meaningfully different and can be a v2 addition.
- **Single HA instance / no multi-user permissions model** beyond HA's own
  admin-only panel visibility — anyone who can see the sidebar can edit
  subnets.
- Device→IP matching will not be complete for every integration; the plan
  leans on a manual-override list to fill gaps rather than promising full
  auto-discovery.
- **Active scan network reachability isn't guaranteed** — if HA runs on a
  VLAN/segment isolated from a registered subnet, pings will simply all
  fail (silently, not an error) rather than discover anything; there's no
  detection/warning for "this subnet is unreachable from HA" in v1.
- **Passive discovery coverage is only as good as the curated service-type
  list** (`const.ZEROCONF_SERVICE_TYPES`) — devices that don't advertise
  under one of those types are invisible to it. Expanding the list, or
  moving to full dynamic service-type enumeration, is a possible v2.
- Active scan's ARP-table read only sees hosts the OS *already* has an
  ARP/neighbor entry for — practically always true right after a
  successful ping, but the parsing is best-effort and platform-dependent
  (`ip neigh show` / `arp -a`, with a separate Windows `arp -a` format).
