# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (`custom_components/ip_management/`) for
tracking subnets on a home network and showing which registered HA devices
are using an IP within each one. It is not a standalone app — it runs
inside Home Assistant Core's process and is installed by copying the
integration directory into a real HA `config/custom_components/`.

See [PLAN.md](PLAN.md) for the full architecture writeup and [README.md](README.md)
for installation/user-facing behavior. Both should be kept in sync with
code changes — update them, don't just leave them as historical snapshots.

## Commands

```bash
python -m venv .venv
.venv/Scripts/activate          # .venv/bin/activate on macOS/Linux
pip install -r requirements_test.txt   # homeassistant + pytest

pytest                           # run the whole suite
pytest tests/test_subnet_utils.py -q          # one file
pytest tests/test_storage.py -q -k reparents  # one test by name

python -m py_compile custom_components/ip_management/*.py   # syntax/import sanity check
```

There is no build step for the frontend (see below) and no linter is
configured — `py_compile` plus the test suite is the sanity check used
throughout this repo's history.

## Architecture

### Backend (`custom_components/ip_management/`)

- **`subnet_utils.py`** — pure-Python CIDR math (`ipaddress`-based), no HA
  imports. This is the one module safe to unit-test in complete isolation.
  Notably: `infer_parent_ids()` computes the *entire* subnet parent/child
  hierarchy from scratch given a `{id: cidr}` mapping — each subnet's parent
  is the most specific *other* subnet that strictly contains it. There is no
  user-settable parent field anywhere in this codebase; nesting is always
  derived, never stored as input.
- **`storage.py`** (`SubnetStore`) — CRUD over HA's `Store` helper. Calls
  `_recompute_hierarchy()` (which wraps `infer_parent_ids`) after *every*
  save or delete, recomputing all subnets' `parent_id`, not just the one
  being changed. This is what makes inserting a subnet "between" two
  existing nested ones — or deleting one — reparent everything correctly
  without special-case code.
- **`device_matcher.py`** (`DeviceMatcher`) — resolves a device's IP from
  `device_tracker` entity attributes and config-entry `host`/`ip`/`ip_address`
  data (device_tracker wins when both exist), then matches each resolved IP
  to the most specific subnet via `subnet_utils.most_specific_match`. Its
  `async_*`-named methods are plain sync functions (HA naming convention,
  not a coroutine marker) — don't `await` them. Also defines
  `DiscoveredHost(ip, mac, name)`, the shared record type `active_scanner.py`
  /`passive_scanner.py` produce, and `resolve_scan_result(host, source)`,
  which turns one into a `DeviceIpInfo` by matching `host.mac` against the
  device registry's `CONNECTION_NETWORK_MAC` connections (falling back to a
  synthetic `scan:<ip>` id when there's no match). `DeviceIpInfo.device_matched`
  (default `True`) is set to `False` only for that synthetic-id case — it's
  what the panel's "unidentified" badge keys off of (see `www/ip-management-panel.js`
  below), distinct from subnet-membership matching ("Unmatched devices").
  `async_match_devices_to_subnets` takes an optional pre-merged `device_ips`
  dict (see `websocket_api.py` below) — omit it and it derives one itself
  via `async_get_device_ips()`, same as before this parameter existed.
- **`active_scanner.py`** (`ActiveScanner`, opt-in, two levels deep) —
  `async_scan(subnets)` ping-sweeps whatever subnet list it's handed; it has
  no opinion on *which* subnets that should be (`hosts_to_scan` only rejects
  a given subnet if it's over `MAX_ACTIVE_SCAN_HOSTS_PER_SUBNET` hosts, not
  based on any opt-in flag). Filtering to subnets the user actually opted
  into (`Subnet.active_scan_enabled`, a per-subnet field set from the Subnet
  Management form, default `False`) is `coordinator.scannable_subnets()`'s
  job, not this module's — enabling active scanning in the options flow only
  turns the coordinator on; scanning still touches nothing until individual
  subnets are opted in too. Responding hosts are then correlated to a MAC by
  reading the system ARP/neighbor table (`ip neigh show` → `arp -a`
  fallback, plus a separate Windows `arp -a` parser). Shells out to the
  system `ping` binary via subprocess rather than raw ICMP sockets — HA
  OS/Supervised containers generally don't grant custom integrations
  `CAP_NET_RAW`. `ActiveScanner.__init__` accepts `ping_fn`/`arp_table_fn`
  overrides specifically so tests can inject fakes instead of touching the
  network.
