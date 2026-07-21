# Sequence Diagrams

## 1. Integration setup (`async_setup_entry`)

Runs once when HA loads the config entry (on HA startup, or right after the
user adds/reloads the integration).

```mermaid
sequenceDiagram
    participant HA as HA Core
    participant Init as __init__.async_setup_entry
    participant Store as SubnetStore
    participant Matcher as DeviceMatcher
    participant Coord as ActiveScanCoordinator
    participant AScan as ActiveScanner
    participant Passive as PassiveScanner
    participant WS as websocket_api
    participant Panel as panel_custom

    HA->>Init: async_setup_entry(hass, entry)
    Init->>Store: SubnetStore(hass)
    Init->>Store: await async_load()
    Store->>Store: _recompute_hierarchy()
    Init->>Matcher: DeviceMatcher(hass)
    Init->>Init: hass.data[DOMAIN][entry_id] = {store, matcher, ...}

    alt options.enable_active_scan == True
        Init->>Coord: ActiveScanCoordinator(hass, entry, store, ActiveScanner(hass), interval_hours)
        Init->>Coord: await async_config_entry_first_refresh()
        Coord->>AScan: await async_scan(scannable_subnets(store.subnets))
        Coord-->>Init: coordinator.data populated
    end

    alt options.enable_passive_discovery == True
        Init->>Passive: PassiveScanner(hass)
        Init->>Passive: await async_start()
        Passive->>Passive: bind AsyncServiceBrowser to HA's shared zeroconf
    end

    Init->>WS: async_register_websocket_commands(hass)
    Init->>Init: _async_register_static_path(hass)  # serves www/ under /ip_management_static
    Init->>Panel: async_register_panel(frontend_url_path="ip-management", ...)
    Init->>Init: entry.add_update_listener(_async_reload_entry)
```

Teardown (`async_unload_entry`) is the mirror image: pop `hass.data[DOMAIN][entry_id]`,
`await coordinator.async_shutdown()` if present, `await passive_scanner.async_stop()`
if present. Changing options (Configure dialog) always triggers a full
`hass.config_entries.async_reload` rather than live-mutating a running
coordinator/scanner.

## 2. Dashboard load (subnets + devices)

What happens when the panel's dashboard view opens or refreshes.

```mermaid
sequenceDiagram
    participant Panel as ip-management-panel.js
    participant WS as HA Websocket connection
    participant SubCmd as ws_list_subnets
    participant DevCmd as ws_list_devices
    participant Store as SubnetStore
    participant Matcher as DeviceMatcher

    Panel->>WS: sendMessagePromise({type: "ip_management/subnets/list"})
    WS->>SubCmd: dispatch
    SubCmd->>Store: store.subnets
    SubCmd->>SubCmd: display_range(cidr) per record
    SubCmd-->>Panel: {subnets: [...]}

    Panel->>WS: sendMessagePromise({type: "ip_management/devices/list"})
    WS->>DevCmd: dispatch
    Note over DevCmd,Matcher: see diagram 4 below for the full merge pipeline
    DevCmd->>Matcher: async_get_device_ips() / resolve_scan_result / apply_manual_ip_links / async_match_devices_to_subnets
    DevCmd-->>Panel: {devices: [{device_id, name, ip_address, subnet_id, source, device_matched, manually_assigned}]}

    Panel->>WS: sendMessagePromise({type: "config/device_registry/list"})
    Note over Panel,WS: HA's own core command — used only to populate<br/>the assign-device dialog's dropdown
    WS-->>Panel: {devices: [...]}  # every registered HA device

    Panel->>Panel: render subnet tree + device rows + badges
```

## 3. Save a subnet (create/edit) — hierarchy recompute

