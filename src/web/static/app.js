/* Airsoft Prop — Web Interface JavaScript */

// ----------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------

async function apiGet(url) {
    const resp = await fetch(url);
    if (resp.status === 401) {
        window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
        return {};
    }
    return resp.json();
}

async function apiPost(url, data) {
    const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
    });
    if (resp.status === 401) {
        window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
        return {};
    }
    return resp.json();
}

function signalBars(signal) {
    const bars = [signal >= 20, signal >= 40, signal >= 60, signal >= 80];
    return `<span class="signal-bars">${bars.map(
        (active) => `<span class="signal-bar${active ? " active" : ""}"></span>`
    ).join("")}</span> ${signal}%`;
}

function showMessage(elementId, text, type) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = text;
    el.className = `message ${type}`;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 5000);
}

// ----------------------------------------------------------------
// WiFi Status (footer + wifi page)
// ----------------------------------------------------------------

async function fetchWifiStatus() {
    try {
        const status = await apiGet("/api/wifi/status");
        const dot = document.getElementById("connection-status");
        const text = document.getElementById("connection-text");

        if (status.connected) {
            dot.className = "status-dot connected";
            text.textContent = `${status.ssid} — ${status.ip_address}`;
        } else {
            dot.className = "status-dot disconnected";
            text.textContent = "Not connected";
        }

        // WiFi status card
        const el = document.getElementById("wifi-status");
        if (el) {
            if (status.connected) {
                el.innerHTML = `
                    <div class="info-table">
                        <div class="info-row">
                            <span class="info-label">Status</span>
                            <span class="info-value network-connected">Connected</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Network</span>
                            <span class="info-value">${status.ssid}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">IP Address</span>
                            <span class="info-value">${status.ip_address}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Signal</span>
                            <span class="info-value">${signalBars(status.signal)}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">MAC</span>
                            <span class="info-value">${status.mac_address || "N/A"}</span>
                        </div>
                    </div>
                    <div class="form-actions">
                        <button class="btn btn-secondary btn-small" onclick="disconnectWifi()">Disconnect</button>
                    </div>`;
            } else {
                el.innerHTML = `
                    <div class="info-table">
                        <div class="info-row">
                            <span class="info-label">Status</span>
                            <span class="info-value" style="color: var(--danger)">Disconnected</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">MAC</span>
                            <span class="info-value">${status.mac_address || "N/A"}</span>
                        </div>
                    </div>`;
            }
        }
    } catch (e) {
        console.error("Failed to fetch WiFi status:", e);
    }
}

// ----------------------------------------------------------------
// WiFi Scan
// ----------------------------------------------------------------

async function scanNetworks() {
    const btn = document.getElementById("btn-scan");
    const list = document.getElementById("network-list");
    btn.disabled = true;
    btn.textContent = "Scanning...";
    list.innerHTML = '<p class="loading">Scanning for networks...</p>';

    try {
        const result = await apiGet("/api/wifi/scan");
        const networks = result.networks ?? result;
        if (networks.length === 0) {
            list.innerHTML = "<p>No networks found.</p>";
        } else {
            list.innerHTML = networks.map((n) => `
                <div class="network-item" onclick="showConnectDialog('${n.ssid}', '${n.security}')">
                    <div class="network-info">
                        <div class="network-ssid">${n.ssid}</div>
                        <div class="network-detail">
                            ${n.security}
                            ${n.connected ? ' <span class="network-connected">&#x2713; Connected</span>' : ""}
                        </div>
                    </div>
                    <div class="network-signal">${signalBars(n.signal)}</div>
                </div>`
            ).join("");
        }
    } catch (e) {
        list.innerHTML = '<p class="message error">Scan failed</p>';
    }

    btn.disabled = false;
    btn.textContent = "Scan";
}

// ----------------------------------------------------------------
// WiFi Connect / Disconnect
// ----------------------------------------------------------------

function showConnectDialog(ssid, security) {
    document.getElementById("connect-ssid").textContent = ssid;
    document.getElementById("connect-form").dataset.ssid = ssid;
    const pwGroup = document.getElementById("password-group");
    if (security === "Open") {
        pwGroup.classList.add("hidden");
    } else {
        pwGroup.classList.remove("hidden");
    }
    document.getElementById("wifi-password").value = "";
    document.getElementById("connect-dialog").classList.remove("hidden");
}

function closeDialog() {
    document.getElementById("connect-dialog").classList.add("hidden");
}