- **`passive_scanner.py`** (`PassiveScanner`, opt-in) — listens for mDNS
  announcements via **Home Assistant's own shared zeroconf instance**
  (`homeassistant.components.zeroconf.async_get_async_instance`), not a
  second mDNS engine. Uses `zeroconf.asyncio.AsyncServiceBrowser` directly
  (not the shared instance's `async_add_service_listener` convenience
  wrapper — that keys its internal browser-tracking dict by listener object,
  so reusing one listener across our multiple curated service types would
  silently drop all but the last browser reference on cleanup).
  `AsyncServiceBrowser`'s callbacks run on the HA event loop (verified
  against the installed `zeroconf` library's source), so `_on_service_state_change`
  can call `hass.async_create_task(...)` directly without
  `call_soon_threadsafe`.
- **`coordinator.py`** (`ActiveScanCoordinator`) — a
  `DataUpdateCoordinator` wrapping `ActiveScanner`; `update_interval` comes
  from the options-flow `active_scan_interval_hours` field (default 24h).
  Also owns `scannable_subnets()`, the module-level pure function that
  filters the store down to subnets with `active_scan_enabled` set before
  handing them to `ActiveScanner.async_scan` — kept as a standalone function
  (rather than inline in `_async_update_data`) specifically so it's testable
  without constructing a full coordinator (which needs a real-ish `hass`).
  The coordinator class itself still has no dedicated test beyond that, same
  thin-wiring policy as `__init__.py`.
- **`websocket_api.py`** — the frontend panel talks to the backend
  exclusively over HA's websocket API, not REST. **Gotcha:** every websocket
  message already carries a reserved, auto-assigned numeric `id` field for
  request/response correlation (added client-side by
  `connection.sendMessagePromise`). Never name a domain field `id` in a
  command schema — it gets silently clobbered by the envelope's id. This
  codebase uses `subnet_id` on the wire and translates it to `id` internally
  in `ws_save_subnet`/`ws_delete_subnet`. This already caused one real bug
  (see git history) — preserve the naming convention in any new command.
  `ws_list_devices` is also where active/passive scan results get folded in:
  it builds `device_ips` from `async_get_device_ips()` first, then
  `dict.setdefault(...)`s in `resolve_scan_result(...)` output from the
  coordinator's `.data` and the passive scanner's `.snapshot()` — `setdefault`
  is *the* mechanism that guarantees scan results only fill gaps and never
  override a device_tracker/config_entry match. Both `entry_data.get(...)`
  calls default to `None`/absent-key-safe, since both scanners are optional
  and may not exist in `hass.data[DOMAIN][entry_id]` at all.
- **`__init__.py`** — wires storage/matcher (and, if enabled via options,
  the active-scan coordinator and passive scanner) into `hass.data[DOMAIN]`,
  registers websocket commands, and registers the sidebar panel via
  `homeassistant.components.panel_custom.async_register_panel`. The static
  JS is served with `cache_headers=True` (aggressive browser caching), so
  `module_url` includes a `?v={PANEL_JS_VERSION}` query string
  (`const.py`) — **bump `PANEL_JS_VERSION` whenever
  `www/ip-management-panel.js` changes**, or updates won't reach users
  without a manual browser cache clear. Registers `entry.add_update_listener`
  → reload-the-whole-entry on options change (simplest way to pick up a new
  scan interval or a toggle flip; no live coordinator-mutation logic).
- **`config_flow.py`** — single-instance, zero-field *setup* flow (all real
  subnet configuration happens in the panel, not here) plus
  `IPManagementOptionsFlow`, which is the *only* place
  `enable_active_scan`/`active_scan_interval_hours`/`enable_passive_discovery`
  are configured — HA renders this natively (Settings → ... → Configure), no
  custom panel UI needed for it. **Gotcha:** don't set
  `self.config_entry = config_entry` in a custom `__init__` — recent HA
  versions make `config_entry` a property derived from `self.hass`/`self.handler`
  automatically, and the manual setter is deprecated (logged as an error for
  custom integrations). Just implement `async_step_init`; `async_get_options_flow`
  should return `IPManagementOptionsFlow()` with no arguments.

