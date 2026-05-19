document.addEventListener("DOMContentLoaded", () => {

  // ── Quota widget (shared across pages) ──
  document.querySelectorAll(".quota-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const selectId = btn.dataset.modelSelect;
      const targetId = btn.dataset.quotaTarget;
      const modelId = document.getElementById(selectId)?.value;
      const info = document.getElementById(targetId);
      if (!info || !modelId) return;
      btn.disabled = true;
      info.textContent = "Checking…";
      info.className = "quota-info";
      info.classList.remove("hidden");
      try {
        const resp = await fetch("/groq/quota", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: modelId }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
          info.textContent = "Error: " + (data.error || resp.statusText);
          info.classList.add("error");
        } else {
          const q = data.quota || {};
          const parts = [];
          if (q.remaining_requests != null && q.limit_requests != null)
            parts.push(`Requests: ${q.remaining_requests}/${q.limit_requests} (resets ${q.reset_requests || "?"})`);
          if (q.remaining_tokens != null && q.limit_tokens != null)
            parts.push(`Tokens: ${q.remaining_tokens}/${q.limit_tokens} (resets ${q.reset_tokens || "?"})`);
          info.textContent = parts.join("  ·  ") || "No quota info returned.";
        }
      } catch (err) {
        info.textContent = "Network error: " + err.message;
        info.classList.add("error");
      } finally {
        btn.disabled = false;
      }
    });
  });

  // ── Generate CV form ──
  const generateForm = document.getElementById("generate-form");
  if (generateForm) {
    const btn        = document.getElementById("generate-btn");
    const statusEl   = document.getElementById("status");
    const warningEl  = document.getElementById("fallback-warning");
    const downloadEl = document.getElementById("download-link");
    const targetEl   = document.getElementById("target");
    const langEl     = document.getElementById("language");
    const modelEl    = document.getElementById("cv-model");

    // Restore saved values
    if (targetEl && sessionStorage.getItem("cv_target"))
      targetEl.value = sessionStorage.getItem("cv_target");
    if (langEl && sessionStorage.getItem("cv_language"))
      langEl.value = sessionStorage.getItem("cv_language");
    if (modelEl && sessionStorage.getItem("cv_model"))
      modelEl.value = sessionStorage.getItem("cv_model");

    // Persist on change
    targetEl?.addEventListener("input",  () => sessionStorage.setItem("cv_target",   targetEl.value));
    langEl?.addEventListener("change",   () => sessionStorage.setItem("cv_language", langEl.value));
    modelEl?.addEventListener("change",  () => sessionStorage.setItem("cv_model",    modelEl.value));

    generateForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (downloadEl.href && downloadEl.href.startsWith("blob:")) {
        URL.revokeObjectURL(downloadEl.href);
        downloadEl.href = "#";
      }
      btn.disabled = true;
      btn.textContent = "Generating…";
      statusEl.textContent = "Agent is working — this may take 15–30 seconds…";
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
        if (resp.headers.get("X-Search-Fallback") === "true")
          warningEl.classList.remove("hidden");
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

  // ── Memory chat ──
  const chatForm = document.getElementById("chat-form");
  if (chatForm) {
    const HISTORY_KEY = "mem_chat_history";
    const MSGS_KEY    = "mem_chat_messages";

    let chatHistory = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || "[]");
    const savedMsgs = JSON.parse(sessionStorage.getItem(MSGS_KEY) || "[]");

    const chatLog    = document.getElementById("chat-log");
    const chatInput  = document.getElementById("chat-input");
    const chatBtn    = document.getElementById("chat-btn");
    const chatStatus = document.getElementById("chat-status");
    const undoBtn    = document.getElementById("undo-btn");
    const clearBtn   = document.getElementById("clear-chat-btn");
    const memModel   = document.getElementById("mem-model");

    // Persist model selection
    if (memModel && sessionStorage.getItem("mem_model"))
      memModel.value = sessionStorage.getItem("mem_model");
    memModel?.addEventListener("change", () =>
      sessionStorage.setItem("mem_model", memModel.value));

    // Restore previous messages from sessionStorage
    savedMsgs.forEach(({ role, text, extra }) => appendMsg(role, text, extra, false));

    function appendMsg(role, text, extra, save = true) {
      const div = document.createElement("div");
      div.className = role === "user"
        ? "chat-msg-user"
        : "chat-msg-agent" + (extra ? " " + extra : "");
      div.textContent = text;
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
      if (save) {
        const msgs = JSON.parse(sessionStorage.getItem(MSGS_KEY) || "[]");
        msgs.push({ role, text, extra: extra || null });
        sessionStorage.setItem(MSGS_KEY, JSON.stringify(msgs));
      }
    }

    chatForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = chatInput.value.trim();
      if (!text) return;
      appendMsg("user", text);
      chatInput.value = "";
      chatBtn.disabled = true;
      chatBtn.textContent = "Thinking…";
      chatStatus.classList.add("hidden");
      const model = memModel?.value || "";
      try {
        const resp = await fetch("/memory/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ history: chatHistory, text, model }),
        });
        const data = await resp.json();
        if (!resp.ok) {
          appendMsg("agent", "Error: " + (data.error || resp.statusText));
        } else {
          chatHistory = data.history;
          sessionStorage.setItem(HISTORY_KEY, JSON.stringify(chatHistory));
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
          await refreshMemoryDisplay();
        }
      } catch (err) {
        chatStatus.textContent = "Error: " + err.message;
        chatStatus.classList.remove("hidden");
      } finally {
        undoBtn.disabled = false;
      }
    });

    clearBtn.addEventListener("click", () => {
      chatHistory = [];
      sessionStorage.removeItem(HISTORY_KEY);
      sessionStorage.removeItem(MSGS_KEY);
      chatLog.innerHTML = "";
    });
  }

  // ── Ingest file form ──
  const ingestFileForm = document.getElementById("ingest-file-form");
  if (ingestFileForm) {
    const statusEl = document.getElementById("ingest-file-status");
    ingestFileForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const files = Array.from(document.getElementById("ingest-file").files);
      if (!files.length) {
        statusEl.textContent = "Please select a file.";
        statusEl.classList.remove("hidden");
        return;
      }
      statusEl.classList.remove("hidden");
      const model = document.getElementById("mem-model")?.value || "";
      const errors = [], reports = [];
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        statusEl.textContent = `Processing ${file.name} (${i + 1}/${files.length})…`;
        const formData = new FormData();
        formData.append("file", file);
        if (model) formData.append("model", model);
        try {
          const resp = await fetch("/memory/ingest/file", { method: "POST", body: formData });
          const data = await resp.json();
          if (!resp.ok) errors.push(`${file.name}: ${data.error || resp.statusText}`);
          else reports.push(`${file.name}: ${data.message}`);
        } catch (err) {
          errors.push(`${file.name}: ${err.message}`);
        }
      }
      await refreshMemoryDisplay();
      statusEl.textContent = [...reports, ...errors.map(e => "⚠ " + e)].join("\n");
    });
  }

  // ── Memory editor ──
  const memEditor = document.getElementById("memory-editor");
  if (memEditor) {
    renderMemoryEditor(window.__INITIAL_MEMORY__ || {});

    const saveBtn    = document.getElementById("mem-save-btn");
    const saveStatus = document.getElementById("mem-save-status");

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveStatus.classList.add("hidden");
      try {
        const resp = await fetch("/memory/update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(collectMemory()),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          saveStatus.textContent = "Error: " + (err.error || resp.statusText);
          saveStatus.className = "mem-save-status error";
        } else {
          saveStatus.textContent = "Saved.";
          saveStatus.className = "mem-save-status";
          setTimeout(() => saveStatus.classList.add("hidden"), 2000);
        }
        saveStatus.classList.remove("hidden");
      } catch (err) {
        saveStatus.textContent = "Network error: " + err.message;
        saveStatus.className = "mem-save-status error";
        saveStatus.classList.remove("hidden");
      } finally {
        saveBtn.disabled = false;
      }
    });
  }

  async function refreshMemoryDisplay() {
    const editor = document.getElementById("memory-editor");
    if (!editor) return;
    try {
      const resp = await fetch("/memory/data");
      if (!resp.ok) return;
      renderMemoryEditor(await resp.json());
    } catch (_) {}
  }

  function renderMemoryEditor(data) {
    const editor = document.getElementById("memory-editor");
    if (!editor) return;
    editor.innerHTML = "";

    const personal = data.personal || {};
    editor.appendChild(buildFieldSection("Personal", [
      "name", "title", "email", "phone", "location", "linkedin", "github",
    ].map(k => ({
      key: "personal." + k,
      label: k.charAt(0).toUpperCase() + k.slice(1),
      value: personal[k] || "",
    }))));

    editor.appendChild(buildTextareaSection("Summary", "summary", data.summary || ""));
    editor.appendChild(buildListSection("Education",      "education",      data.education      || []));
    editor.appendChild(buildListSection("Experience",     "experience",     data.experience     || []));
    editor.appendChild(buildListSection("Projects",       "projects",       data.projects       || []));

    const skills = data.skills || {};
    editor.appendChild(buildFieldSection("Skills", [
      { key: "skills.technical", label: "Technical", value: (skills.technical || []).join(", ") },
      { key: "skills.soft",      label: "Soft",      value: (skills.soft      || []).join(", ") },
      { key: "skills.languages", label: "Languages", value: (skills.languages || []).join(", ") },
    ], "Comma-separated"));

    editor.appendChild(buildListSection("Certifications", "certifications", data.certifications || []));
    editor.appendChild(buildListSection("Awards",         "awards",         data.awards         || []));
    editor.appendChild(buildTextareaSection("Notes",      "notes",          data.notes          || ""));
  }

  function buildFieldSection(title, fields, hint) {
    const wrap = document.createElement("div");
    wrap.className = "mem-section";
    const h = document.createElement("div");
    h.className = "mem-section-title";
    h.textContent = title + (hint ? " — " + hint : "");
    wrap.appendChild(h);
    const body = document.createElement("div");
    body.className = "mem-fields";
    fields.forEach(({ key, label, value }) => {
      const row = document.createElement("div");
      row.className = "mem-field";
      const lbl = document.createElement("span");
      lbl.className = "mem-label";
      lbl.textContent = label;
      const inp = document.createElement("input");
      inp.className = "mem-input";
      inp.type = "text";
      inp.dataset.key = key;
      inp.value = value;
      row.appendChild(lbl);
      row.appendChild(inp);
      body.appendChild(row);
    });
    wrap.appendChild(body);
    return wrap;
  }

  function buildTextareaSection(title, key, value) {
    const wrap = document.createElement("div");
    wrap.className = "mem-section";
    const h = document.createElement("div");
    h.className = "mem-section-title";
    h.textContent = title;
    wrap.appendChild(h);
    const body = document.createElement("div");
    body.className = "mem-fields";
    const ta = document.createElement("textarea");
    ta.className = "mem-textarea";
    ta.dataset.key = key;
    ta.value = value;
    body.appendChild(ta);
    wrap.appendChild(body);
    return wrap;
  }

  function buildListSection(title, key, items) {
    const wrap = document.createElement("div");
    wrap.className = "mem-section";
    const h = document.createElement("div");
    h.className = "mem-section-title";
    h.textContent = title;
    wrap.appendChild(h);

    const list = document.createElement("div");
    list.className = "mem-list";
    list.dataset.listKey = key;

    function addItem(val) {
      const item = document.createElement("div");
      item.className = "mem-list-item";
      const ta = document.createElement("textarea");
      ta.value = typeof val === "string" ? val : JSON.stringify(val, null, 2);
      ta.rows = typeof val === "object" && val !== null ? 4 : 2;
      const rmBtn = document.createElement("button");
      rmBtn.className = "mem-remove-btn";
      rmBtn.title = "Remove";
      rmBtn.textContent = "×";
      rmBtn.addEventListener("click", () => item.remove());
      item.appendChild(ta);
      item.appendChild(rmBtn);
      list.appendChild(item);
    }

    items.forEach(addItem);
    wrap.appendChild(list);

    const addBtn = document.createElement("button");
    addBtn.className = "mem-add-btn";
    addBtn.textContent = "+ Add entry";
    addBtn.addEventListener("click", () => addItem(""));
    wrap.appendChild(addBtn);
    return wrap;
  }

  function collectMemory() {
    const editor = document.getElementById("memory-editor");
    const mem = {
      personal: { name: "", title: "", email: "", phone: "", location: "", linkedin: "", github: "" },
      summary: "",
      education: [], experience: [], projects: [],
      skills: { technical: [], soft: [], languages: [] },
      certifications: [], awards: [],
      notes: "",
    };

    editor.querySelectorAll("input[data-key]").forEach(inp => {
      const parts = inp.dataset.key.split(".");
      if (parts.length === 2 && mem[parts[0]] !== undefined) {
        if (parts[0] === "skills") {
          mem[parts[0]][parts[1]] = inp.value.split(",").map(s => s.trim()).filter(Boolean);
        } else {
          mem[parts[0]][parts[1]] = inp.value.trim();
        }
      }
    });

    editor.querySelectorAll("textarea[data-key]").forEach(ta => {
      mem[ta.dataset.key] = ta.value.trim();
    });

    editor.querySelectorAll("[data-list-key]").forEach(list => {
      const key = list.dataset.listKey;
      if (!(key in mem)) return;
      mem[key] = Array.from(list.querySelectorAll(".mem-list-item textarea"))
        .map(ta => {
          const v = ta.value.trim();
          if (!v) return null;
          try { return JSON.parse(v); } catch (_) { return v; }
        })
        .filter(v => v !== null);
    });

    return mem;
  }

});
