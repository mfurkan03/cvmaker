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

  // --- Memory chat ---
  const chatForm = document.getElementById("chat-form");
  if (chatForm) {
    let chatHistory = [];
    const chatLog = document.getElementById("chat-log");
    const chatInput = document.getElementById("chat-input");
    const chatBtn = document.getElementById("chat-btn");
    const chatStatus = document.getElementById("chat-status");
    const undoBtn = document.getElementById("undo-btn");
    const clearChatBtn = document.getElementById("clear-chat-btn");

    function appendMsg(role, text, extra) {
      const div = document.createElement("div");
      div.className = role === "user" ? "chat-msg-user" : "chat-msg-agent" + (extra ? " " + extra : "");
      div.textContent = text;
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    chatForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = chatInput.value.trim();
      if (!text) return;
      appendMsg("user", text);
      chatInput.value = "";
      chatBtn.disabled = true;
      chatBtn.textContent = "Thinking...";
      chatStatus.classList.add("hidden");
      try {
        const resp = await fetch("/memory/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ history: chatHistory, text }),
        });
        const data = await resp.json();
        if (!resp.ok) {
          appendMsg("agent", "Error: " + (data.error || resp.statusText));
        } else {
          chatHistory = data.history;
          appendMsg("agent", data.report);
          await refreshMemoryDisplay();
        }
      } catch (err) {
        appendMsg("agent", "Network error: " + err.message);
      } finally {
        chatBtn.disabled = false;
        chatBtn.textContent = "Send";
      }
    });

    undoBtn.addEventListener("click", async () => {
      undoBtn.disabled = true;
      try {
        const resp = await fetch("/memory/undo", { method: "POST" });
        const data = await resp.json();
        if (!resp.ok) {
          chatStatus.textContent = data.error || "Nothing to undo.";
          chatStatus.classList.remove("hidden");
        } else {
          appendMsg("agent", "↩ " + data.report, "undo");
          const display = document.getElementById("memory-display");
          if (display && data.memory_json) display.textContent = data.memory_json;
        }
      } catch (err) {
        chatStatus.textContent = "Error: " + err.message;
        chatStatus.classList.remove("hidden");
      } finally {
        undoBtn.disabled = false;
      }
    });

    clearChatBtn.addEventListener("click", () => {
      chatHistory = [];
      chatLog.innerHTML = "";
    });
  }

  // --- Ingest file form ---
  const ingestFileForm = document.getElementById("ingest-file-form");
  if (ingestFileForm) {
    const statusEl = document.getElementById("ingest-file-status");
    ingestFileForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const files = Array.from(document.getElementById("ingest-file").files);
      if (!files.length) { statusEl.textContent = "Please select a file."; statusEl.classList.remove("hidden"); return; }
      statusEl.classList.remove("hidden");
      const errors = [];
      const reports = [];
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        statusEl.textContent = `Processing ${file.name} (${i + 1}/${files.length})...`;
        const formData = new FormData();
        formData.append("file", file);
        try {
          const resp = await fetch("/memory/ingest/file", { method: "POST", body: formData });
          const data = await resp.json();
          if (!resp.ok) {
            errors.push(`${file.name}: ${data.error || resp.statusText}`);
          } else {
            reports.push(`${file.name}: ${data.message}`);
          }
        } catch (err) {
          errors.push(`${file.name}: ${err.message}`);
        }
      }
      await refreshMemoryDisplay();
      const lines = [...reports, ...errors.map(e => "⚠ " + e)];
      statusEl.textContent = lines.join("\n");
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