async function connectToNetwork(event) {
    event.preventDefault();
    const form = document.getElementById("connect-form");
    const ssid = form.dataset.ssid;
    const password = document.getElementById("wifi-password").value;

    closeDialog();

    const list = document.getElementById("network-list");
    list.innerHTML = `<p class="loading">Connecting to ${ssid}...</p>`;

    try {
        const result = await apiPost("/api/wifi/connect", { ssid, password });
        if (result.success) {
            fetchWifiStatus();
            scanNetworks();
            fetchSavedNetworks();
        } else {
            list.innerHTML = `<p class="message error">${result.message}</p>`;
        }
    } catch (e) {
        list.innerHTML = '<p class="message error">Connection failed</p>';
    }
}

async function disconnectWifi() {
    try {
        await apiPost("/api/wifi/disconnect", {});
        fetchWifiStatus();
    } catch (e) {
        console.error("Disconnect failed:", e);
    }
}

// ----------------------------------------------------------------
// Saved Networks
// ----------------------------------------------------------------

async function fetchSavedNetworks() {
    const el = document.getElementById("saved-networks");
    if (!el) return;

    try {
        const saved = await apiGet("/api/wifi/saved");
        if (saved.length === 0) {
            el.innerHTML = "<p>No saved networks.</p>";
        } else {
            el.innerHTML = saved.map((ssid) => `
                <div class="saved-item">
                    <span>${ssid}</span>
                    <button class="btn btn-secondary btn-small" onclick="forgetNetwork('${ssid}')">Forget</button>
                </div>`
            ).join("");
        }
    } catch (e) {
        el.innerHTML = '<p class="message error">Failed to load</p>';
    }
}

async function forgetNetwork(ssid) {
    try {
        await apiPost("/api/wifi/forget", { ssid });
        fetchSavedNetworks();
    } catch (e) {
        console.error("Forget failed:", e);
    }
}

// ----------------------------------------------------------------
// Config
// ----------------------------------------------------------------

async function loadConfig() {
    try {
        const config = await apiGet("/api/config");
        setField("device-name", config.game.device_name);
        setField("default-timer", config.game.default_timer);
        setField("timer-step", config.game.timer_step);
        setField("default-digits", config.modes.random_code.default_digits);
        setField("max-code-length", config.modes.set_code.max_code_length);
        setField("crack-interval", config.modes.usb_key_cracker.crack_interval);
        setField("penalty-seconds", config.game.penalty_seconds);
        setField("volume", config.audio.volume);
        document.getElementById("volume-value").textContent = config.audio.volume;
        document.getElementById("backlight").checked = config.display.backlight;
        // Logging settings
        setField("log-level", config.logging.level);
        setField("max-files", config.logging.max_files);

        // Mark customized fields
        const customized = config.customized || [];
        document.querySelectorAll("[data-key]").forEach((el) => {
            const group = el.closest(".form-group");
            if (group) {
                if (customized.includes(el.dataset.key)) {
                    group.classList.add("customized");
                } else {
                    group.classList.remove("customized");
                }
            }
        });
    } catch (e) {
        console.error("Failed to load config:", e);
    }
}

