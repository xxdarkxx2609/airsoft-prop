/* Config page */

// ----------------------------------------------------------------
// Load / save config
// ----------------------------------------------------------------

async function loadConfig() {
    try {
        const data = await apiGet("/api/config");
        const customized = data.customized || [];

        document.querySelectorAll("[data-key]").forEach(el => {
            const key = el.dataset.key;
            const val = _getNestedKey(data, key);
            if (val === undefined) return;

            if (el.type === "checkbox") {
                el.checked = !!val;
            } else {
                el.value = val;
            }

            // Volume label sync
            if (el.id === "volume" || el.dataset.key === "audio.volume") {
                const label = document.getElementById("volume-label");
                if (label) label.textContent = Math.round(val * 100) + "%";
            }

            // Customized marker
            const group = el.closest(".form-group");
            if (group) {
                group.classList.toggle("customized", customized.includes(key));
                let badge = group.querySelector(".customized-badge");
                if (customized.includes(key)) {
                    if (!badge) {
                        badge = document.createElement("span");
                        badge.className = "customized-badge";
                        badge.textContent = "*";
                        badge.title = "Customized";
                        const lbl = group.querySelector("label");
                        if (lbl) lbl.appendChild(badge);
                    }
                } else if (badge) {
                    badge.remove();
                }
            }
        });
    } catch (_) {
        showMessage("config-msg", "Failed to load configuration.", "error");
    }
}

function _getNestedKey(obj, dotKey) {
    return dotKey.split(".").reduce((acc, k) => (acc && acc[k] !== undefined ? acc[k] : undefined), obj);
}

