/* Dashboard page — game state polling, battery, system stats */

let _pollInterval = null;
let _lastGameData = null;
let _countdownInterval = null;

// ----------------------------------------------------------------
// Game state polling
// ----------------------------------------------------------------

async function pollGameState() {
    try {
        const data = await apiGet("/api/game-state");
        _lastGameData = data;
        renderGameState(data);
        if (data.recent_events) renderRecentEvents(data.recent_events);
        if (data.device_name) {
            const dev = document.getElementById("stat-device-name");
            if (dev) dev.textContent = data.device_name;
        }
    } catch (_) {}
}

function startPolling() {
    if (_pollInterval) return;
    pollGameState();
    _pollInterval = setInterval(pollGameState, 2000);
}

function stopPolling() {
    clearInterval(_pollInterval);
    _pollInterval = null;
    clearInterval(_countdownInterval);
    _countdownInterval = null;
}

document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopPolling(); else startPolling();
});

// ----------------------------------------------------------------
// Game state render
// ----------------------------------------------------------------

function renderGameState(data) {
    const badge = document.getElementById("state-badge");
    if (badge) {
        const state = String(data.state || "UNKNOWN").toLowerCase();
        badge.textContent = state;
        badge.className = "chip state-" + state;
    }

    const armedStrip = document.getElementById("armed-strip");
    if (!armedStrip) return;

    const isArmed = String(data.state || "").toLowerCase() === "armed";
    armedStrip.style.display = isArmed ? "" : "none";

    const modeName = document.getElementById("armed-mode-name");
    if (modeName) modeName.textContent = (data.armed && data.armed.mode) || "";

    if (!isArmed) {
        clearInterval(_countdownInterval);
        _countdownInterval = null;
        return;
    }

    const armed = data.armed || {};
    const snapshotTs = (armed.snapshot_ts || Date.now() / 1000) * 1000;
    const remainingAtSnapshot = armed.remaining_seconds || 0;
    const total = armed.total_seconds || remainingAtSnapshot || 1;

    function updateCountdown() {
        const elapsed = (Date.now() - snapshotTs) / 1000;
        const remaining = Math.max(0, remainingAtSnapshot - elapsed);
        const pct = Math.min(100, Math.max(0, (remaining / total) * 100));

        const mins = Math.floor(remaining / 60);
        const secs = Math.floor(remaining % 60);
        const label = document.getElementById("armed-countdown");
        if (label) label.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;

        const bar = document.getElementById("armed-progress-fill");
        if (bar) {
            bar.style.width = pct + "%";
        }
        const progress = document.getElementById("armed-progress");
        if (progress) progress.setAttribute("aria-valuenow", String(Math.round(pct)));
    }

    clearInterval(_countdownInterval);
    updateCountdown();
    _countdownInterval = setInterval(updateCountdown, 500);
}

// ----------------------------------------------------------------
// Recent events
// ----------------------------------------------------------------

function renderRecentEvents(events) {
    const el = document.getElementById("recent-events");
    if (!el) return;

    if (!events || events.length === 0) {
        el.innerHTML = "<li class=\"empty dim\">No recent events.</li>";
        return;
    }

    const TYPE_COLORS = {
        arm: "chip-warning",
        defuse: "chip-success",
        detonate: "chip-danger",
        plant: "chip-warning",
        boot: "chip-info",
        error: "chip-danger",
        info: "",
    };

    const rows = [...events].reverse().map(ev => {
        const ts = new Date(ev.ts).toLocaleTimeString();
        const color = TYPE_COLORS[ev.type] || "";
        const type = String(ev.type).replace(/&/g, "&amp;").replace(/</g, "&lt;");
        const msg = String(ev.message || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
        return `<li class="event-row">
            <span class="event-ts">${ts}</span>
            <span class="chip ${color}">${type}</span>
            <span class="event-msg">${msg}</span>
        </li>`;
    }).join("");

    el.innerHTML = rows;
}

// ----------------------------------------------------------------
// Battery segment bar (32 segments)
// ----------------------------------------------------------------

function renderBatterySegbar(level) {
    const el = document.getElementById("battery-segbar");
    if (!el) return;
    const total = 32;
    const filled = Math.round(Math.max(0, Math.min(100, level)) / 100 * total);
    const colorClass = level > 50 ? "seg-green" : level > 20 ? "seg-yellow" : "seg-red";
    el.innerHTML = Array.from({ length: total }, (_, i) =>
        `<span class="seg${i < filled ? " " + colorClass : ""}"></span>`
    ).join("");
}

// ----------------------------------------------------------------
// Battery fetch
// ----------------------------------------------------------------

async function fetchBatteryPanel() {
    try {
        const data = await apiGet("/api/battery");
        const levelEl = document.getElementById("stat-battery-level");
        const chargingEl = document.getElementById("stat-charging");

        if (!data.available) {
            if (levelEl) levelEl.textContent = "—";
            if (chargingEl) chargingEl.textContent = "—";
            return;
        }

        renderBatterySegbar(data.level || 0);

        if (levelEl) {
            const level = data.level ?? 0;
            const voltage = data.voltage != null ? ` · ${data.voltage.toFixed(2)} V` : "";
            levelEl.textContent = `${level}%${voltage}`;
        }
        if (chargingEl) {
            chargingEl.textContent = data.charging === true
                ? (data.power_plugged ? "Charging" : "Yes")
                : (data.power_plugged ? "Plugged (not charging)" : "On battery");
        }
    } catch (_) {}
}

// ----------------------------------------------------------------
// System + WiFi stats
// ----------------------------------------------------------------

async function fetchSystemPanel() {
    try {
        const data = await apiGet("/api/system");
        const fields = {
            "stat-version": data.version,
            "stat-platform": data.platform,
            "stat-uptime": data.uptime,
        };
        for (const [id, val] of Object.entries(fields)) {
            const el = document.getElementById(id);
            if (el && val != null) el.textContent = val;
        }
    } catch (_) {}
}

async function fetchWifiPanel() {
    try {
        const data = await apiGet("/api/wifi/status");
        const ssid = document.getElementById("stat-wifi-ssid");
        const ip = document.getElementById("stat-wifi-ip");
        if (ssid) ssid.textContent = data.ssid || (data.ap_mode ? "AP mode" : "—");
        if (ip) ip.textContent = data.ip_address || "—";
    } catch (_) {}
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    startPolling();
    fetchBatteryPanel();
    fetchSystemPanel();
    fetchWifiPanel();
    setInterval(fetchBatteryPanel, 10000);
    setInterval(fetchSystemPanel, 30000);
    setInterval(fetchWifiPanel, 15000);
});