```mermaid
sequenceDiagram
    participant Panel as ip-management-panel.js
    participant WS as HA Websocket connection
    participant Cmd as ws_save_subnet
    participant Store as SubnetStore
    participant Utils as subnet_utils

    Panel->>WS: sendMessagePromise({type: "ip_management/subnets/save", subnet_id?, cidr, label, item_type, notes, active_scan_enabled})
    WS->>Cmd: dispatch (msg["id"] is the websocket envelope id — NOT subnet_id)
    Cmd->>Cmd: payload = msg minus "type"/"id"; rename subnet_id -> id
    Cmd->>Store: await async_save_subnet(payload)
    Store->>Utils: parse_network(cidr)
    alt invalid CIDR
        Utils-->>Store: raise InvalidCidrError
        Store-->>Cmd: propagate
        Cmd-->>Panel: send_error(msg["id"], "invalid_subnet", ...)
    else valid CIDR
        Store->>Store: merge into _subnets[id] (preserve created_at)
        Store->>Store: _recompute_hierarchy()
        Store->>Utils: infer_parent_ids(all cidrs)
        Utils-->>Store: {subnet_id: parent_id, ...} for every subnet
        Store->>Store: await _async_persist()  # whole file rewritten
        Store-->>Cmd: saved record
        Cmd->>Utils: display_range(record["cidr"])
        Cmd-->>Panel: send_result(msg["id"], {subnet: record})
    end
    Panel->>Panel: reload subnet list, re-render tree
```

## 4. List devices — the source-merge pipeline (`ws_list_devices`)

This is the most order-sensitive flow in the codebase: each source can only
*fill gaps*, except the manual IP link step, which runs last and can
override anything.

```mermaid
sequenceDiagram
    participant Cmd as ws_list_devices
    participant Matcher as DeviceMatcher
    participant Coord as ActiveScanCoordinator (optional)
    participant Passive as PassiveScanner (optional)
    participant Store as SubnetStore

    Cmd->>Matcher: async_get_device_ips()
    Matcher->>Matcher: _from_config_entries()  # entry.data host/ip/ip_address
    Matcher->>Matcher: _from_device_tracker()  # overwrites on device_id collision
    Matcher-->>Cmd: device_ips: {device_id: DeviceIpInfo(source="config_entry"|"device_tracker")}

    opt coordinator present and has data
        Cmd->>Coord: coordinator.data  (cached, not a live scan)
        loop each DiscoveredHost
            Cmd->>Matcher: resolve_scan_result(host, source="active_scan")
            Matcher-->>Cmd: DeviceIpInfo (real device_id via MAC match, or synthetic "scan:<ip>")
            Cmd->>Cmd: device_ips.setdefault(info.device_id, info)
            Note right of Cmd: setdefault = never overwrites an<br/>existing device_tracker/config_entry entry
        end
    end

    opt passive_scanner present
        Cmd->>Passive: passive_scanner.snapshot()
        loop each DiscoveredHost
            Cmd->>Matcher: resolve_scan_result(host, source="passive_scan")
            Matcher-->>Cmd: DeviceIpInfo
            Cmd->>Cmd: device_ips.setdefault(info.device_id, info)
        end
    end

    Cmd->>Store: store.ip_device_links
    Cmd->>Matcher: apply_manual_ip_links(device_ips, ip_device_links)
    Note right of Matcher: Runs LAST — can override ANY source,<br/>not just unidentified scan results.<br/>Stale device_id (deleted from registry) is ignored.
    Matcher-->>Cmd: device_ips (manually-linked entries have manually_assigned=True)

    Cmd->>Store: store.device_overrides
    Cmd->>Matcher: async_match_devices_to_subnets(store.subnets, device_overrides, device_ips)
    loop each device
        alt device_id in device_overrides
            Matcher->>Matcher: subnet_id = device_overrides[device_id]  # forced, skips IP matching
        else
            Matcher->>Matcher: most_specific_match(info.ip_address, all subnet CIDRs)
        end
    end
    Matcher-->>Cmd: list of {device_id, name, ip_address, subnet_id, source, device_matched, manually_assigned}
```

## 5. Manually assigning a device to an IP (assign-device dialog)

