/* Airsoft Prop — Shared helper module */

// ----------------------------------------------------------------
// Core API helpers
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

// ----------------------------------------------------------------
// UI helpers
// ----------------------------------------------------------------

function showMessage(id, text, type) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = text;
    el.className = `message ${type}`;
    el.style.display = "";
    el.classList.remove("hidden");
    setTimeout(() => { el.style.display = "none"; }, 5000);
}

function signalBars(signal) {
    const thresholds = [25, 50, 75, 100];
    const bars = thresholds.map(t => signal >= t);
    return `<span class="signal-bars">${bars.map(
        active => `<span class="signal-bar${active ? " active" : ""}"></span>`
    ).join("")}</span>`;
}

// ----------------------------------------------------------------
// Theme
// ----------------------------------------------------------------

function initTheme() {
    let theme;
    try {
        const stored = localStorage.getItem("ap");
        theme = stored ? JSON.parse(stored).theme : null;
    } catch (_) {
        theme = null;
    }
    if (!theme) {
        theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    document.documentElement.dataset.theme = theme;
}

function toggleTheme() {
    const current = document.documentElement.dataset.theme || "light";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
        const stored = JSON.parse(localStorage.getItem("ap") || "{}");
        stored.theme = next;
        localStorage.setItem("ap", JSON.stringify(stored));
    } catch (_) {}
}

// ----------------------------------------------------------------
// Mobile drawer
// ----------------------------------------------------------------

function openDrawer() {
    document.body.classList.add("sidebar-open");
}

function closeDrawer() {
    document.body.classList.remove("sidebar-open");
}

// ----------------------------------------------------------------
// Sidebar clock (live uptime ticker)
// ----------------------------------------------------------------

async function initSidebarClock() {
    const uptimeEl = document.getElementById("sb-uptime");
    const ipEl     = document.getElementById("sb-ip");
    if (!uptimeEl && !ipEl) return;

    let bootEpoch = null;

    try {
        const data = await apiGet("/api/system");
        if (data.uptime_seconds !== undefined) {
            bootEpoch = Date.now() - data.uptime_seconds * 1000;
        }
        if (ipEl && data.ip_address) {
            ipEl.textContent = data.ip_address;
        }
    } catch (_) {}

    function tick() {
        if (!uptimeEl) return;
        if (bootEpoch === null) {
            uptimeEl.textContent = "UP --:--:--";
            return;
        }
        const secs = Math.floor((Date.now() - bootEpoch) / 1000);
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        const s = secs % 60;
        uptimeEl.textContent = `UP ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    tick();
    setInterval(tick, 1000);
}

// ----------------------------------------------------------------
// Steppers
// ----------------------------------------------------------------

function initSteppers() {
    document.querySelectorAll("[data-stepper]").forEach(container => {
        const input = container.querySelector("input[type=number]");
        const dec = container.querySelector("[data-step=dec]");
        const inc = container.querySelector("[data-step=inc]");
        const large = parseInt(input.dataset.largeStep || "0", 10);

        function clamp(v) {
            const min = parseFloat(input.min);
            const max = parseFloat(input.max);
            if (!isNaN(min) && v < min) return min;
            if (!isNaN(max) && v > max) return max;
            return v;
        }

        function step(delta) {
            const current = parseFloat(input.value) || 0;
            input.value = clamp(current + delta);
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
        }

        const baseStep = parseFloat(input.step) || 1;

        if (dec) {
            dec.addEventListener("click", () => step(-baseStep));
            dec.addEventListener("dblclick", () => large && step(-large));
        }
        if (inc) {
            inc.addEventListener("click", () => step(baseStep));
            inc.addEventListener("dblclick", () => large && step(large));
        }
    });
}

// ----------------------------------------------------------------
// WiFi status chip (header)
// ----------------------------------------------------------------

async function fetchWifiStatus() {
    try {
        const status = await apiGet("/api/wifi/status");

        // Header chip
        const headerDot  = document.getElementById("header-wifi-dot");
        const headerText = document.getElementById("header-wifi-text");
        if (headerDot && headerText) {
            if (status.ap_mode) {
                headerDot.className = "chip-dot ap-mode";
                headerText.textContent = "AP: " + (status.ssid || "hotspot");
            } else if (status.connected) {
                headerDot.className = "chip-dot connected";
                headerText.textContent = status.ssid || status.ip_address || "Connected";
            } else {
                headerDot.className = "chip-dot disconnected";
                headerText.textContent = "No WiFi";
            }
        }

        // Legacy footer elements (kept for any templates that still reference them)
        const dot  = document.getElementById("connection-status");
        const text = document.getElementById("connection-text");
        if (dot)  dot.className  = status.connected ? "status-dot connected" : "status-dot disconnected";
        if (text) text.textContent = status.connected ? `${status.ssid} — ${status.ip_address}` : "Not connected";
    } catch (_) {}
}

// ----------------------------------------------------------------
// DOMContentLoaded bootstrap
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initSteppers();
    fetchWifiStatus();
    initSidebarClock();

    const themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

    const burgerBtn = document.getElementById("burger-btn");
    if (burgerBtn) burgerBtn.addEventListener("click", openDrawer);

    const scrim = document.getElementById("sidebar-scrim");
    if (scrim) scrim.addEventListener("click", closeDrawer);

    // Re-poll WiFi status every 30 s
    setInterval(fetchWifiStatus, 30000);
});
