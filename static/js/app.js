document.addEventListener("DOMContentLoaded", () => {
  // --- Generate CV form ---
  const generateForm = document.getElementById("generate-form");
  if (generateForm) {
    const btn = document.getElementById("generate-btn");
    const statusEl = document.getElementById("status");
    const warningEl = document.getElementById("fallback-warning");
    const downloadEl = document.getElementById("download-link");

    generateForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      // Revoke any previous blob URL to avoid memory leaks
      if (downloadEl.href && downloadEl.href.startsWith("blob:")) {
        URL.revokeObjectURL(downloadEl.href);
        downloadEl.href = "#";
      }
      btn.disabled = true;
      btn.textContent = "Generating...";
      statusEl.textContent = "Agent is working — this may take 15–30 seconds...";
      statusEl.classList.remove("hidden");
      warningEl.classList.add("hidden");
      downloadEl.classList.add("hidden");

      const formData = new FormData(generateForm);
      try {
        const resp = await fetch("/generate", { method: "POST", body: formData });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ error: resp.statusText }));
          statusEl.textContent = "Error: " + (err.error || resp.statusText);
          return;
        }
        if (resp.headers.get("X-Search-Fallback") === "true") {
          warningEl.classList.remove("hidden");
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        downloadEl.href = url;
        downloadEl.classList.remove("hidden");
        statusEl.textContent = "CV generated successfully.";
      } catch (err) {
        statusEl.textContent = "Network error: " + err.message;
      } finally {
        btn.disabled = false;
        btn.textContent = "Generate CV";
      }
    });
  }

  // --- Ingest text form ---
  const ingestTextForm = document.getElementById("ingest-text-form");
  if (ingestTextForm) {
    const statusEl = document.getElementById("ingest-text-status");
    ingestTextForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData();
      formData.set("text", document.getElementById("ingest-text").value);
      statusEl.textContent = "Processing...";
      statusEl.classList.remove("hidden");
      try {
        const resp = await fetch("/memory/ingest/text", { method: "POST", body: formData });
        const data = await resp.json();
        statusEl.textContent = resp.ok ? data.message : "Error: " + (data.error || JSON.stringify(data));
        if (resp.ok) refreshMemoryDisplay();
      } catch (err) {
        statusEl.textContent = "Error: " + err.message;
      }
    });
  }

  // --- Ingest file form ---
  const ingestFileForm = document.getElementById("ingest-file-form");
  if (ingestFileForm) {
    const statusEl = document.getElementById("ingest-file-status");
    ingestFileForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const file = document.getElementById("ingest-file").files[0];
      if (!file) { statusEl.textContent = "Please select a file."; statusEl.classList.remove("hidden"); return; }
      const formData = new FormData();
      formData.append("file", file);
      statusEl.textContent = "Uploading and processing...";
      statusEl.classList.remove("hidden");
      try {
        const resp = await fetch("/memory/ingest/file", { method: "POST", body: formData });
        const data = await resp.json();
        statusEl.textContent = resp.ok ? data.message : "Error: " + (data.error || JSON.stringify(data));
        if (resp.ok) refreshMemoryDisplay();
      } catch (err) {
        statusEl.textContent = "Error: " + err.message;
      }
    });
  }

  async function refreshMemoryDisplay() {
    const display = document.getElementById("memory-display");
    if (!display) return;
    try {
      const resp = await fetch("/memory/data");
      if (!resp.ok) return;
      const data = await resp.json();
      display.textContent = JSON.stringify(data, null, 2);
    } catch (_) {
      // silently ignore refresh errors — stale display is acceptable
    }
  }
});