function setField(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

async function saveConfig(event) {
    event.preventDefault();
    const data = {};
    document.querySelectorAll("[data-key]").forEach((el) => {
        const key = el.dataset.key;
        if (el.type === "checkbox") {
            data[key] = el.checked;
        } else if (el.type === "number" || el.type === "range") {
            data[key] = parseFloat(el.value);
        } else {
            data[key] = el.value;
        }
    });

    try {
        const result = await apiPost("/api/config", data);
        showMessage("config-message", result.message, result.success ? "success" : "error");
        if (result.success) loadConfig();
    } catch (e) {
        showMessage("config-message", "Save failed", "error");
    }
}

async function resetConfig() {
    if (!confirm("Reset all settings to defaults? This cannot be undone.")) return;
    try {
        const result = await apiPost("/api/config/reset", {});
        showMessage("config-message", result.message, result.success ? "success" : "error");
        if (result.success) loadConfig();
    } catch (e) {
        showMessage("config-message", "Reset failed", "error");
    }
}

// ----------------------------------------------------------------
// Tournament
// ----------------------------------------------------------------

let _tournamentModes = [];

async function loadTournament() {
    try {
        const data = await apiGet("/api/tournament");
        _tournamentModes = data.available_modes || [];

        document.getElementById("tournament-enabled").checked = data.enabled;
        document.getElementById("tournament-pin").value = data.pin || "0000";

        // Populate mode dropdown
        const select = document.getElementById("tournament-mode");
        if (!select) return;
        select.innerHTML = "";
        _tournamentModes.forEach((m) => {
            const opt = document.createElement("option");
            opt.value = m.module;
            opt.textContent = m.name;
            select.appendChild(opt);
        });
        select.value = data.mode;

        // Render settings for current mode
        renderModeSettings(data.mode, data.settings);

        // Show PIN warning if default
        const pinWarn = document.getElementById("pin-warning");
        if (pinWarn) {
            if (data.pin === "0000") {
                pinWarn.classList.remove("hidden");
            } else {
                pinWarn.classList.add("hidden");
            }
        }
    } catch (e) {
        console.error("Failed to load tournament config:", e);
    }
}

function onTournamentModeChange() {
    const select = document.getElementById("tournament-mode");
    renderModeSettings(select.value, {});
}

function renderModeSettings(moduleKey, currentSettings) {
    const container = document.getElementById("mode-settings-container");
    if (!container) return;

    const mode = _tournamentModes.find((m) => m.module === moduleKey);
    if (!mode || mode.options.length === 0) {
        container.innerHTML = "";
        return;
    }

    let html = '<h3>Mode Settings</h3>';
    mode.options.forEach((opt) => {
        const val = currentSettings[opt.key] !== undefined ? currentSettings[opt.key] : opt.default;
        const id = `tmode-${opt.key}`;

        if (opt.type === "range") {
            let labelExtra = "";
            if (opt.key === "timer") {
                const mins = Math.floor(val / 60);
                const secs = val % 60;
                labelExtra = ` (${mins}:${String(secs).padStart(2, "0")})`;
            }
            html += `
                <div class="form-group">
                    <label for="${id}">${opt.label}${labelExtra}</label>
                    <input type="number" id="${id}" data-mode-key="${opt.key}"
                           value="${val}" min="${opt.min}" max="${opt.max}" step="${opt.step}">
                </div>`;
        } else if (opt.type === "code") {
            html += `
                <div class="form-group">
                    <label for="${id}">${opt.label}</label>
                    <input type="text" id="${id}" data-mode-key="${opt.key}"
                           value="${val || ""}" maxlength="${opt.max}" pattern="[0-9]*"
                           inputmode="numeric" placeholder="Enter digits..."
                           oninput="this.value = this.value.replace(/[^0-9]/g, '')">
                </div>`;
        }
    });

    container.innerHTML = html;

    // Add timer format update listener
    container.querySelectorAll('input[data-mode-key="timer"]').forEach((el) => {
        el.addEventListener("input", function () {
            const v = parseInt(this.value) || 0;
            const m = Math.floor(v / 60);
            const s = v % 60;
            const label = this.closest(".form-group").querySelector("label");
            const baseLabel = label.textContent.split("(")[0].trim();
            label.textContent = `${baseLabel} (${m}:${String(s).padStart(2, "0")})`;
        });
    });
}

async function saveTournament(event) {
    event.preventDefault();

    const enabled = document.getElementById("tournament-enabled").checked;
    const mode = document.getElementById("tournament-mode").value;
    const pin = document.getElementById("tournament-pin").value;

    // Collect mode settings
    const settings = {};
    document.querySelectorAll("[data-mode-key]").forEach((el) => {
        const key = el.dataset.modeKey;
        if (el.type === "number") {
            settings[key] = parseFloat(el.value);
        } else {
            settings[key] = el.value;
        }
    });

    try {
        const resp = await fetch("/api/tournament", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled, mode, pin, settings }),
        });
        const result = await resp.json();

        if (resp.ok && result.success) {
            showMessage("tournament-message", result.message, "success");
            loadTournament();
        } else {
            showMessage("tournament-message", result.message || "Save failed", "error");
        }
    } catch (e) {
        showMessage("tournament-message", "Save failed", "error");
    }
}

function togglePinVisibility() {
    const pin = document.getElementById("tournament-pin");
    const btn = pin.nextElementSibling;
    if (pin.type === "password") {
        pin.type = "text";
        btn.textContent = "Hide";
    } else {
        pin.type = "password";
        btn.textContent = "Show";
    }
}

// ----------------------------------------------------------------
// Log Viewer
// ----------------------------------------------------------------

let _logAllLines = [];

async function fetchLogList() {
    try {
        const files = await apiGet("/api/logs");
        const select = document.getElementById("log-select");
        if (!select) return;

        const prev = select.value;
        select.innerHTML = '<option value="">Select a log file...</option>';

        files.forEach((f) => {
            const size = f.size < 1024
                ? `${f.size} B`
                : f.size < 1048576
                    ? `${(f.size / 1024).toFixed(1)} KB`
                    : `${(f.size / 1048576).toFixed(1)} MB`;
            const date = new Date(f.modified * 1000).toLocaleString();
            const opt = document.createElement("option");
            opt.value = f.name;
            opt.textContent = `${f.name} (${size}, ${date})`;
            select.appendChild(opt);
        });

        // Restore previous selection or auto-select first file.
        if (prev && [...select.options].some((o) => o.value === prev)) {
            select.value = prev;
        } else if (files.length > 0) {
            select.value = files[0].name;
        }
        loadLogFile();
    } catch (e) {
        const info = document.getElementById("log-files-info");
        if (info) info.innerHTML = '<p class="message error">Failed to load log list</p>';
    }
}

