/* USB Keys page */

let _permissiveDefuse = true;
let _permissiveTournament = true;

// ----------------------------------------------------------------
// Load registered keys + security badges
// ----------------------------------------------------------------

async function loadUsbKeys() {
    try {
        const data = await apiGet("/api/usb-keys");

        _permissiveDefuse = !!data.permissive_defuse;
        _permissiveTournament = !!data.permissive_tournament;

        _renderKeyList("defuse-keys-list", "defuse", data.defuse_keys || []);
        _renderKeyList("tournament-keys-list", "tournament", data.tournament_keys || []);

        _renderSecurityBadge(
            document.getElementById("defuse-security-badge"),
            data.permissive_defuse,
            (data.defuse_keys || []).length,
        );
        _renderSecurityBadge(
            document.getElementById("tournament-security-badge"),
            data.permissive_tournament,
            (data.tournament_keys || []).length,
        );
    } catch (_) {
        showMessage("usb-msg", "Failed to load USB keys.", "error");
    }
}

function _renderSecurityBadge(badgeEl, permissive, registeredCount) {
    if (!badgeEl) return;
    if (permissive) {
        badgeEl.textContent = "PERMISSIVE — any key file accepted";
        badgeEl.className = "chip chip-warning";
    } else {
        badgeEl.textContent = `LOCKED — ${registeredCount} registered`;
        badgeEl.className = "chip chip-success";
    }
}

