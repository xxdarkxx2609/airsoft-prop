/* Tournament page */

let _availableModes = [];
let _gameInProgress = false;

// ----------------------------------------------------------------
// Load
// ----------------------------------------------------------------

async function loadTournament() {
    try {
        const data = await apiGet("/api/tournament");
        _availableModes = data.available_modes || [];
        _gameInProgress = !!data.game_in_progress;

        const enabledToggle = document.getElementById("tournament-enabled");
        if (enabledToggle) enabledToggle.checked = !!data.enabled;

        const pinInput = document.getElementById("tournament-pin");
        if (pinInput) pinInput.value = data.pin || "0000";

        // Populate mode dropdown
        const select = document.getElementById("tournament-mode");
        if (select) {
            select.innerHTML = "";
            _availableModes.forEach(m => {
                const opt = document.createElement("option");
                opt.value = m.module;
                opt.textContent = m.name;
                select.appendChild(opt);
            });
            select.value = data.mode || "";
        }

        // Render settings for the current mode
        renderModeSettings(data.mode, data.settings || {});

        // Game-in-progress banner
        const warnBanner = document.getElementById("game-in-progress-warning");
        if (warnBanner) warnBanner.style.display = _gameInProgress ? "" : "none";

        // Disable save button when game in progress
        const saveBtn = document.getElementById("save-tournament-btn");
        if (saveBtn) {
            saveBtn.disabled = _gameInProgress;
            saveBtn.title = _gameInProgress ? "Cannot save while a game is in progress." : "";
        }

        if (_gameInProgress) {
            showMessage("tournament-msg", "A game is currently in progress. Tournament settings cannot be saved.", "warning");
        }
    } catch (_) {
        showMessage("tournament-msg", "Failed to load tournament configuration.", "error");
    }
}

// ----------------------------------------------------------------
// Mode change
// ----------------------------------------------------------------

function onModeChange() {
    const select = document.getElementById("tournament-mode");
    if (select) renderModeSettings(select.value, {});
}

// ----------------------------------------------------------------
// Render mode settings
// ----------------------------------------------------------------

function renderModeSettings(moduleKey, currentSettings) {
    const container = document.getElementById("mode-settings");
    if (!container) return;

    const mode = _availableModes.find(m => m.module === moduleKey);
    if (!mode || !mode.options || mode.options.length === 0) {
        container.innerHTML = "";
        return;
    }

    let html = "<h3>Mode Settings</h3>";

    mode.options.forEach(opt => {
        const val = currentSettings[opt.key] !== undefined ? currentSettings[opt.key] : opt.default;
        const id = `tmode-${opt.key}`;

        if (opt.type === "int" || opt.type === "timer") {
            const isTimer = opt.type === "timer";
            let labelSuffix = "";
            if (isTimer && typeof val === "number") {
                const mins = Math.floor(val / 60);
                const secs = val % 60;
                labelSuffix = ` (${mins}:${String(secs).padStart(2, "0")})`;
            }

            html += `<div class="form-group">
                <label for="${id}">${opt.label}${labelSuffix}</label>
                <div class="stepper" data-stepper>
                    <button class="stepper-btn" type="button" data-step="dec">−</button>
                    <input type="number" id="${id}" data-mode-key="${opt.key}"
                           value="${val}" min="${opt.min ?? ""}" max="${opt.max ?? ""}"
                           step="${opt.step ?? 1}" data-large-step="${opt.large_step ?? 0}">
                    <button class="stepper-btn" type="button" data-step="inc">+</button>
                </div>
            </div>`;
        } else if (opt.type === "code") {
            html += `<div class="form-group">
                <label for="${id}">${opt.label}</label>
                <input type="text" id="${id}" data-mode-key="${opt.key}"
                       value="${val || ""}" maxlength="${opt.max ?? 10}"
                       pattern="[0-9]*" inputmode="numeric" placeholder="Digits…">
            </div>`;
        } else if (opt.type === "select") {
            const choices = opt.choices || [];
            const optionsHtml = choices.map(c =>
                `<option value="${c}"${val === c ? " selected" : ""}>${c === "" ? "Random" : c}</option>`
            ).join("");
            html += `<div class="form-group">
                <label for="${id}">${opt.label}</label>
                <select id="${id}" data-mode-key="${opt.key}">${optionsHtml}</select>
            </div>`;
        } else if (opt.type === "text") {
            html += `<div class="form-group">
                <label for="${id}">${opt.label}</label>
                <input type="text" id="${id}" data-mode-key="${opt.key}"
                       value="${val || ""}" maxlength="${opt.max ?? 20}" placeholder="Optional…">
            </div>`;
        }
    });

    container.innerHTML = html;

    // Re-init steppers for new inputs
    initSteppers();

    // Timer label live update
    container.querySelectorAll("input[data-mode-key]").forEach(el => {
        const opt = mode.options.find(o => o.key === el.dataset.modeKey);
        if (!opt || opt.type !== "timer") return;
        el.addEventListener("input", function () {
            const v = parseInt(this.value) || 0;
            const m = Math.floor(v / 60);
            const s = v % 60;
            const label = this.closest(".form-group")?.querySelector("label");
            if (label) {
                const base = label.textContent.split("(")[0].trim();
                label.textContent = `${base} (${m}:${String(s).padStart(2, "0")})`;
            }
        });
    });
}

// ----------------------------------------------------------------
// Save
// ----------------------------------------------------------------

async function saveTournament(event) {
    if (event && event.preventDefault) event.preventDefault();

    if (_gameInProgress) {
        showMessage("tournament-msg", "Cannot save: a game is in progress.", "error");
        return;
    }

    const enabled = document.getElementById("tournament-enabled")?.checked ?? false;
    const mode = document.getElementById("tournament-mode")?.value || "";
    const pin = document.getElementById("tournament-pin")?.value || "0000";

    const settings = {};
    document.querySelectorAll("[data-mode-key]").forEach(el => {
        const key = el.dataset.modeKey;
        settings[key] = el.type === "number" ? parseFloat(el.value) : el.value;
    });

    try {
        const resp = await fetch("/api/tournament", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled, mode, pin, settings }),
        });
        if (resp.status === 401) { window.location.href = "/login"; return; }

        const result = await resp.json();

        if (resp.status === 409) {
            showMessage("tournament-msg", result.message || "Game in progress — cannot save.", "error");
            return;
        }

        showMessage("tournament-msg", result.message || (result.success ? "Saved." : "Save failed."), result.success ? "success" : "error");
        if (result.success) loadTournament();
    } catch (_) {
        showMessage("tournament-msg", "Save failed.", "error");
    }
}

// ----------------------------------------------------------------
// PIN visibility toggle
// ----------------------------------------------------------------

function togglePinVisibility() {
    const pin = document.getElementById("tournament-pin");
    if (!pin) return;
    const btn = document.getElementById("pin-show-btn");
    if (pin.type === "password") {
        pin.type = "text";
        if (btn) btn.textContent = "Hide";
    } else {
        pin.type = "password";
        if (btn) btn.textContent = "Show";
    }
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    loadTournament();

    const modeSelect = document.getElementById("tournament-mode");
    if (modeSelect) modeSelect.addEventListener("change", onModeChange);

    const saveBtn = document.getElementById("save-tournament-btn");
    if (saveBtn) saveBtn.addEventListener("click", saveTournament);

    const pinToggle = document.getElementById("pin-show-btn");
    if (pinToggle) pinToggle.addEventListener("click", togglePinVisibility);
});