async function loadLogFile() {
    const select = document.getElementById("log-select");
    const content = document.getElementById("log-content");
    if (!select || !content) return;

    const filename = select.value;
    if (!filename) {
        content.innerHTML = '<p class="loading">Select a log file above...</p>';
        document.getElementById("log-stats").textContent = "";
        return;
    }

    content.innerHTML = '<p class="loading">Loading...</p>';

    const linesParam = document.getElementById("log-lines").value;
    const url = linesParam === "0"
        ? `/api/logs/${filename}?lines=999999`
        : `/api/logs/${filename}?lines=${linesParam}`;

    try {
        const data = await apiGet(url);
        _logAllLines = data.lines;

        renderLogLines(_logAllLines);

        const stats = document.getElementById("log-stats");
        if (data.total_lines > data.lines.length) {
            stats.textContent = `Showing last ${data.lines.length} of ${data.total_lines} lines`;
        } else {
            stats.textContent = `${data.total_lines} lines total`;
        }
    } catch (e) {
        content.innerHTML = '<p class="message error">Failed to load log file</p>';
    }
}

function renderLogLines(lines) {
    const content = document.getElementById("log-content");
    const filter = (document.getElementById("log-filter").value || "").trim().toLowerCase();

    const filtered = filter
        ? lines.filter((l) => l.toLowerCase().includes(filter))
        : lines;

    if (filtered.length === 0) {
        content.innerHTML = filter
            ? '<p class="loading">No lines match the filter.</p>'
            : '<p class="loading">Log file is empty.</p>';
        return;
    }

    const html = filtered.map((line) => {
        let cls = "log-line";
        if (line.includes("[CRITICAL]")) cls += " log-line-critical";
        else if (line.includes("[ERROR]")) cls += " log-line-error";
        else if (line.includes("[WARNING]")) cls += " log-line-warning";
        else if (line.includes("[DEBUG]")) cls += " log-line-debug";

        let escaped = line
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        if (filter) {
            const re = new RegExp(`(${filter.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
            escaped = escaped.replace(re, "<mark>$1</mark>");
        }

        return `<div class="${cls}">${escaped}</div>`;
    }).join("");

    content.innerHTML = html;
    // Auto-scroll to bottom.
    content.scrollTop = content.scrollHeight;
}

function filterLogLines() {
    renderLogLines(_logAllLines);
}

// ----------------------------------------------------------------
// System Info
// ----------------------------------------------------------------

async function fetchSystemInfo() {
    const el = document.getElementById("system-info");
    if (!el) return;

    try {
        const info = await apiGet("/api/system");
        const rows = [
            ["Version", info.version],
            ["Platform", `${info.platform} (${info.machine})`],
            ["Python", info.python],
            ["Hostname", info.hostname],
            ["CPU Temp", info.cpu_temp],
            ["Uptime", info.uptime],
            ["RAM", `${info.ram_used} / ${info.ram_total} (${info.ram_percent})`],
            ["Mock Mode", info.mock_mode ? "Yes" : "No"],
        ];
        el.innerHTML = `<div class="info-table">${rows.map(
            ([label, value]) => `
                <div class="info-row">
                    <span class="info-label">${label}</span>
                    <span class="info-value">${value}</span>
                </div>`
        ).join("")}</div>`;
    } catch (e) {
        el.innerHTML = '<p class="message error">Failed to load system info</p>';
    }
}

// ----------------------------------------------------------------
// Battery
// ----------------------------------------------------------------

async function fetchBatteryInfo() {
    const el = document.getElementById("battery-info");
    if (!el) return;

    try {
        const info = await apiGet("/api/battery");

        if (!info.available) {
            el.innerHTML = '<p class="message info">No battery HAT detected.</p>';
            return;
        }

        const levelClass = info.level > 50 ? "good" : info.level > 20 ? "warn" : "crit";

        let statusText = "Unknown";
        if (info.charging === true) {
            statusText = "Charging";
        } else if (info.charging === false) {
            statusText = "Discharging";
        }

        let timeRow;
        if (info.power_plugged === true) {
            let chargeText = "Charging...";
            if (info.charge_minutes !== null && info.charge_minutes !== undefined) {
                const h = Math.floor(info.charge_minutes / 60);
                const m = info.charge_minutes % 60;
                chargeText = h > 0 ? `~${h}h ${m}min` : `~${m}min`;
            }
            timeRow = ["Est. Charge Time", chargeText];
        } else {
            let runtimeText = "N/A";
            if (info.runtime_minutes !== null && info.runtime_minutes !== undefined) {
                const h = Math.floor(info.runtime_minutes / 60);
                const m = info.runtime_minutes % 60;
                runtimeText = h > 0 ? `~${h}h ${m}min` : `~${m}min`;
            }
            timeRow = ["Est. Runtime", runtimeText];
        }

        const rows = [
            ["Status", statusText],
            ["Voltage", info.voltage !== null ? `${info.voltage.toFixed(2)} V` : "N/A"],
            ["Current", info.current_ma !== null ? `${info.current_ma.toFixed(0)} mA` : "N/A"],
            timeRow,
            ["External Power", info.power_plugged === true ? "Connected" : info.power_plugged === false ? "Not connected" : "N/A"],
        ];

        el.innerHTML = `
            <div class="battery-level-display">
                <div class="battery-percent ${levelClass}">${info.level}%</div>
                <div class="battery-bar">
                    <div class="battery-fill ${levelClass}" style="width: ${info.level}%"></div>
                </div>
            </div>
            <div class="info-table">${rows.map(
                ([label, value]) => `
                    <div class="info-row">
                        <span class="info-label">${label}</span>
                        <span class="info-value">${value}</span>
                    </div>`
            ).join("")}</div>`;
    } catch (e) {
        el.innerHTML = '<p class="message error">Failed to load battery info</p>';
    }
}

// ----------------------------------------------------------------
// Update
// ----------------------------------------------------------------

async function checkUpdate() {
    const btn = document.getElementById("btn-check");
    const status = document.getElementById("update-status");
    btn.disabled = true;
    btn.textContent = "Checking...";

    try {
        const data = await apiGet("/api/update/check");
        let html = `
            <div class="info-table">
                <div class="info-row">
                    <span class="info-label">Current Version</span>
                    <span class="info-value">${data.current_version}</span>
                </div>`;

        if (data.available) {
            if (data.latest_version) {
                html += `
                    <div class="info-row">
                        <span class="info-label">Latest Version</span>
                        <span class="info-value">${data.latest_version}</span>
                    </div>`;
            }
            html += `
                <div class="info-row">
                    <span class="info-label">Status</span>
                    <span class="info-value" style="color: var(--warning)">${data.message}</span>
                </div>`;
            if (data.changes) {
                html += `</div><h3>Changes</h3><ul>${data.changes.map(
                    (c) => `<li>${c}</li>`
                ).join("")}</ul>`;
            } else {
                html += "</div>";
            }
            document.getElementById("btn-install").classList.remove("hidden");
        } else {
            html += `
                <div class="info-row">
                    <span class="info-label">Status</span>
                    <span class="info-value" style="color: var(--success)">Up to date</span>
                </div>
            </div>`;
            document.getElementById("btn-install").classList.add("hidden");
        }

        status.innerHTML = html;
    } catch (e) {
        status.innerHTML = '<p class="message error">Check failed</p>';
    }

    btn.disabled = false;
    btn.textContent = "Check for Updates";
}

async function installUpdate() {
    const btn = document.getElementById("btn-install");
    btn.disabled = true;
    btn.textContent = "Installing...";

    try {
        const result = await apiPost("/api/update/install", {});
        showMessage("update-message", result.message, result.success ? "success" : "error");
        if (result.success) {
            btn.classList.add("hidden");
            document.getElementById("btn-restart").classList.remove("hidden");
        }
    } catch (e) {
        showMessage("update-message", "Update failed", "error");
    }

    btn.disabled = false;
    btn.textContent = "Install Update";
}

async function restartService() {
    if (!confirm("Restart the service? The device will be briefly unavailable.\nPlease reload this page manually after the restart has finished.")) return;

    const btn = document.getElementById("btn-restart");
    btn.disabled = true;
    btn.textContent = "Restarting...";
    const statusDiv = document.getElementById("update-status");

    try {
        await apiPost("/api/service/restart", {});
    } catch (e) {
        // Ignore — network error means the service is already restarting
    }

    statusDiv.innerHTML =
        '<p style="color: var(--warning)">Restart triggered. Please reload this page manually once the device is back online.</p>';
    btn.classList.add("hidden");
}

// ----------------------------------------------------------------
// Init — fetch status on every page
// ----------------------------------------------------------------

fetchWifiStatus();