### Frontend (`custom_components/ip_management/www/ip-management-panel.js`)

Hand-written, dependency-free vanilla `HTMLElement`/Shadow DOM custom
element — deliberately not LitElement, to avoid needing a JS build step
(esbuild/npm) for what is two views and a handful of components. It ships
as-is; there is nothing to compile.

- The sidebar link opens this panel's **dashboard** view directly (the
  "Utilized IPs" screen — a tree of subnets with matched devices). This is
  the landing/default route, not a separate screen behind a menu.
- **Subnet Management** is a second internal view (`this._view = "subnets"`),
  reached only via the 3-dot menu on the dashboard — it is *not* a second
  sidebar entry. Both views live in the same custom element; navigation is
  handled internally, not through HA's router.
- The add/edit subnet form has no parent-subnet field by design — nesting
  is always inferred server-side from the CIDR (see `subnet_utils.py`
  above). Don't re-add one.
- Outgoing save/delete messages use `subnet_id`, matching the websocket API
  naming above — don't rename this back to `id`.
- Two badge helpers, easy to confuse: `sourceBadge(d.source)` (neutral,
  shows tracker/config/active scan/mDNS) and `unidentifiedDeviceBadge(d)`
  (warning-styled, only renders when `d.device_matched === false`). Both are
  rendered per device row in *both* places device rows appear (the per-subnet
  list and the "Unmatched devices" section) — don't add one without the
  other when touching that markup.

### Testing approach

No `hass` fixture / `pytest-homeassistant-custom-component` is used. That
package (and its transitive deps `pytest-aiohttp`/`pytest-socket`) was tried
and removed — on this Windows sandbox, `pytest-socket`'s socket blocking
broke asyncio's event-loop self-pipe creation, failing even fully
synchronous, HA-independent tests as a side effect of the plugin merely
being installed (auto-registered via a `pytest11` entry point, independent
of what's declared in `conftest.py`). Instead:

- `tests/conftest.py` just puts the repo root on `sys.path` so tests can
  `import custom_components.ip_management.<module>`.
- `subnet_utils` tests run directly against the real module (no HA
  dependency at all).
- `storage`/`device_matcher`/`websocket_api` tests use small hand-written
  fakes for the specific HA surface touched (`Store`, `device_registry`,
  `entity_registry`, `hass.states`, `hass.config_entries`) via
  `monkeypatch.setattr`, rather than a real `HomeAssistant` instance.
- `websocket_api.py` handlers are decorated with
  `@websocket_api.async_response`, which reschedules the coroutine onto
  `hass.async_create_background_task` — not directly awaitable. Tests reach
  the real handler via `handler.__wrapped__` (left in place by the
  decorator's internal `functools.wraps`) to bypass that scheduling and test
  the actual logic synchronously.
- `active_scanner.py` tests inject fake `ping_fn`/`arp_table_fn` callables
  into `ActiveScanner(...)` rather than touching the network, and test the
  `parse_*_output`/`hosts_to_scan` pure functions directly with sample
  command output strings.
- `passive_scanner.py` tests monkeypatch
  `passive_scanner_module.ha_zeroconf.async_get_async_instance` and (for the
  lifecycle tests) `passive_scanner_module.AsyncServiceBrowser` itself with
  fakes — there's no way to exercise real mDNS multicast in this sandbox.
  `FakeHass.async_create_task` schedules onto the real running loop
  (`asyncio.get_event_loop().create_task`) so `await asyncio.sleep(0)` lets
  the scheduled coroutine actually run before assertions.
- `test_config_flow.py` constructs `IPManagementOptionsFlow()` directly and
  sets `flow._config_entry = SimpleNamespace(options=...)` — the private
  compatibility attribute the `config_entry` property checks first — rather
  than going through the deprecated public setter (see the config_flow
  gotcha above) or standing up a real flow manager.

If you add a new websocket command or storage/matcher/scanner behavior,
follow the same fake-based pattern rather than reintroducing
`pytest-homeassistant-custom-component`.
