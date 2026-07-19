/**
 * IP Management sidebar panel.
 *
 * A dependency-free custom element (no build step) so the integration can
 * ship this file as-is. Home Assistant sets `.hass` and `.panel` on this
 * element automatically once it's mounted behind the sidebar link.
 *
 * Views:
 *  - "dashboard": the Utilized IPs screen — this is what the sidebar link
 *    opens directly.
 *  - "subnets": the Subnet Management screen, reached only via the 3-dot
 *    menu on the dashboard.
 */

const STYLE = `
<style>
  :host {
    display: block;
    height: 100%;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
    -webkit-font-smoothing: antialiased;
  }
  .toolbar {
    display: flex;
    align-items: center;
    height: 64px;
    padding: 0 16px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, #fff);
    box-sizing: border-box;
  }
  .toolbar .title {
    flex: 1;
    font-size: 20px;
    font-weight: 400;
  }
  .icon-button {
    background: none;
    border: none;
    color: inherit;
    font-size: 22px;
    line-height: 1;
    cursor: pointer;
    padding: 8px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .icon-button:hover {
    background: rgba(255, 255, 255, 0.15);
  }
  .menu-wrap {
    position: relative;
  }
  .menu {
    position: absolute;
    right: 0;
    top: 100%;
    margin-top: 4px;
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
    border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    min-width: 180px;
    z-index: 10;
    overflow: hidden;
  }
  .menu button {
    display: block;
    width: 100%;
    text-align: left;
    padding: 12px 16px;
    background: none;
    border: none;
    color: inherit;
    font-size: 14px;
    cursor: pointer;
  }
  .menu button:hover {
    background: var(--secondary-background-color, #eee);
  }
  .content {
    padding: 16px;
    max-width: 960px;
    margin: 0 auto;
    box-sizing: border-box;
  }
  .card {
    background: var(--card-background-color, #fff);
    border-radius: 8px;
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0, 0, 0, 0.2));
    margin-bottom: 16px;
    overflow: hidden;
  }
  .subnet-row {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    cursor: pointer;
  }
  .subnet-row:last-child {
    border-bottom: none;
  }
  .subnet-row:hover {
    background: var(--secondary-background-color, #fafafa);
  }
  .subnet-main {
    flex: 1;
    min-width: 0;
  }
  .subnet-label {
    font-weight: 500;
  }
  .subnet-meta {
    font-size: 13px;
    color: var(--secondary-text-color, #727272);
    margin-top: 2px;
  }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    background: var(--secondary-background-color, #eee);
    font-size: 12px;
    margin-left: 8px;
  }
  .device-count {
    font-size: 13px;
    color: var(--secondary-text-color, #727272);
    margin-right: 8px;
    white-space: nowrap;
  }
  .caret {
    display: inline-block;
    transition: transform 0.15s ease;
    margin-right: 4px;
  }
  .caret.open {
    transform: rotate(90deg);
  }
  .device-list {
    padding: 4px 16px 12px 16px;
    background: var(--secondary-background-color, #fafafa);
  }
  .device-item {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 14px;
    border-bottom: 1px dashed var(--divider-color, #e0e0e0);
  }
  .device-item:last-child {
    border-bottom: none;
  }
  .device-ip {
    color: var(--secondary-text-color, #727272);
    font-family: monospace;
  }
  .empty {
    padding: 24px 16px;
    color: var(--secondary-text-color, #727272);
    text-align: center;
  }
  .section-title {
    padding: 12px 16px;
    font-weight: 500;
    font-size: 15px;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
  }
  .error-banner {
    background: var(--error-color, #db4437);
    color: #fff;
    padding: 12px 16px;
    border-radius: 4px;
    margin-bottom: 16px;
  }
  .form-row {
    display: flex;
    flex-direction: column;
    padding: 8px 16px;
  }
  .form-row label {
    font-size: 13px;
    color: var(--secondary-text-color, #727272);
    margin-bottom: 4px;
  }
  .form-row input,
  .form-row select,
  .form-row textarea {
    font-size: 14px;
    padding: 8px;
    border: 1px solid var(--divider-color, #ccc);
    border-radius: 4px;
    background: var(--primary-background-color, #fff);
    color: var(--primary-text-color);
    font-family: inherit;
  }
  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 16px;
  }
  button.primary {
    background: var(--primary-color);
    color: var(--text-primary-color, #fff);
    border: none;
    border-radius: 4px;
    padding: 10px 18px;
    font-size: 14px;
    cursor: pointer;
  }
  button.secondary {
    background: none;
    color: var(--primary-color);
    border: 1px solid var(--divider-color, #ccc);
    border-radius: 4px;
    padding: 10px 18px;
    font-size: 14px;
    cursor: pointer;
  }
  button.text-danger {
    background: none;
    border: none;
    color: var(--error-color, #db4437);
    cursor: pointer;
    font-size: 13px;
  }
  .row-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .add-fab {
    margin: 16px;
  }
</style>
`;

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

