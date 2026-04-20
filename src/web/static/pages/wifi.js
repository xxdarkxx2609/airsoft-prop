/* WiFi page */

// ----------------------------------------------------------------
// Current connection status
// ----------------------------------------------------------------

async function fetchWifiStatus() {
    try {
        const status = await apiGet("/api/wifi/status");

        const ssidEl = document.getElementById("wifi-ssid");
        const ipEl = document.getElementById("wifi-ip");
        const signalEl = document.getElementById("wifi-signal");
        const modeEl = document.getElementById("wifi-mode");
        const disconnectBtn = document.getElementById("disconnect-btn");

        if (status.connected) {
            if (ssidEl) ssidEl.textContent = status.ssid || "—";
            if (ipEl) ipEl.textContent = status.ip_address || "—";
            if (signalEl) signalEl.innerHTML = signalBars(status.signal || 0) + ` ${status.signal || 0}%`;
            if (modeEl) modeEl.textContent = status.mode || "Station";
            if (disconnectBtn) disconnectBtn.style.display = "";
        } else {
            if (ssidEl) ssidEl.textContent = "Not connected";
            if (ipEl) ipEl.textContent = "—";
            if (signalEl) signalEl.innerHTML = "—";
            if (modeEl) modeEl.textContent = "—";
            if (disconnectBtn) disconnectBtn.style.display = "none";
        }

        // Also update shared header chip
        const dot = document.getElementById("connection-status");
        const text = document.getElementById("connection-text");
        if (dot) dot.className = status.connected ? "status-dot connected" : "status-dot disconnected";
        if (text) text.textContent = status.connected ? `${status.ssid} — ${status.ip_address}` : "Not connected";
    } catch (_) {}
}

// ----------------------------------------------------------------
// Network scan
// ----------------------------------------------------------------