async function saveConfig(event) {
    if (event && event.preventDefault) event.preventDefault();
    const data = {};

    document.querySelectorAll("[data-key]").forEach(el => {
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
        showMessage("config-msg", result.message || (result.success ? "Saved." : "Save failed."), result.success ? "success" : "error");
        if (result.success) loadConfig();
    } catch (_) {
        showMessage("config-msg", "Save failed.", "error");
    }
}

async function resetConfig() {
    if (!confirm("Reset all settings to defaults? This cannot be undone.")) return;
    try {
        const result = await apiPost("/api/config/reset", {});
        showMessage("config-msg", result.message || (result.success ? "Reset complete." : "Reset failed."), result.success ? "success" : "error");
        if (result.success) loadConfig();
    } catch (_) {
        showMessage("config-msg", "Reset failed.", "error");
    }
}

// ----------------------------------------------------------------
// Volume slider live label
// ----------------------------------------------------------------

function _bindVolumeSlider() {
    const slider = document.querySelector("[data-key='audio.volume']");
    const label = document.getElementById("volume-label");
    if (!slider || !label) return;
    slider.addEventListener("input", () => {
        label.textContent = Math.round(parseFloat(slider.value) * 100) + "%";
    });
}

// ----------------------------------------------------------------
// device_name validation (max 7 chars)
// ----------------------------------------------------------------

function _bindDeviceNameValidation() {
    const input = document.querySelector("[data-key='game.device_name']");
    if (!input) return;
    input.addEventListener("input", () => {
        const warn = document.getElementById("device-name-warning");
        if (!warn) return;
        warn.style.display = input.value.length > 7 ? "" : "none";
    });
}

// ----------------------------------------------------------------
// Backlight toggle immediate feedback
// ----------------------------------------------------------------

function _bindBacklightToggle() {
    const toggle = document.querySelector("[data-key='display.backlight']");
    if (!toggle) return;
    toggle.addEventListener("change", async () => {
        try {
            await apiPost("/api/config", { "display.backlight": toggle.checked });
        } catch (_) {}
    });
}

// ----------------------------------------------------------------
// Sounds
// ----------------------------------------------------------------

async function loadSounds() {
    const el = document.getElementById("sounds-list");
    if (!el) return;
    try {
        const data = await apiGet("/api/sounds");
        const sounds = data.sounds || data;
        if (!Array.isArray(sounds) || sounds.length === 0) {
            el.innerHTML = "<p>No custom sounds uploaded.</p>";
            return;
        }
        el.innerHTML = sounds.map(s => {
            const filename = s.filename || "";
            const display = filename.replace(/&/g, "&amp;").replace(/</g, "&lt;");
            const safe = encodeURIComponent(filename);
            return `<div class="sound-item">
                <span class="sound-name">${display}</span>
                <div class="sound-actions">
                    <button class="btn btn-secondary btn-small" onclick="previewSound('${safe}')">&#9654; Preview</button>
                    <button class="btn btn-danger btn-small" onclick="deleteSound('${safe}')">Delete</button>
                </div>
            </div>`;
        }).join("");
    } catch (_) {
        el.innerHTML = "<p class=\"message error\">Failed to load sounds.</p>";
    }
}

async function uploadSound(event) {
    if (event && event.preventDefault) event.preventDefault();
    const input = document.getElementById("sound-upload");
    if (!input || !input.files.length) {
        showMessage("sounds-msg", "Select a file to upload.", "error");
        return;
    }

    const formData = new FormData();
    formData.append("file", input.files[0]);

    try {
        const resp = await fetch("/api/sounds/upload", { method: "POST", body: formData });
        if (resp.status === 401) { window.location.href = "/login"; return; }
        const result = await resp.json();
        showMessage("sounds-msg", result.message || (result.success ? "Uploaded." : "Upload failed."), result.success ? "success" : "error");
        if (result.success) { input.value = ""; loadSounds(); }
    } catch (_) {
        showMessage("sounds-msg", "Upload failed.", "error");
    }
}

async function deleteSound(encodedName) {
    const displayName = decodeURIComponent(encodedName);
    if (!confirm(`Delete sound "${displayName}"?`)) return;
    try {
        const resp = await fetch(`/api/sounds/${encodedName}`, { method: "DELETE" });
        const result = await resp.json();
        showMessage("sounds-msg", result.message || (result.success ? "Deleted." : "Delete failed."), result.success ? "success" : "error");
        if (result.success) loadSounds();
    } catch (_) {
        showMessage("sounds-msg", "Delete failed.", "error");
    }
}

function previewSound(encodedName) {
    const existing = document.getElementById("sound-preview-player");
    if (existing) existing.remove();
    const audio = document.createElement("audio");
    audio.id = "sound-preview-player";
    audio.src = `/api/sounds/preview/${encodedName}`;
    audio.autoplay = true;
    document.body.appendChild(audio);
}

// ----------------------------------------------------------------
// Branding
// ----------------------------------------------------------------

async function loadBranding() {
    try {
        const data = await apiGet("/api/branding");
        const nameInput = document.getElementById("team-name-input");
        if (nameInput && data.team_name != null) nameInput.value = data.team_name;

        const preview = document.getElementById("logo-preview");
        if (preview) {
            if (data.logo_url) {
                preview.src = data.logo_url;
                preview.style.display = "";
                const delBtn = document.getElementById("delete-logo-btn");
                if (delBtn) delBtn.style.display = "";
            } else {
                preview.style.display = "none";
                const delBtn = document.getElementById("delete-logo-btn");
                if (delBtn) delBtn.style.display = "none";
            }
        }
    } catch (_) {}
}

async function saveBranding(event) {
    if (event && event.preventDefault) event.preventDefault();

    const formData = new FormData();
    const nameInput = document.getElementById("team-name-input");
    if (nameInput) formData.append("team_name", nameInput.value);

    const fileInput = document.getElementById("logo-upload");
    if (fileInput && fileInput.files && fileInput.files.length > 0) {
        formData.append("logo", fileInput.files[0]);
    }

    try {
        const resp = await fetch("/api/branding", { method: "POST", body: formData });
        if (resp.status === 401) { window.location.href = "/login"; return; }
        const result = await resp.json();
        showMessage("branding-msg", result.message || (result.success ? "Saved." : "Save failed."), result.success ? "success" : "error");
        if (result.success) {
            if (fileInput) fileInput.value = "";
            loadBranding();
        }
    } catch (_) {
        showMessage("branding-msg", "Save failed.", "error");
    }
}

async function deleteLogo() {
    if (!confirm("Delete the logo?")) return;
    try {
        const resp = await fetch("/api/branding/logo", { method: "DELETE" });
        const result = await resp.json();
        showMessage("branding-msg", result.message || (result.success ? "Logo deleted." : "Delete failed."), result.success ? "success" : "error");
        if (result.success) loadBranding();
    } catch (_) {
        showMessage("branding-msg", "Delete failed.", "error");
    }
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    loadConfig();
    loadSounds();
    loadBranding();
    _bindVolumeSlider();
    _bindDeviceNameValidation();
    _bindBacklightToggle();

    const saveBtn = document.getElementById("save-config-btn");
    if (saveBtn) saveBtn.addEventListener("click", saveConfig);

    const resetBtn = document.getElementById("reset-config-btn");
    if (resetBtn) resetBtn.addEventListener("click", resetConfig);

    const discardBtn = document.getElementById("discard-config-btn");
    if (discardBtn) discardBtn.addEventListener("click", () => loadConfig());

    const soundUploadBtn = document.getElementById("sound-upload-btn");
    if (soundUploadBtn) soundUploadBtn.addEventListener("click", uploadSound);

    const saveBrandingBtn = document.getElementById("save-branding-btn");
    if (saveBrandingBtn) saveBrandingBtn.addEventListener("click", saveBranding);

    const deleteLogoBtn = document.getElementById("delete-logo-btn");
    if (deleteLogoBtn) deleteLogoBtn.addEventListener("click", deleteLogo);

    const logoUpload = document.getElementById("logo-upload");
    const logoFilename = document.getElementById("logo-filename");
    if (logoUpload && logoFilename) {
        logoUpload.addEventListener("change", () => {
            logoFilename.textContent = logoUpload.files.length ? logoUpload.files[0].name : "No file chosen";
        });
    }

    const soundUpload = document.getElementById("sound-upload");
    const soundFilenameEl = document.getElementById("sound-filename");
    if (soundUpload && soundFilenameEl) {
        soundUpload.addEventListener("change", () => {
            soundFilenameEl.textContent = soundUpload.files.length ? soundUpload.files[0].name : "No file chosen";
        });
    }
});
