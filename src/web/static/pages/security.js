/* Security page */

function _passwordIsSet() {
    // The template only renders #current-password / #remove-password-panel when a password is set.
    return document.getElementById("remove-password-panel") !== null;
}

// ----------------------------------------------------------------
// Set / change password
// ----------------------------------------------------------------

async function setPassword(event) {
    if (event && event.preventDefault) event.preventDefault();

    const currentPw = document.getElementById("current-password")?.value || "";
    const newPw = document.getElementById("new-password")?.value || "";
    const confirmPw = document.getElementById("confirm-password")?.value || "";

    if (!newPw) {
        showMessage("password-msg", "New password cannot be empty.", "error");
        return;
    }

    if (newPw !== confirmPw) {
        showMessage("password-msg", "Passwords do not match.", "error");
        return;
    }

    const payload = { new_password: newPw, confirm_password: confirmPw };
    if (_passwordIsSet()) payload.current_password = currentPw;

    try {
        const result = await apiPost("/api/security/password", payload);
        if (result.success) {
            showMessage("password-msg", result.message || "Password updated.", "success");
            setTimeout(() => window.location.reload(), 1200);
        } else {
            showMessage("password-msg", result.message || "Failed to set password.", "error");
        }
    } catch (_) {
        showMessage("password-msg", "Request failed.", "error");
    }
}

// ----------------------------------------------------------------
// Remove password
// ----------------------------------------------------------------

async function removePassword(event) {
    if (event && event.preventDefault) event.preventDefault();

    const currentPw = document.getElementById("remove-current-password")?.value || "";

    if (!currentPw) {
        showMessage("remove-msg", "Enter your current password to remove it.", "error");
        return;
    }

    if (!confirm("Remove the password? Anyone on the network will be able to access the device.")) return;

    try {
        const resp = await fetch("/api/security/password", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ current_password: currentPw }),
        });

        if (resp.status === 401) {
            window.location.href = "/login";
            return;
        }

        const result = await resp.json();

        if (result.success) {
            showMessage("remove-msg", result.message || "Password removed.", "success");
            setTimeout(() => window.location.reload(), 1200);
        } else {
            showMessage("remove-msg", result.message || "Failed to remove password.", "error");
        }
    } catch (_) {
        showMessage("remove-msg", "Request failed.", "error");
    }
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    const passwordForm = document.getElementById("password-form");
    if (passwordForm) passwordForm.addEventListener("submit", setPassword);

    const removeBtn = document.getElementById("remove-password-btn");
    if (removeBtn) removeBtn.addEventListener("click", removePassword);
});
