/* Logs page */

let _logAllLines = [];

// ----------------------------------------------------------------
// File list
// ----------------------------------------------------------------

async function fetchLogList() {
    const select = document.getElementById("log-file-select");
    if (!select) return;

    try {
        const files = await apiGet("/api/logs");
        const prev = select.value;
        select.innerHTML = "<option value=\"\">Select a log file…</option>";

        files.forEach(f => {
            const size = f.size < 1024
                ? `${f.size} B`
                : f.size < 1048576
                    ? `${(f.size / 1024).toFixed(1)} KB`
                    : `${(f.size / 1048576).toFixed(1)} MB`;
            const date = new Date(f.modified * 1000).toLocaleString();
            const opt = document.createElement("option");
            opt.value = f.name;
            opt.textContent = `${f.name}  (${size}, ${date})`;
            select.appendChild(opt);
        });

        if (prev && [...select.options].some(o => o.value === prev)) {
            select.value = prev;
        } else if (files.length > 0) {
            select.value = files[0].name;
        }

        loadLogFile();
    } catch (_) {
        showMessage("log-status", "Failed to load log file list.", "error");
    }
}

// ----------------------------------------------------------------
// Load file content
// ----------------------------------------------------------------

async function loadLogFile() {
    const select = document.getElementById("log-file-select");
    const content = document.getElementById("log-content");
    if (!select || !content) return;

    const filename = select.value;
    const downloadBtn = document.getElementById("download-btn");
    if (!filename) {
        content.innerHTML = "<p class=\"dim\">Select a log file above.</p>";
        _setText("log-status", "");
        if (downloadBtn) downloadBtn.removeAttribute("href");
        return;
    }

    if (downloadBtn) {
        downloadBtn.href = `/api/logs/${encodeURIComponent(filename)}`;
        downloadBtn.setAttribute("download", filename);
    }

    content.innerHTML = "<p class=\"loading\">Loading…</p>";

    const linesInput = document.getElementById("log-lines");
    const linesParam = linesInput ? linesInput.value : "500";
    const url = linesParam === "0"
        ? `/api/logs/${encodeURIComponent(filename)}?lines=999999`
        : `/api/logs/${encodeURIComponent(filename)}?lines=${linesParam}`;

    try {
        const data = await apiGet(url);
        _logAllLines = data.lines || [];

        filterLines();

        const stats = document.getElementById("log-status");
        if (stats) {
            if (data.total_lines > _logAllLines.length) {
                stats.textContent = `Showing last ${_logAllLines.length} of ${data.total_lines} lines`;
            } else {
                stats.textContent = `${data.total_lines} lines total`;
            }
        }
    } catch (_) {
        content.innerHTML = "<p class=\"message error\">Failed to load log file.</p>";
    }
}

// ----------------------------------------------------------------
// Render
// ----------------------------------------------------------------

// Matches: "2026-04-20 17:04:26 [LEVEL] module: message"
// Level tokens: DEBUG | INFO | WARNING | WARN | ERROR | CRITICAL
const LOG_LINE_RE = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+\[?(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL)\]?\s+(.*)$/;

function _escape(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderLogLines(lines) {
    const content = document.getElementById("log-content");
    if (!content) return;

    if (lines.length === 0) {
        content.innerHTML = "<p class=\"dim\" style=\"padding:12px\">No lines match.</p>";
        return;
    }

    const searchInput = document.getElementById("log-search");
    const rawSearch = (searchInput ? searchInput.value : "").trim();
    let highlightRe = null;
    if (rawSearch) {
        try {
            highlightRe = new RegExp(`(${rawSearch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
        } catch (_) {}
    }

    function highlight(html) {
        return highlightRe ? html.replace(highlightRe, "<mark>$1</mark>") : html;
    }

    content.innerHTML = lines.map(line => {
        const m = line.match(LOG_LINE_RE);
        if (m) {
            const [, date, time, rawLevel, msg] = m;
            const level = rawLevel.toUpperCase();
            const levelClass = level === "WARN" ? "warning" : level.toLowerCase();
            return `<div class="log-row log-row-${levelClass}">`
                + `<span class="log-ts">${_escape(date)}\n${_escape(time)}</span>`
                + `<span class="log-level log-level-${levelClass}">${_escape(level)}</span>`
                + `<span class="log-msg">${highlight(_escape(msg))}</span>`
                + `</div>`;
        }
        // Fallback: unparseable line, single cell
        return `<div class="log-row"><span></span><span></span><span class="log-msg">${highlight(_escape(line))}</span></div>`;
    }).join("");

    content.scrollTop = content.scrollHeight;
}

// ----------------------------------------------------------------
// Client-side filter
// ----------------------------------------------------------------

function filterLines() {
    const levelSelect = document.getElementById("log-level-filter");
    const searchInput = document.getElementById("log-search");

    const level = levelSelect ? levelSelect.value : "";
    const search = (searchInput ? searchInput.value : "").trim().toLowerCase();

    let filtered = _logAllLines;

    if (level) {
        const levelUpper = level.toUpperCase();
        filtered = filtered.filter(l => l.toUpperCase().includes(`[${levelUpper}]`));
    }

    if (search) {
        filtered = filtered.filter(l => l.toLowerCase().includes(search));
    }

    renderLogLines(filtered);
}

// ----------------------------------------------------------------

function _setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    fetchLogList();

    const fileSelect = document.getElementById("log-file-select");
    if (fileSelect) fileSelect.addEventListener("change", loadLogFile);

    const linesInput = document.getElementById("log-lines");
    if (linesInput) linesInput.addEventListener("change", loadLogFile);

    const levelFilter = document.getElementById("log-level-filter");
    if (levelFilter) levelFilter.addEventListener("change", filterLines);

    const searchInput = document.getElementById("log-search");
    if (searchInput) searchInput.addEventListener("input", filterLines);

    const refreshBtn = document.getElementById("log-refresh-btn");
    if (refreshBtn) refreshBtn.addEventListener("click", (e) => { e.preventDefault(); loadLogFile(); });
});
