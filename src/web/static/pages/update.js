/* Update page */

function _esc(str) {
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function _setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

// ----------------------------------------------------------------
// Check for update
// ----------------------------------------------------------------

async function checkUpdate() {
    const btn = document.getElementById("check-update-btn");
    const installBtn = document.getElementById("install-update-btn");
    const changesList = document.getElementById("changes-list");

    if (btn) { btn.disabled = true; btn.textContent = "Checking…"; }
    showMessage("update-msg", "Checking for updates…", "warning");

    try {
        const data = await apiGet("/api/update/check");

        _setText("current-version", data.current_version || "—");
        _setText("latest-version", data.latest_version || "—");
        _setText("commits-behind", data.commits_behind != null ? String(data.commits_behind) : "—");
        _setText("last-checked", new Date().toLocaleString());

        if (changesList) {
            if (Array.isArray(data.changes) && data.changes.length > 0) {
                changesList.innerHTML = data.changes.map(c => `<li>${_esc(c)}</li>`).join("");
            } else {
                changesList.innerHTML = "<li class=\"changes-placeholder\">No changelog available.</li>";
            }
        }

        if (data.available) {
            showMessage("update-msg", data.message || "Update available.", "warning");
            if (installBtn) installBtn.disabled = false;
        } else {
            showMessage("update-msg", "Up to date.", "success");
            if (installBtn) installBtn.disabled = true;
        }
    } catch (_) {
        showMessage("update-msg", "Check failed. Is the device online?", "error");
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Check for Updates"; }
    }
}

// ----------------------------------------------------------------
// Install update
// ----------------------------------------------------------------

async function installUpdate() {
    if (!confirm("Install the update? The device will need to be restarted afterwards.")) return;

    const btn = document.getElementById("install-update-btn");
    if (btn) { btn.disabled = true; btn.textContent = "Installing…"; }

    try {
        const result = await apiPost("/api/update/install", {});
        showMessage("update-msg", result.message || (result.success ? "Update installed. Restart the service to apply." : "Install failed."), result.success ? "success" : "error");
    } catch (_) {
        showMessage("update-msg", "Install failed.", "error");
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Install Update"; }
    }
}

// ----------------------------------------------------------------
// Restart service after update
// ----------------------------------------------------------------

async function restartService() {
    if (!confirm("Restart the service now?")) return;

    const btn = document.getElementById("restart-service-btn");
    const statusEl = document.getElementById("restart-status");
    if (btn) { btn.disabled = true; btn.textContent = "Restarting…"; }
    if (statusEl) { statusEl.style.display = ""; statusEl.textContent = "Sending restart request…"; }

    try {
        const result = await apiPost("/api/service/restart", {});
        if (result.restart_verified === false) {
            if (statusEl) statusEl.textContent = "Restart sent but not verified. The service may still be restarting.";
            if (btn) { btn.disabled = false; btn.textContent = "Restart Service"; }
            return;
        }
    } catch (_) {
        // Network drop likely means service restarted — proceed to poll
    }

    if (statusEl) statusEl.textContent = "Service restarting… waiting for reconnection.";

    let attempts = 0;
    const timer = setInterval(async () => {
        attempts++;
        try {
            const resp = await fetch("/", { cache: "no-store" });
            if (resp.ok) {
                clearInterval(timer);
                if (statusEl) statusEl.textContent = "Back online! Reloading…";
                setTimeout(() => window.location.reload(), 1000);
            }
        } catch (_) {}

        if (attempts >= 20) {
            clearInterval(timer);
            if (statusEl) statusEl.textContent = "Service restarted. Please reload manually.";
            if (btn) { btn.disabled = false; btn.textContent = "Restart Service"; }
        }
    }, 3000);
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    const checkBtn = document.getElementById("check-update-btn");
    if (checkBtn) checkBtn.addEventListener("click", checkUpdate);

    const installBtn = document.getElementById("install-update-btn");
    if (installBtn) installBtn.addEventListener("click", installUpdate);

    const restartBtn = document.getElementById("restart-service-btn");
    if (restartBtn) restartBtn.addEventListener("click", restartService);

    // Load current version on page load
    checkUpdate();
});