```mermaid
sequenceDiagram
    actor User
    participant Panel as ip-management-panel.js
    participant WS as HA Websocket connection
    participant Cmd as ws_assign_ip_device
    participant Store as SubnetStore

    User->>Panel: click a device row's IP address (.device-ip[data-open-assign])
    Panel->>Panel: lookup device by IP in this._devices
    Panel->>Panel: _openAssignDialog(device) -> this._assigningDevice = device; re-render
    Panel->>Panel: render <select> pre-selected to device.device_id if manually_assigned else "" (Automatic)
    Note over Panel: options come from this._haDevices,<br/>fetched once via core config/device_registry/list

    User->>Panel: pick a device (or "Automatic") and Save
    Panel->>Panel: deviceId = select.value || null
    Panel->>WS: sendMessagePromise({type: "ip_management/devices/assign_ip", ip_address, device_id: deviceId})
    WS->>Cmd: dispatch
    Cmd->>Store: await async_set_ip_device_link(ip_address, device_id)
    alt device_id is None
        Store->>Store: _ip_device_links.pop(ip_address, None)
    else
        Store->>Store: _ip_device_links[ip_address] = device_id
    end
    Store->>Store: await _async_persist()
    Cmd-->>Panel: send_result(msg["id"], {})
    Panel->>Panel: close dialog, reload devices list (diagram 4 re-runs, now with the new link)
```

Clicking the dialog's Cancel button, or the `.dialog-overlay` background
(but not the `.dialog-box` itself), closes the dialog without calling
`assign_ip` at all.

## 6. Active scan cycle (coordinator-driven)

```mermaid
sequenceDiagram
    participant Timer as HA event loop timer
    participant Coord as ActiveScanCoordinator
    participant Store as SubnetStore
    participant Scanner as ActiveScanner
    participant OS as OS ping/arp subprocess

    Timer->>Coord: update_interval elapsed (default 24h)
    Coord->>Coord: _async_update_data()
    Coord->>Store: store.subnets
    Coord->>Coord: scannable_subnets(subnets)  # filter to active_scan_enabled == True
    Coord->>Scanner: await async_scan(scannable_subnets)

    loop each scannable subnet
        Scanner->>Scanner: hosts_to_scan(cidr, MAX_ACTIVE_SCAN_HOSTS_PER_SUBNET)
        alt subnet larger than 512 addresses
            Scanner->>Scanner: log warning, skip (returns None, not partial scan)
        else
            Scanner->>Scanner: add every address (incl. network/broadcast) to all_ips
        end
    end

    par bounded by PING_CONCURRENCY=32 semaphore
        Scanner->>OS: asyncio.create_subprocess_exec(ping ...) per IP
        OS-->>Scanner: return code (alive/not)
    end

    Scanner->>OS: ip neigh show  (POSIX)  /  arp -a  (Windows)
    OS-->>Scanner: raw ARP/neighbor table text
    Scanner->>Scanner: parse_ip_neigh_output / parse_arp_a_output / parse_windows_arp_a_output
    Scanner-->>Coord: list[DiscoveredHost(ip, mac)] for every IP that responded
    Coord->>Coord: self.data = result  (cached for ws_list_devices, see diagram 4)
```

## 7. Passive discovery (mDNS) lifecycle

```mermaid
sequenceDiagram
    participant Init as __init__.async_setup_entry
    participant Passive as PassiveScanner
    participant HAZ as HA shared Zeroconf instance
    participant Browser as AsyncServiceBrowser
    participant Net as LAN (mDNS multicast)

    Init->>Passive: await async_start()
    Passive->>HAZ: await async_get_async_instance(hass)
    Passive->>Browser: AsyncServiceBrowser(haz.zeroconf, ZEROCONF_SERVICE_TYPES, handlers=[_on_service_state_change])
    Browser->>Net: subscribe to curated service types (HomeKit, Chromecast, AirPlay, printers, ...)

    loop whenever a device announces/updates
        Net-->>Browser: service state change
        Browser->>Passive: _on_service_state_change(..., state_change)  [runs on HA event loop]
        alt state_change == Removed
            Passive->>Passive: ignore
        else
            Passive->>Passive: hass.async_create_task(_async_resolve(service_type, name))
            Passive->>HAZ: await async_get_service_info(service_type, name, timeout=3000ms)
            HAZ-->>Passive: AsyncServiceInfo (addresses, server name)
            Passive->>Passive: friendly_name_from_service_info(...)
            Passive->>Passive: self._hosts[ip] = DiscoveredHost(ip, mac=None, name)
        end
    end

    Note over Passive: snapshot() returns list(self._hosts.values())<br/>on demand — pulled by ws_list_devices (diagram 4)

    Init->>Passive: await async_stop()  (on entry unload)
    Passive->>Browser: await async_cancel()
```