const SOURCE_LABELS = {
  device_tracker: "tracker",
  config_entry: "config",
  active_scan: "active scan",
  passive_scan: "mDNS",
};

function sourceBadge(source) {
  const label = SOURCE_LABELS[source] || source;
  return `<span class="badge" title="How this device's IP was found">${escapeHtml(label)}</span>`;
}

class IPManagementPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._view = "dashboard";
    this._subnets = [];
    this._devices = [];
    this._loading = true;
    this._error = null;
    this._menuOpen = false;
    this._expanded = new Set();
    this._editingSubnet = null;
    this._formError = null;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._loadData();
    }
  }

  get hass() {
    return this._hass;
  }

  set panel(_panel) {
    // Unused: navigation is handled internally, not via HA's router.
  }

  connectedCallback() {
    this._render();
    this._boundCloseMenu = () => this._closeMenu();
    document.addEventListener("click", this._boundCloseMenu);
  }

  disconnectedCallback() {
    if (this._boundCloseMenu) {
      document.removeEventListener("click", this._boundCloseMenu);
    }
  }

  async _loadData() {
    this._loading = true;
    this._error = null;
    this._render();
    try {
      const [subnetsResp, devicesResp] = await Promise.all([
        this._hass.connection.sendMessagePromise({
          type: "ip_management/subnets/list",
        }),
        this._hass.connection.sendMessagePromise({
          type: "ip_management/devices/list",
        }),
      ]);
      this._subnets = subnetsResp.subnets;
      this._devices = devicesResp.devices;
    } catch (err) {
      this._error = (err && err.message) || String(err);
    }
    this._loading = false;
    this._render();
  }

  async _saveSubnet(payload) {
    this._formError = null;
    try {
      await this._hass.connection.sendMessagePromise({
        type: "ip_management/subnets/save",
        ...payload,
      });
    } catch (err) {
      this._formError = (err && err.message) || String(err);
      this._render();
      return false;
    }
    this._editingSubnet = null;
    await this._loadData();
    return true;
  }

  async _deleteSubnet(id) {
    await this._hass.connection.sendMessagePromise({
      type: "ip_management/subnets/delete",
      subnet_id: id,
    });
    await this._loadData();
  }

  _buildTree() {
    const byParent = new Map();
    for (const s of this._subnets) {
      const key = s.parent_id || "__root__";
      if (!byParent.has(key)) byParent.set(key, []);
      byParent.get(key).push(s);
    }
    for (const list of byParent.values()) {
      list.sort((a, b) => a.label.localeCompare(b.label) || a.cidr.localeCompare(b.cidr));
    }

    const devicesBySubnet = new Map();
    for (const d of this._devices) {
      const key = d.subnet_id || "__unmatched__";
      if (!devicesBySubnet.has(key)) devicesBySubnet.set(key, []);
      devicesBySubnet.get(key).push(d);
    }

    const rows = [];
    const walk = (parentKey, depth) => {
      const children = byParent.get(parentKey) || [];
      for (const subnet of children) {
        rows.push({
          subnet,
          depth,
          devices: devicesBySubnet.get(subnet.id) || [],
        });
        walk(subnet.id, depth + 1);
      }
    };
    walk("__root__", 0);

    return { rows, unmatched: devicesBySubnet.get("__unmatched__") || [] };
  }

  _toggleExpanded(id) {
    if (this._expanded.has(id)) {
      this._expanded.delete(id);
    } else {
      this._expanded.add(id);
    }
    this._render();
  }

  _toggleMenu(e) {
    e.stopPropagation();
    this._menuOpen = !this._menuOpen;
    this._render();
  }

  _closeMenu() {
    if (this._menuOpen) {
      this._menuOpen = false;
      this._render();
    }
  }

  _goToSubnetManagement() {
    this._menuOpen = false;
    this._view = "subnets";
    this._editingSubnet = null;
    this._render();
  }

  _goToDashboard() {
    this._view = "dashboard";
    this._editingSubnet = null;
    this._formError = null;
    this._render();
  }

  // ---------- Rendering ----------

  _render() {
    if (!this.shadowRoot) return;
    const body =
      this._view === "dashboard"
        ? this._renderDashboard()
        : this._renderSubnetManagement();
    this.shadowRoot.innerHTML = `${STYLE}${body}`;
    this._attachHandlers();
  }

  _renderToolbar(title, { showMenu, showBack }) {
    return `
      <div class="toolbar">
        ${showBack ? `<button class="icon-button" id="back-btn" title="Back">&#8592;</button>` : ""}
        <div class="title">${escapeHtml(title)}</div>
        ${
          showMenu
            ? `<div class="menu-wrap">
                <button class="icon-button" id="menu-btn" title="Menu">&#8942;</button>
                ${
                  this._menuOpen
                    ? `<div class="menu">
                        <button id="manage-subnets-btn">Manage subnets</button>
                       </div>`
                    : ""
                }
               </div>`
            : ""
        }
      </div>
    `;
  }

  _renderDashboard() {
    if (this._loading) {
      return `${this._renderToolbar("IP Management", { showMenu: true })}<div class="content"><div class="empty">Loading…</div></div>`;
    }

    const { rows, unmatched } = this._buildTree();

    const rowsHtml = rows
      .map(({ subnet, depth, devices }) => {
        const expanded = this._expanded.has(subnet.id);
        const indent = depth * 20;
        return `
          <div>
            <div class="subnet-row" data-subnet-id="${escapeHtml(subnet.id)}" style="padding-left: ${16 + indent}px">
              <span class="caret ${expanded ? "open" : ""}">&#9656;</span>
              <div class="subnet-main">
                <div class="subnet-label">
                  ${escapeHtml(subnet.label || subnet.cidr)}
                  ${subnet.item_type ? `<span class="badge">${escapeHtml(subnet.item_type)}</span>` : ""}
                </div>
                <div class="subnet-meta">${escapeHtml(subnet.cidr)} &nbsp;•&nbsp; ${escapeHtml(subnet.display_range)}</div>
              </div>
              <div class="device-count">${devices.length} device${devices.length === 1 ? "" : "s"}</div>
            </div>
            ${
              expanded
                ? `<div class="device-list">
                    ${
                      devices.length
                        ? devices
                            .map(
                              (d) => `
                              <div class="device-item">
                                <span>${escapeHtml(d.name)} ${sourceBadge(d.source)}</span>
                                <span class="device-ip">${escapeHtml(d.ip_address)}</span>
                              </div>`
                            )
                            .join("")
                        : `<div class="device-item"><span>No devices matched to this subnet</span></div>`
                    }
                   </div>`
                : ""
            }
          </div>
        `;
      })
      .join("");

    const unmatchedHtml = unmatched.length
      ? `
        <div class="card">
          <div class="section-title">Unmatched devices</div>
          <div class="device-list">
            ${unmatched
              .map(
                (d) => `
                <div class="device-item">
                  <span>${escapeHtml(d.name)} ${sourceBadge(d.source)}</span>
                  <span class="device-ip">${escapeHtml(d.ip_address)}</span>
                </div>`
              )
              .join("")}
          </div>
        </div>
      `
      : "";

    return `
      ${this._renderToolbar("IP Management", { showMenu: true })}
      <div class="content">
        ${this._error ? `<div class="error-banner">${escapeHtml(this._error)}</div>` : ""}
        <div class="card">
          ${rows.length ? rowsHtml : `<div class="empty">No subnets defined yet. Open the menu to add one.</div>`}
        </div>
        ${unmatchedHtml}
      </div>
    `;
  }

  _renderSubnetManagement() {
    const { rows } = this._buildTree();

    const editing = this._editingSubnet;
    const formHtml = editing
      ? `
        <div class="card">
          <div class="section-title">${editing.id ? "Edit subnet" : "Add subnet"}</div>
          ${this._formError ? `<div class="error-banner" style="margin: 8px 16px;">${escapeHtml(this._formError)}</div>` : ""}
          <form id="subnet-form">
            <div class="form-row">
              <label>CIDR block (e.g. 192.168.10.0/24)</label>
              <input name="cidr" required value="${escapeHtml(editing.cidr || "")}" placeholder="192.168.10.0/24" />
              <p style="font-size: 12px; color: var(--secondary-text-color, #727272); margin: 4px 0 0;">
                Nesting is automatic — if this CIDR falls inside (or contains)
                an existing subnet, the hierarchy is inferred for you.
              </p>
            </div>
            <div class="form-row">
              <label>Label</label>
              <input name="label" value="${escapeHtml(editing.label || "")}" placeholder="Cameras" />
            </div>
            <div class="form-row">
              <label>Item type</label>
              <input name="item_type" value="${escapeHtml(editing.item_type || "")}" placeholder="IoT" />
            </div>
            <div class="form-row">
              <label>Notes</label>
              <textarea name="notes" rows="2">${escapeHtml(editing.notes || "")}</textarea>
            </div>
            <div class="form-actions">
              <button type="button" class="secondary" id="cancel-form-btn">Cancel</button>
              <button type="submit" class="primary">Save</button>
            </div>
          </form>
        </div>
      `
      : "";

    const listHtml = rows
      .map(({ subnet, depth }) => {
        const indent = depth * 20;
        return `
          <div class="subnet-row" style="padding-left: ${16 + indent}px; cursor: default;">
            <div class="subnet-main">
              <div class="subnet-label">
                ${escapeHtml(subnet.label || subnet.cidr)}
                ${subnet.item_type ? `<span class="badge">${escapeHtml(subnet.item_type)}</span>` : ""}
              </div>
              <div class="subnet-meta">${escapeHtml(subnet.cidr)} &nbsp;•&nbsp; ${escapeHtml(subnet.display_range)}</div>
            </div>
            <div class="row-actions">
              <button class="text-danger" data-edit-id="${escapeHtml(subnet.id)}">Edit</button>
              <button class="text-danger" data-delete-id="${escapeHtml(subnet.id)}">Delete</button>
            </div>
          </div>
        `;
      })
      .join("");

    const html = `
      ${this._renderToolbar("Manage subnets", { showMenu: false, showBack: true })}
      <div class="content">
        ${this._error ? `<div class="error-banner">${escapeHtml(this._error)}</div>` : ""}
        ${formHtml}
        <div class="card">
          ${rows.length ? listHtml : `<div class="empty">No subnets defined yet.</div>`}
        </div>
        ${!editing ? `<button class="primary add-fab" id="add-subnet-btn">+ Add subnet</button>` : ""}
      </div>
    `;

    return html;
  }

  // ---------- Event wiring ----------

  _attachHandlers() {
    const root = this.shadowRoot;

    const backBtn = root.getElementById("back-btn");
    if (backBtn) backBtn.addEventListener("click", () => this._goToDashboard());

    const menuBtn = root.getElementById("menu-btn");
    if (menuBtn) menuBtn.addEventListener("click", (e) => this._toggleMenu(e));

    const manageBtn = root.getElementById("manage-subnets-btn");
    if (manageBtn)
      manageBtn.addEventListener("click", () => this._goToSubnetManagement());

    root.querySelectorAll(".subnet-row[data-subnet-id]").forEach((el) => {
      el.addEventListener("click", () =>
        this._toggleExpanded(el.getAttribute("data-subnet-id"))
      );
    });

    const addBtn = root.getElementById("add-subnet-btn");
    if (addBtn)
      addBtn.addEventListener("click", () => {
        this._editingSubnet = { id: null, cidr: "", label: "", item_type: "", notes: "" };
        this._formError = null;
        this._render();
      });

    const cancelBtn = root.getElementById("cancel-form-btn");
    if (cancelBtn)
      cancelBtn.addEventListener("click", () => {
        this._editingSubnet = null;
        this._formError = null;
        this._render();
      });

    root.querySelectorAll("[data-edit-id]").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.getAttribute("data-edit-id");
        const subnet = this._subnets.find((s) => s.id === id);
        if (subnet) {
          this._editingSubnet = { ...subnet };
          this._formError = null;
          this._render();
        }
      });
    });

    root.querySelectorAll("[data-delete-id]").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.getAttribute("data-delete-id");
        this._deleteSubnet(id);
      });
    });

    const form = root.getElementById("subnet-form");
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const data = new FormData(form);
        const payload = {
          subnet_id: this._editingSubnet.id || undefined,
          cidr: data.get("cidr").trim(),
          label: data.get("label").trim(),
          item_type: data.get("item_type").trim(),
          notes: data.get("notes").trim() || null,
        };
        this._saveSubnet(payload);
      });
    }
  }
}

customElements.define("ip-management-panel", IPManagementPanel);