function _renderKeyList(containerId, keyType, keys) {
    const el = document.getElementById(containerId);
    if (!el) return;

    if (keys.length === 0) {
        el.innerHTML = "<p class=\"dim\">No keys registered.</p>";
        return;
    }

    el.innerHTML = keys.map(k => {
        const label = String(k.label || k.id || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
        const keyId = String(k.id || "");
        const ts = k.created_at ? new Date(k.created_at * 1000).toLocaleDateString() : "—";
        return `<div class="key-item">
            <div class="key-info">
                <span class="key-label">${label}</span>
                <span class="key-meta">Created ${ts}</span>
            </div>
            <button class="btn btn-danger btn-small"
                onclick="revokeKey('${keyType}', '${keyId}', '${label}')">Revoke</button>
        </div>`;
    }).join("");
}

// ----------------------------------------------------------------
// USB sticks
// ----------------------------------------------------------------

async function refreshUsbSticks() {
    const listEl = document.getElementById("stick-list");
    const selectEl = document.getElementById("key-mount-point");

    try {
        const data = await apiGet("/api/usb-keys/usb-sticks");
        const sticks = data.sticks || [];

        if (selectEl) {
            selectEl.innerHTML = sticks.length === 0
                ? "<option value=\"\">No USB sticks detected</option>"
                : sticks.map(s => {
                    const mp = String(s.mount_point || "").replace(/"/g, "&quot;");
                    const name = String(s.display_name || s.mount_point || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
                    const size = s.size_total ? ` (${s.size_total})` : "";
                    return `<option value="${mp}">${name}${size}</option>`;
                }).join("");
        }

        if (listEl) {
            if (sticks.length === 0) {
                listEl.innerHTML = "<p class=\"dim\">No USB sticks detected.</p>";
            } else {
                listEl.innerHTML = sticks.map(s => {
                    const name = String(s.display_name || s.mount_point || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
                    const size = s.size_total ? `${s.size_total} total, ${s.size_free || "?"} free` : "—";
                    const defuseBadge = _statusBadge("Defuse", s.defuse_status, s.defuse_label, _permissiveDefuse);
                    const tourneyBadge = _statusBadge("Tournament", s.tournament_status, s.tournament_label, _permissiveTournament);
                    return `<div class="stick-item">
                        <div class="stick-info">
                            <span class="stick-name">${name}</span>
                            <span class="stick-size">${size}</span>
                        </div>
                        <div class="stick-badges">${defuseBadge}${tourneyBadge}</div>
                    </div>`;
                }).join("");
            }
        }
    } catch (_) {
        if (listEl) listEl.innerHTML = "<p class=\"message error\">Failed to detect USB sticks.</p>";
    }
}

function _statusBadge(kind, status, label, permissive) {
    if (!status || status === "none") {
        return permissive ? "" : `<span class="chip chip-danger">${kind}: UNKNOWN</span>`;
    }
    if (status === "registered") {
        const safeLabel = String(label || kind).replace(/&/g, "&amp;").replace(/</g, "&lt;");
        return `<span class="chip chip-success">${kind}: ${safeLabel}</span>`;
    }
    if (status === "permissive") {
        return `<span class="chip chip-warning">${kind}: PERMISSIVE</span>`;
    }
    if (status === "unrecognized") {
        return `<span class="chip chip-danger">${kind}: UNRECOGNIZED</span>`;
    }
    return `<span class="chip">${kind}: ${status}</span>`;
}

// ----------------------------------------------------------------
// Generate key
// ----------------------------------------------------------------

async function generateKey(event) {
    if (event && event.preventDefault) event.preventDefault();
    const keyType = document.getElementById("key-type")?.value || "defuse";
    const label = document.getElementById("key-label")?.value?.trim() || "";
    const mountPoint = document.getElementById("key-mount-point")?.value?.trim() || "";

    if (!mountPoint) { showMessage("usb-msg", "Select a USB stick.", "error"); return; }

    try {
        const result = await apiPost("/api/usb-keys/generate", {
            key_type: keyType,
            label,
            mount_point: mountPoint,
        });

        if (result.success && result.token) {
            _showTokenDialog(result.token);
            loadUsbKeys();
        } else {
            showMessage("usb-msg", result.message || "Failed to generate key.", "error");
        }
    } catch (_) {
        showMessage("usb-msg", "Failed to generate key.", "error");
    }
}

function _showTokenDialog(token) {
    const dialog = document.getElementById("token-dialog");
    const tokenDisplay = document.getElementById("token-display");
    if (!dialog) return;
    if (tokenDisplay) tokenDisplay.textContent = token;
    dialog.dataset.token = token;
    dialog.style.display = "";
}

function closeTokenDialog() {
    const dialog = document.getElementById("token-dialog");
    if (dialog) dialog.style.display = "none";
    loadUsbKeys();
}

// ----------------------------------------------------------------
// Revoke key
// ----------------------------------------------------------------

async function revokeKey(keyType, keyId, label) {
    if (!confirm(`Revoke key "${label}"? This cannot be undone.`)) return;
    try {
        const resp = await fetch(`/api/usb-keys/${encodeURIComponent(keyType)}/${encodeURIComponent(keyId)}`, {
            method: "DELETE",
        });
        const result = await resp.json();
        showMessage("usb-msg", result.message || (result.success ? "Key revoked." : "Revoke failed."), result.success ? "success" : "error");
        if (result.success) loadUsbKeys();
    } catch (_) {
        showMessage("usb-msg", "Revoke failed.", "error");
    }
}

// ----------------------------------------------------------------
// Copy token
// ----------------------------------------------------------------

async function copyToken() {
    const token = document.getElementById("token-dialog")?.dataset.token || "";
    try {
        await navigator.clipboard.writeText(token);
        const btn = document.getElementById("token-copy-btn");
        if (btn) {
            const orig = btn.textContent;
            btn.textContent = "Copied!";
            setTimeout(() => { btn.textContent = orig; }, 1500);
        }
    } catch (_) {
        showMessage("usb-msg", "Copy failed — please copy manually.", "error");
    }
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    loadUsbKeys();
    refreshUsbSticks();

    const generateBtn = document.getElementById("generate-key-btn");
    if (generateBtn) generateBtn.addEventListener("click", generateKey);

    const rescanBtn = document.getElementById("rescan-sticks-btn");
    if (rescanBtn) rescanBtn.addEventListener("click", refreshUsbSticks);

    const closeTokenBtn = document.getElementById("token-close-btn");
    if (closeTokenBtn) closeTokenBtn.addEventListener("click", closeTokenDialog);

    const copyTokenBtn = document.getElementById("token-copy-btn");
    if (copyTokenBtn) copyTokenBtn.addEventListener("click", copyToken);
});