async function scanNetworks() {
    const btn = document.getElementById("scan-btn");
    const list = document.getElementById("network-list");
    if (btn) { btn.disabled = true; btn.textContent = "Scanning…"; }
    if (list) list.innerHTML = "<p class=\"loading\">Scanning for networks…</p>";

    try {
        const result = await apiGet("/api/wifi/scan");

        if (result.error === "ap_active") {
            if (list) list.innerHTML = "<p class=\"message warning\">Cannot scan while Access Point mode is active. Disable Force AP first.</p>";
            return;
        }

        const networks = result.networks ?? result;

        if (!Array.isArray(networks) || networks.length === 0) {
            if (list) list.innerHTML = "<p>No networks found.</p>";
            return;
        }

        if (list) {
            list.innerHTML = networks.map(n => {
                const ssid = String(n.ssid || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
                const security = String(n.security || "Open");
                const secBadge = security !== "Open"
                    ? `<span class="chip chip-orange">${security.replace(/&/g, "&amp;")}</span>`
                    : `<span class="chip chip-gray">Open</span>`;
                const connectedBadge = n.connected
                    ? `<span class="chip chip-green">Connected</span>`
                    : "";
                return `<div class="network-item" data-ssid="${ssid}" data-security="${security}">
                    <div class="network-info">
                        <div class="network-ssid">${ssid} ${connectedBadge}</div>
                        <div class="network-meta">${secBadge}</div>
                    </div>
                    <div class="network-signal">${signalBars(n.signal || 0)}</div>
                    <button class="btn btn-primary btn-small" onclick="showConnectModal('${ssid}', '${security}')">Connect</button>
                </div>`;
            }).join("");
        }
    } catch (_) {
        if (list) list.innerHTML = "<p class=\"message error\">Scan failed.</p>";
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Scan"; }
    }
}

// ----------------------------------------------------------------
// Connect modal
// ----------------------------------------------------------------

function showConnectModal(ssid, security) {
    const modal = document.getElementById("connect-modal");
    if (!modal) return;
    const ssidField = document.getElementById("connect-ssid");
    const pwField = document.getElementById("connect-password");

    if (ssidField) ssidField.value = ssid;
    modal.dataset.ssid = ssid;
    modal.dataset.security = security;

    if (pwField) {
        pwField.value = "";
        pwField.disabled = (security === "Open");
    }

    modal.style.display = "";
    modal.setAttribute("aria-hidden", "false");
    if (pwField && security !== "Open") pwField.focus();
}

function closeConnectModal() {
    const modal = document.getElementById("connect-modal");
    if (modal) { modal.style.display = "none"; modal.setAttribute("aria-hidden", "true"); }
}

async function connectToNetwork(event) {
    if (event && event.preventDefault) event.preventDefault();
    const modal = document.getElementById("connect-modal");
    if (!modal) return;

    const ssid = modal.dataset.ssid;
    const password = document.getElementById("connect-password")?.value || "";

    closeConnectModal();

    const list = document.getElementById("network-list");
    if (list) list.innerHTML = `<p class="loading">Connecting to ${ssid}…</p>`;

    try {
        const result = await apiPost("/api/wifi/connect", { ssid, password });
        if (result.success) {
            await fetchWifiStatus();
            await scanNetworks();
            await fetchSavedNetworks();
        } else {
            if (list) list.innerHTML = `<p class="message error">${result.message || "Connection failed."}</p>`;
        }
    } catch (_) {
        if (list) list.innerHTML = "<p class=\"message error\">Connection failed.</p>";
    }
}

// ----------------------------------------------------------------
// Disconnect
// ----------------------------------------------------------------

async function disconnectWifi() {
    try {
        await apiPost("/api/wifi/disconnect", {});
        await fetchWifiStatus();
    } catch (_) {}
}

// ----------------------------------------------------------------
// Saved networks
// ----------------------------------------------------------------

async function fetchSavedNetworks() {
    const el = document.getElementById("saved-list");
    if (!el) return;
    try {
        const saved = await apiGet("/api/wifi/saved");
        if (!Array.isArray(saved) || saved.length === 0) {
            el.innerHTML = "<p>No saved networks.</p>";
            return;
        }
        el.innerHTML = saved.map(ssid => {
            const safe = String(ssid).replace(/&/g, "&amp;").replace(/</g, "&lt;");
            return `<div class="saved-item">
                <span>${safe}</span>
                <button class="btn btn-secondary btn-small" onclick="forgetNetwork('${safe}')">Forget</button>
            </div>`;
        }).join("");
    } catch (_) {
        el.innerHTML = "<p class=\"message error\">Failed to load saved networks.</p>";
    }
}

async function forgetNetwork(ssid) {
    try {
        await apiPost("/api/wifi/forget", { ssid });
        await fetchSavedNetworks();
    } catch (_) {}
}

// ----------------------------------------------------------------
// AP status
// ----------------------------------------------------------------

async function fetchApStatus() {
    try {
        const data = await apiGet("/api/wifi/ap-status");
        const active = !!data.active;

        const ssidRow = document.getElementById("ap-ssid-row");
        const pwRow = document.getElementById("ap-password-row");
        const ipRow = document.getElementById("ap-ip-row");
        const ssidEl = document.getElementById("ap-ssid");
        const pwEl = document.getElementById("ap-password");
        const ipEl = document.getElementById("ap-ip");

        if (ssidRow) ssidRow.style.display = active ? "" : "none";
        if (pwRow) pwRow.style.display = active && data.password ? "" : "none";
        if (ipRow) ipRow.style.display = active ? "" : "none";

        if (ssidEl) ssidEl.textContent = data.ssid || "—";
        if (pwEl) pwEl.textContent = data.password || "—";
        if (ipEl) ipEl.textContent = data.ip || "—";
    } catch (_) {}
}

// ----------------------------------------------------------------
// Force AP toggle
// ----------------------------------------------------------------

async function fetchForceAp() {
    try {
        const data = await apiGet("/api/wifi/force-ap");
        const toggle = document.getElementById("force-ap-toggle");
        if (toggle) toggle.checked = !!data.force_ap;
    } catch (_) {}
}

async function setForceAp(value) {
    try {
        await apiPost("/api/wifi/force-ap", { force_ap: value });
        await fetchApStatus();
    } catch (_) {}
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    fetchWifiStatus();
    fetchSavedNetworks();
    fetchApStatus();
    fetchForceAp();

    const forceToggle = document.getElementById("force-ap-toggle");
    if (forceToggle) forceToggle.addEventListener("change", e => setForceAp(e.target.checked));

    const connectSubmit = document.getElementById("connect-submit-btn");
    if (connectSubmit) connectSubmit.addEventListener("click", connectToNetwork);

    const connectCancel = document.getElementById("connect-cancel-btn");
    if (connectCancel) connectCancel.addEventListener("click", closeConnectModal);

    const scanBtn = document.getElementById("scan-btn");
    if (scanBtn) scanBtn.addEventListener("click", scanNetworks);

    const disconnectBtn = document.getElementById("disconnect-btn");
    if (disconnectBtn) disconnectBtn.addEventListener("click", disconnectWifi);
});
