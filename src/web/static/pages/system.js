/* System page */

// ----------------------------------------------------------------
// System info
// ----------------------------------------------------------------

async function fetchSystemInfo() {
    try {
        const data = await apiGet("/api/system");

        const fields = {
            "sys-version": data.version,
            "sys-platform": data.platform ? `${data.platform} (${data.machine || ""})` : null,
            "sys-python": data.python,
            "sys-hostname": data.hostname,
            "sys-cpu-temp": data.cpu_temp,
            "sys-uptime": data.uptime,
            "sys-ram-used": data.ram_used,
            "sys-ram-total": data.ram_total,
            "sys-ram-percent": data.ram_percent,
        };

        for (const [id, val] of Object.entries(fields)) {
            const el = document.getElementById(id);
            if (el && val != null) el.textContent = val;
        }

        const ramBar = document.getElementById("ram-bar");
        if (ramBar && data.ram_percent != null) {
            const pct = String(data.ram_percent).replace("%", "").trim();
            const num = parseFloat(pct);
            if (!isNaN(num)) ramBar.style.width = num + "%";
        }

        const mockBadge = document.getElementById("mock-mode-badge");
        if (mockBadge) mockBadge.style.display = data.mock_mode ? "" : "none";
    } catch (_) {
        showMessage("system-msg", "Failed to load system information.", "error");
    }
}

// ----------------------------------------------------------------
// Hardware HAL
// ----------------------------------------------------------------

async function loadHardware() {
    const container = document.getElementById("hardware-form");
    if (!container) return;

    try {
        const data = await apiGet("/api/hardware");
        const current = data.current || {};
        const available = data.available || {};

        if (Object.keys(current).length === 0) {
            container.innerHTML = "<p class=\"dim\">No hardware components found.</p>";
            return;
        }

        container.innerHTML = Object.entries(current).map(([key, selected]) => {
            const options = available[key] || [selected];
            const safeKey = String(key).replace(/&/g, "&amp;");
            const selectOptions = options.map(opt => {
                const safeOpt = String(opt).replace(/&/g, "&amp;");
                return `<option value="${safeOpt}"${opt === selected ? " selected" : ""}>${safeOpt}</option>`;
            }).join("");
            return `<div class="form-group">
                <label for="hw-${safeKey}">${safeKey}</label>
                <select id="hw-${safeKey}" data-hw-key="${safeKey}">${selectOptions}</select>
            </div>`;
        }).join("");
    } catch (_) {
        container.innerHTML = "<p class=\"message error\">Failed to load hardware configuration.</p>";
    }
}

async function saveHardware(event) {
    if (event && event.preventDefault) event.preventDefault();
    const data = {};
    document.querySelectorAll("[data-hw-key]").forEach(el => {
        data[el.dataset.hwKey] = el.value;
    });

    try {
        const result = await apiPost("/api/hardware", data);
        if (result.success) {
            showMessage("hardware-msg", (result.message || "Saved.") + " A restart is required to apply hardware changes.", "warning");
            const warn = document.getElementById("restart-warning");
            if (warn) warn.style.display = "";
        } else {
            showMessage("hardware-msg", result.message || "Save failed.", "error");
        }
    } catch (_) {
        showMessage("hardware-msg", "Save failed.", "error");
    }
}

// ----------------------------------------------------------------
// Restart service
// ----------------------------------------------------------------

async function restartService() {
    if (!confirm("Restart the service? The device will be briefly unavailable.")) return;

    const btn = document.getElementById("restart-service-btn");
    if (btn) { btn.disabled = true; btn.textContent = "Restarting…"; }

    const msgEl = document.getElementById("restart-status");
    if (msgEl) { msgEl.style.display = ""; msgEl.textContent = "Sending restart request…"; }

    try {
        const result = await apiPost("/api/service/restart", {});

        if (result.restart_verified === false) {
            if (msgEl) msgEl.textContent = "Restart sent but could not be verified. The service may still be restarting.";
            if (btn) { btn.disabled = false; btn.textContent = "Restart Service"; }
            return;
        }
    } catch (_) {
        // Network error likely means service went down — treat as success
    }

    if (msgEl) msgEl.textContent = "Service is restarting… reconnecting";

    let countdown = 15;
    const timer = setInterval(async () => {
        countdown--;
        if (msgEl) msgEl.textContent = `Reconnecting in ${countdown}s…`;

        try {
            const resp = await fetch("/", { cache: "no-store" });
            if (resp.ok) {
                clearInterval(timer);
                if (msgEl) msgEl.textContent = "Back online! Reloading…";
                setTimeout(() => window.location.reload(), 800);
            }
        } catch (_) {}

        if (countdown <= 0) {
            clearInterval(timer);
            if (msgEl) msgEl.textContent = "Service restarted. Please reload manually.";
            if (btn) { btn.disabled = false; btn.textContent = "Restart Service"; }
        }
    }, 3000);
}

// ----------------------------------------------------------------
// Reboot / shutdown
// ----------------------------------------------------------------

async function reboot() {
    if (!confirm("Reboot the device?")) return;
    try {
        const resp = await fetch("/api/system/reboot", { method: "POST" });
        if (resp.status === 404) { showMessage("system-msg", "Reboot is not supported on this device.", "error"); return; }
        const result = await resp.json();
        showMessage("system-msg", result.message || "Reboot initiated.", "warning");
    } catch (_) {
        showMessage("system-msg", "Reboot request failed.", "error");
    }
}

async function shutdown() {
    if (!confirm("Shut down the device?")) return;
    try {
        const resp = await fetch("/api/system/shutdown", { method: "POST" });
        if (resp.status === 404) { showMessage("system-msg", "Shutdown is not supported on this device.", "error"); return; }
        const result = await resp.json();
        showMessage("system-msg", result.message || "Shutdown initiated.", "warning");
    } catch (_) {
        showMessage("system-msg", "Shutdown request failed.", "error");
    }
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    fetchSystemInfo();
    loadHardware();

    const hwSaveBtn = document.getElementById("save-hardware-btn");
    if (hwSaveBtn) hwSaveBtn.addEventListener("click", saveHardware);

    const restartBtn = document.getElementById("restart-service-btn");
    if (restartBtn) restartBtn.addEventListener("click", restartService);

    const rebootBtn = document.getElementById("reboot-btn");
    if (rebootBtn) rebootBtn.addEventListener("click", reboot);

    const shutdownBtn = document.getElementById("shutdown-btn");
    if (shutdownBtn) shutdownBtn.addEventListener("click", shutdown);
});
