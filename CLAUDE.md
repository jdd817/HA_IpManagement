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
  not a coroutine marker) — don't `await` them.
- **`websocket_api.py`** — the frontend panel talks to the backend
  exclusively over HA's websocket API, not REST. **Gotcha:** every websocket
  message already carries a reserved, auto-assigned numeric `id` field for
  request/response correlation (added client-side by
  `connection.sendMessagePromise`). Never name a domain field `id` in a
  command schema — it gets silently clobbered by the envelope's id. This
  codebase uses `subnet_id` on the wire and translates it to `id` internally
  in `ws_save_subnet`/`ws_delete_subnet`. This already caused one real bug
  (see git history) — preserve the naming convention in any new command.
- **`__init__.py`** — wires storage/matcher into `hass.data[DOMAIN]`,
  registers websocket commands, and registers the sidebar panel via
  `homeassistant.components.panel_custom.async_register_panel`. The static
  JS is served with `cache_headers=True` (aggressive browser caching), so
  `module_url` includes a `?v={PANEL_JS_VERSION}` query string
  (`const.py`) — **bump `PANEL_JS_VERSION` whenever
  `www/ip-management-panel.js` changes**, or updates won't reach users
  without a manual browser cache clear.
- **`config_flow.py`** — single-instance, zero-field flow; it only exists so
  the integration can be added once from Settings → Devices & Services. All
  real configuration happens in the panel itself, not here.

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

If you add a new websocket command or storage/matcher behavior, follow the
same fake-based pattern rather than reintroducing
`pytest-homeassistant-custom-component`.
