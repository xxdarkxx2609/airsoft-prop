/* Battery page */

const BATTERY_SEGMENTS = 30;
const SPARKLINE_CAPACITY = 60;

let _batterySamples = [];
let _batteryInterval = null;

// ----------------------------------------------------------------
// Fetch + render
// ----------------------------------------------------------------

async function fetchBattery() {
    try {
        const data = await apiGet("/api/battery");

        if (!data.available) {
            const noEl = document.getElementById("no-battery-msg");
            const mainEl = document.getElementById("battery-panel");
            if (noEl) noEl.style.display = "";
            if (mainEl) mainEl.style.display = "none";
            return;
        }

        const noEl = document.getElementById("no-battery-msg");
        const mainEl = document.getElementById("battery-panel");
        if (noEl) noEl.style.display = "none";
        if (mainEl) mainEl.style.display = "";

        const level = data.level ?? 0;

        // Segment bar
        _renderSegBar(level);

        // Stats
        _setText("bat-level", `${level}%`);
        _setText("bat-voltage", data.voltage != null ? `${data.voltage.toFixed(2)} V` : "—");
        _setText("bat-current", data.current_ma != null ? `${Math.round(data.current_ma)} mA` : "—");
        _setText("bat-charging", data.charging === true ? "Yes" : data.charging === false ? "No" : "—");
        _setText("bat-plugged", data.power_plugged === true ? "Connected" : data.power_plugged === false ? "Not connected" : "—");

        const runMin = data.runtime_minutes;
        const chargeMin = data.charge_minutes;
        _setText("bat-runtime", runMin != null ? _formatMinutes(runMin) : "—");
        _setText("bat-charge-time", chargeMin != null ? _formatMinutes(chargeMin) : "—");

        // Sparkline sample
        _batterySamples.push({ ts: Date.now(), level });
        if (_batterySamples.length > SPARKLINE_CAPACITY) {
            _batterySamples = _batterySamples.slice(-SPARKLINE_CAPACITY);
        }
        renderSparkline(_batterySamples);
    } catch (_) {}
}

function _setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function _formatMinutes(mins) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return h > 0 ? `~${h}h ${m}min` : `~${m}min`;
}

// ----------------------------------------------------------------
// Segment bar (30 segments)
// ----------------------------------------------------------------

function _renderSegBar(level) {
    const el = document.getElementById("bat-segbar");
    if (!el) return;
    const filled = Math.round(Math.max(0, Math.min(100, level)) / 100 * BATTERY_SEGMENTS);
    const colorClass = level > 50 ? "seg-green" : level > 20 ? "seg-yellow" : "seg-red";
    el.innerHTML = Array.from({ length: BATTERY_SEGMENTS }, (_, i) =>
        `<span class="seg${i < filled ? " " + colorClass : ""}"></span>`
    ).join("");
}

// ----------------------------------------------------------------
// Sparkline SVG
// ----------------------------------------------------------------

function renderSparkline(samples) {
    const svg = document.getElementById("sparkline-svg");
    if (!svg || samples.length < 2) return;

    const W = 200;
    const H = 40;
    const values = samples.map(s => s.level);
    const minV = Math.min(...values);
    const maxV = Math.max(...values);
    const rangeV = maxV - minV || 1;

    const points = values.map((v, i) => {
        const x = (i / (values.length - 1)) * W;
        const y = H - ((v - minV) / rangeV) * H;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = `<polyline
        fill="none"
        stroke="var(--accent, #4caf50)"
        stroke-width="1.5"
        stroke-linejoin="round"
        stroke-linecap="round"
        points="${points}"/>`;
}

// ----------------------------------------------------------------
// Visibility-aware polling
// ----------------------------------------------------------------

function _startPolling() {
    if (_batteryInterval) return;
    fetchBattery();
    _batteryInterval = setInterval(fetchBattery, 10000);
}

function _stopPolling() {
    clearInterval(_batteryInterval);
    _batteryInterval = null;
}

document.addEventListener("visibilitychange", () => {
    if (document.hidden) _stopPolling(); else _startPolling();
});

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    _startPolling();
});
