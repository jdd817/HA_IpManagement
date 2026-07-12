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
├── config_flow.py         # single-instance "Add Integration" flow (no user
│                           # input needed — just enables the component)
├── const.py
├── storage.py              # Subnet CRUD over HA's Store helper
├── subnet_utils.py          # ipaddress-based CIDR/range/nesting logic
├── device_matcher.py         # discovers device/entity IPs, maps to subnets
├── websocket_api.py           # ws commands consumed by the frontend panel
└── www/                       # built frontend bundle (panel + mgmt screen)
    └── ip-management-panel.js

tests/
├── test_subnet_utils.py
├── test_storage.py
└── test_device_matcher.py
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
  - `ip_management/subnets/save` → create/update (validates CIDR + nesting)
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
  parent_id: str | None    # points at containing Subnet, if nested
  label: str                # e.g. "Cameras", "IoT devices"
  item_type: str             # free-form category/tag shown in the UI
  notes: str | None
  created_at / updated_at
```

Validation rules (in `subnet_utils.py`, built on Python's `ipaddress`
module):

- `cidr` must parse as a valid `IPv4Network` (v6 out of scope for v1, see
  §7).
- If `parent_id` is set, the child network must be a strict subset of the
  parent's network (`child.subnet_of(parent)`), else reject with a clear
  error in the save response.
- Sibling overlap is *allowed* (a user may intentionally want two labels over
  the same range) but the UI will visually flag overlapping siblings.

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
`device_matcher.py` gathers candidates from several sources and picks the
best one per device:

1. `device_tracker` entities — `attributes.ip` / `attributes.ip_address`.
2. Config entry data — many integrations store `CONF_HOST` as an IP in
   `entry.data["host"]`; matched back to the device(s) created by that
   entry via the device registry.
3. Device registry `connections` — some integrations register
   `dr.CONNECTION_NETWORK_MAC` today; this data source is queried but is
   expected to be sparse in v1.

Each candidate IP is matched to the **most specific** subnet that contains
it (smallest prefix-length-wins, i.e. a `/32` beats a `/24`). Devices with no
resolvable IP are listed in an "Unmatched devices" section in the UI rather
than silently dropped, with a manual override to associate a device with a
subnet directly (stored as an entry in the same storage file, keyed by
device_id) — this covers the integrations that don't expose IP anywhere.

This heuristic nature is a known limitation and should be called out to the
user up front rather than promised as 100% automatic (see open questions).

## 5. UI/UX Flows

### Utilized IPs screen (the sidebar link itself)

- Tree/table of subnets, nested rows indented to match `parent_id` chains.
- Each row: label, item_type badge, CIDR block, last-octet range, device
  count.
- Expand a row → list of matched devices (name, entity/device link back
  into HA, resolved IP).
- Top-right 3-dot (`ha-icon-button` with `mdi:dots-vertical`) opens a menu
  with a single primary action: **"Manage subnets"** → switches the panel's
  internal route to the management screen (no new sidebar entry).

### Subnet management screen

- Flat/nested list with inline edit + delete per row, and an "Add subnet"
  action.
- Form fields: CIDR (validated live using the same `subnet_utils` logic,
  mirrored in JS or validated via a debounced websocket call), parent
  subnet (searchable dropdown, defaults to "no parent"/top level), label,
  item type, notes.
- Back button / breadcrumb returns to the main dashboard.

### Frontend implementation notes

- Built with `LitElement` (same stack HA's own frontend uses), hand-written
  — no heavy framework needed for two views and a handful of components.
- Shipped as a single bundled JS file (esbuild) registered as a static path
  under `/ip_management_panel/` and loaded via `panel_custom`.

## 6. Suggested Build Order

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

## 7. Open Questions / Assumptions

- **IPv4 only for v1** — confirm this is acceptable; IPv6 nesting/CIDR
  math is meaningfully different and can be a v2 addition.
- **Single HA instance / no multi-user permissions model** beyond HA's own
  admin-only panel visibility — anyone who can see the sidebar can edit
  subnets.
- Device→IP matching will not be complete for every integration; the plan
  leans on a manual-override list to fill gaps rather than promising full
  auto-discovery.
