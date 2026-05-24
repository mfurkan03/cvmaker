document.addEventListener("DOMContentLoaded", () => {

  // Preferred display order for object fields inside cards
  const FIELD_ORDER = [
    "name", "description", "organization",
    "start_date", "end_date",
    "technologies", "github", "url", "highlights",
    "company", "title", "role", "position",
    "institution", "degree", "field",
    "university", "department", "faculty",
    "cgpa", "thesis",
    "startDate", "endDate", "start", "end",
  ];

  // Card templates for empty "Add" clicks
  const CARD_TEMPLATES = {
    education:      { institution: "", degree: "", field: "", start: "", end: "" },
    experience:     { company: "", title: "", start: "", end: "", highlights: [] },
    projects:       { name: "", description: "", technologies: [], url: "" },
    certifications: "",
    awards:         "",
  };

  function sortedEntries(obj) {
    return Object.entries(obj).sort(([a], [b]) => {
      const ai = FIELD_ORDER.indexOf(a);
      const bi = FIELD_ORDER.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
  }

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
          info.textContent = resp.status === 404 ? data.error : "Error: " + (data.error || resp.statusText);
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
    const btn         = document.getElementById("generate-btn");
    const statusEl    = document.getElementById("status");
    const warningEl   = document.getElementById("fallback-warning");
    const targetEl    = document.getElementById("target");
    const langEl      = document.getElementById("language");
    const modelEl     = document.getElementById("cv-model");

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
      btn.disabled = true;
      btn.textContent = "Generating…";
      warningEl.classList.add("hidden");

      statusEl.innerHTML =
        '<div id="pipeline-progress">' +
          '<span id="step-label">Starting…</span>' +
          '<div class="pipeline-bar-track">' +
            '<div id="pipeline-bar" class="pipeline-bar"></div>' +
          '</div>' +
        '</div>';
      statusEl.classList.remove("hidden");

      const formData = new FormData(generateForm);
      try {
        const resp = await fetch("/generate/pipeline", { method: "POST", body: formData });
        if (!resp.ok) {
          let data = {};
          try { data = await resp.json(); } catch {}
          statusEl.textContent = "Error: " + (data.error || resp.statusText);
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let doneReceived = false;

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              let msg;
              try { msg = JSON.parse(line.slice(6)); } catch { continue; }

              if (msg.type === "progress") {
                const pct = ((msg.step - 1) / msg.total) * 100;
                const bar = document.getElementById("pipeline-bar");
                const label = document.getElementById("step-label");
                if (bar) bar.style.width = pct + "%";
                if (label) label.textContent = "Step " + msg.step + " of " + msg.total + " — " + msg.label;

              } else if (msg.type === "done") {
                doneReceived = true;
                const bar = document.getElementById("pipeline-bar");
                if (bar) bar.style.width = "100%";
                await new Promise(r => setTimeout(r, 420));

                window.__CV_SECTIONS__ = msg.sections;
                window.__CV_LANGUAGE__ = langEl ? langEl.value : "English";
                if (msg.used_fallback) warningEl.classList.remove("hidden");
                showCvPreview(msg.html);
                statusEl.textContent = "CV generated. Click any text to edit, or use the refine panel below.";
                break;

              } else if (msg.type === "error") {
                doneReceived = true;
                statusEl.textContent = "Error: " + msg.error;
                break;
              }
            }
            if (doneReceived) break;
          }
        } finally {
          reader.cancel().catch(() => {});
        }

        if (!doneReceived) {
          statusEl.textContent = "Error: Stream ended unexpectedly. Please try again.";
        }
      } catch (err) {
        statusEl.textContent = "Network error: " + err.message;
      } finally {
        btn.disabled = false;
        btn.textContent = "Generate CV";
      }
    });

    // ── Preview helpers ──

    function showCvPreview(html) {
      const placeholder = document.getElementById("cv-preview-placeholder");
      const content     = document.getElementById("cv-preview-content");
      const htmlEl      = document.getElementById("cv-preview-html");
      const refinePanel = document.getElementById("refine-panel");

      if (placeholder) placeholder.classList.add("hidden");
      if (htmlEl) htmlEl.innerHTML = html;
      if (content) content.classList.remove("hidden");
      if (refinePanel) refinePanel.classList.remove("hidden");

      // Activate split layout (removes max-width constraint on <main>)
      document.querySelector("main")?.classList.add("cv-split-active");

      attachEditListeners();
    }

    function setNestedValue(obj, path, value) {
      const parts = path.split(".");
      let cur = obj;
      for (let i = 0; i < parts.length - 1; i++) {
        const key = isNaN(parts[i]) ? parts[i] : parseInt(parts[i], 10);
        if (cur[key] === undefined || cur[key] === null) return;
        cur = cur[key];
      }
      const last = parts[parts.length - 1];
      cur[isNaN(last) ? last : parseInt(last, 10)] = value;
    }

    function attachEditListeners() {
      const htmlEl = document.getElementById("cv-preview-html");
      if (!htmlEl) return;
      htmlEl.querySelectorAll("[data-cv-path]").forEach(el => {
        el.addEventListener("blur", () => {
          if (!window.__CV_SECTIONS__) return;
          const path = el.dataset.cvPath;
          const value = el.innerText.trim();
          setNestedValue(window.__CV_SECTIONS__, path, value);
        });
        // Prevent Enter from inserting <br>/<div> in single-line fields
        const multiLinePaths = ["summary", "research_interests"];
        const isMultiLine = multiLinePaths.some(p => el.dataset.cvPath === p) ||
                            el.dataset.cvPath?.includes(".bullets.");
        if (!isMultiLine) {
          el.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter") { ev.preventDefault(); el.blur(); }
          });
        }
      });
    }

    // ── Download ──
    const downloadBtn = document.getElementById("cv-download-btn");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", async () => {
        if (!window.__CV_SECTIONS__) return;
        downloadBtn.disabled = true;
        downloadBtn.textContent = "Generating PDF…";
        try {
          const resp = await fetch("/cv/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sections: window.__CV_SECTIONS__,
              language: window.__CV_LANGUAGE__ || "English",
            }),
          });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            alert("Download error: " + (err.error || resp.statusText));
            return;
          }
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "cv.pdf";
          a.click();
          URL.revokeObjectURL(url);
        } catch (err) {
          alert("Network error: " + err.message);
        } finally {
          downloadBtn.disabled = false;
          downloadBtn.textContent = "Download PDF";
        }
      });
    }

    // ── Refine form ──
    const refineForm = document.getElementById("refine-form");
    if (refineForm) {
      const refineBtn    = document.getElementById("refine-btn");
      const refineInput  = document.getElementById("refine-input");
      const refineStatus = document.getElementById("refine-status");

      refineForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const instruction = refineInput.value.trim();
        if (!instruction || !window.__CV_SECTIONS__) return;
        refineBtn.disabled = true;
        refineBtn.textContent = "Applying…";
        refineStatus.textContent = "Asking AI to refine…";
        refineStatus.classList.remove("hidden");

        try {
          const resp = await fetch("/cv/refine", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sections: window.__CV_SECTIONS__,
              instruction,
              language: window.__CV_LANGUAGE__ || "English",
              model: modelEl?.value || "",
            }),
          });
          const data = await resp.json();
          if (!resp.ok) {
            refineStatus.textContent = "Error: " + (data.error || resp.statusText);
            return;
          }
          window.__CV_SECTIONS__ = data.sections;
          showCvPreview(data.html);
          refineInput.value = "";
          refineStatus.textContent = "Done. Review the changes above.";
          setTimeout(() => refineStatus.classList.add("hidden"), 3000);
        } catch (err) {
          refineStatus.textContent = "Network error: " + err.message;
        } finally {
          refineBtn.disabled = false;
          refineBtn.textContent = "Apply";
        }
      });
    }
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
    editor.appendChild(buildCardListSection("Education",      "education",      data.education      || []));
    editor.appendChild(buildCardListSection("Experience",     "experience",     data.experience     || []));
    editor.appendChild(buildCardListSection("Projects",       "projects",       data.projects       || []));

    const skills = data.skills || {};
    editor.appendChild(buildFieldSection("Skills", [
      { key: "skills.technical", label: "Technical", value: (skills.technical || []).join(", ") },
      { key: "skills.soft",      label: "Soft",      value: (skills.soft      || []).join(", ") },
      { key: "skills.languages", label: "Languages", value: (skills.languages || []).join(", ") },
    ], "Comma-separated"));

    editor.appendChild(buildCardListSection("Certifications", "certifications", data.certifications || []));
    editor.appendChild(buildCardListSection("Awards",         "awards",         data.awards         || []));
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

  function isLongStr(s) {
    return String(s).includes('\n') || String(s).length > 100;
  }

  function buildStringListWidget(arr) {
    const wrap = document.createElement("div");
    wrap.className = "mem-string-list";
    wrap.dataset.widgetType = "string-list";

    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "mem-add-btn mem-add-list-item-btn";
    addBtn.textContent = "+ Add item";
    addBtn.addEventListener("click", () => addStringItem(""));
    wrap.appendChild(addBtn);

    function addStringItem(val) {
      const row = document.createElement("div");
      row.className = "mem-string-list-item";
      const inp = document.createElement("input");
      inp.type = "text";
      inp.className = "mem-string-list-input";
      inp.value = val;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "mem-remove-btn";
      rm.title = "Remove";
      rm.textContent = "×";
      rm.addEventListener("click", () => row.remove());
      row.appendChild(inp);
      row.appendChild(rm);
      wrap.insertBefore(row, addBtn);
    }

    arr.forEach(v => addStringItem(String(v ?? "")));
    return wrap;
  }

  function renderWidget(val) {
    if (val === null || val === undefined) val = "";

    if (Array.isArray(val)) {
      return buildStringListWidget(
        val.map(v => (typeof v === "object" && v !== null) ? JSON.stringify(v) : String(v ?? ""))
      );
    }

    if (typeof val === "object") {
      const wrap = document.createElement("div");
      wrap.className = "mem-sub-object";
      wrap.dataset.widgetType = "sub-object";
      Object.entries(val).forEach(([k, v]) => wrap.appendChild(buildFieldRow(k, v)));
      return wrap;
    }

    const s = String(val);
    if (isLongStr(s)) {
      const ta = document.createElement("textarea");
      ta.className = "mem-value-textarea";
      ta.dataset.widgetType = "textarea";
      ta.value = s;
      ta.rows = Math.min(Math.max(2, s.split('\n').length + 1), 8);
      return ta;
    }

    const inp = document.createElement("input");
    inp.type = "text";
    inp.className = "mem-value-input";
    inp.dataset.widgetType = "string";
    inp.value = s;
    return inp;
  }

  function buildFieldRow(key, val) {
    const row = document.createElement("div");
    row.className = "mem-field-row";
    row.dataset.fieldKey = key;
    const lbl = document.createElement("span");
    lbl.className = "mem-label";
    lbl.textContent = key;
    row.appendChild(lbl);
    row.appendChild(renderWidget(val));
    return row;
  }

  function buildCard(item, index, list) {
    const card = document.createElement("div");
    card.className = "mem-card";

    const header = document.createElement("div");
    header.className = "mem-card-header";

    const titleEl = document.createElement("span");
    titleEl.className = "mem-card-title";
    if (typeof item === "string" || typeof item === "number") {
      titleEl.textContent = String(item).slice(0, 60) || `Entry #${index + 1}`;
    } else {
      const tf = ["name", "company", "institution", "title", "position"].find(f => item[f]);
      titleEl.textContent = tf ? String(item[tf]).slice(0, 60) : `Entry #${index + 1}`;
    }

    const actions = document.createElement("div");
    actions.className = "mem-card-actions";

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "mem-order-btn";
    upBtn.title = "Move up";
    upBtn.textContent = "↑";
    upBtn.addEventListener("click", () => {
      const prev = card.previousElementSibling;
      if (prev && prev.classList.contains("mem-card")) list.insertBefore(card, prev);
    });

    const dnBtn = document.createElement("button");
    dnBtn.type = "button";
    dnBtn.className = "mem-order-btn";
    dnBtn.title = "Move down";
    dnBtn.textContent = "↓";
    dnBtn.addEventListener("click", () => {
      const next = card.nextElementSibling;
      if (next && next.classList.contains("mem-card")) list.insertBefore(next, card);
    });

    const rmBtn = document.createElement("button");
    rmBtn.type = "button";
    rmBtn.className = "mem-remove-btn";
    rmBtn.title = "Remove entry";
    rmBtn.textContent = "×";
    rmBtn.addEventListener("click", () => card.remove());

    actions.appendChild(upBtn);
    actions.appendChild(dnBtn);
    actions.appendChild(rmBtn);
    header.appendChild(titleEl);
    header.appendChild(actions);
    card.appendChild(header);

    const body = document.createElement("div");
    body.className = "mem-card-body";

    if (typeof item === "string" || typeof item === "number") {
      const ta = document.createElement("textarea");
      ta.className = "mem-card-string";
      ta.dataset.widgetType = "card-string";
      ta.value = String(item);
      ta.rows = 2;
      body.appendChild(ta);
    } else if (typeof item === "object" && item !== null) {
      sortedEntries(item).forEach(([key, val]) => body.appendChild(buildFieldRow(key, val)));
    }

    card.appendChild(body);
    return card;
  }

  function buildCardListSection(title, sectionKey, items) {
    const wrap = document.createElement("div");
    wrap.className = "mem-section";

    const h = document.createElement("div");
    h.className = "mem-section-title";
    h.textContent = title;
    wrap.appendChild(h);

    const list = document.createElement("div");
    list.className = "mem-card-list";
    list.dataset.cardListKey = sectionKey;

    items.forEach((item, i) => list.appendChild(buildCard(item, i, list)));
    wrap.appendChild(list);

    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "mem-add-btn";
    const singular = title.toLowerCase().replace(/s$/, "");
    addBtn.textContent = `+ Add ${singular}`;
    addBtn.addEventListener("click", () => {
      const template = CARD_TEMPLATES[sectionKey];
      let newItem;
      if (template !== undefined) {
        newItem = typeof template === "string" ? "" : JSON.parse(JSON.stringify(template));
      } else {
        const cards = list.querySelectorAll(".mem-card");
        if (cards.length > 0 && items.length > 0 && typeof items[0] === "object") {
          newItem = Object.fromEntries(
            Object.entries(items[0]).map(([k, v]) => [k, Array.isArray(v) ? [] : ""])
          );
        } else {
          newItem = {};
        }
      }
      list.appendChild(buildCard(newItem, list.querySelectorAll(".mem-card").length, list));
    });
    wrap.appendChild(addBtn);

    return wrap;
  }

  function readWidget(el) {
    if (!el) return "";
    const t = el.dataset.widgetType;
    if (t === "string") return el.value.trim();
    if (t === "textarea" || t === "card-string") return el.value.trim();
    if (t === "string-list") {
      return Array.from(el.querySelectorAll(".mem-string-list-input"))
        .map(i => i.value.trim())
        .filter(Boolean);
    }
    if (t === "sub-object") {
      const obj = {};
      el.querySelectorAll(":scope > .mem-field-row").forEach(row => {
        const key = row.dataset.fieldKey;
        const widget = row.querySelector(".mem-value-input, .mem-value-textarea, .mem-string-list, .mem-sub-object");
        if (key) obj[key] = readWidget(widget);
      });
      return obj;
    }
    return el.value ? el.value.trim() : "";
  }

  function readCard(cardEl) {
    const strEl = cardEl.querySelector(".mem-card-string");
    if (strEl) return strEl.value.trim();
    const obj = {};
    const body = cardEl.querySelector(".mem-card-body");
    if (!body) return obj;
    body.querySelectorAll(":scope > .mem-field-row").forEach(row => {
      const key = row.dataset.fieldKey;
      const widget = row.querySelector(".mem-value-input, .mem-value-textarea, .mem-string-list, .mem-sub-object");
      if (key && widget) obj[key] = readWidget(widget);
    });
    return obj;
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

    editor.querySelectorAll("[data-card-list-key]").forEach(list => {
      const key = list.dataset.cardListKey;
      if (!(key in mem)) return;
      mem[key] = Array.from(list.querySelectorAll(":scope > .mem-card"))
        .map(readCard)
        .filter(v => v !== null && v !== "" && !(typeof v === "object" && Object.keys(v).length === 0));
    });

    return mem;
  }

  // ── GitHub import ────────────────────────────────────────────────────────
  const githubForm = document.getElementById("github-import-form");
  if (githubForm) {
    const statusEl = document.getElementById("github-import-status");
    const importBtn = document.getElementById("github-import-btn");

    githubForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = document.getElementById("github-username").value.trim();
      if (!username) {
        statusEl.textContent = "Please enter a GitHub username.";
        statusEl.className = "status";
        statusEl.classList.remove("hidden");
        return;
      }
      const model = document.getElementById("github-model")?.value || "";
      const includeForks = document.getElementById("github-forks")?.checked || false;

      importBtn.disabled = true;
      importBtn.textContent = "Importing…";
      statusEl.textContent = "Fetching repo list from GitHub…";
      statusEl.className = "status";
      statusEl.classList.remove("hidden");

      try {
        const resp = await fetch("/memory/github-import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, model, include_forks: includeForks }),
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          statusEl.textContent = "Error: " + (err.error || resp.statusText);
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let addedCount = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop();

          for (const chunk of lines) {
            const line = chunk.replace(/^data: /, "").trim();
            if (!line) continue;
            let msg;
            try { msg = JSON.parse(line); } catch { continue; }

            if (msg.error) {
              statusEl.textContent = "Error: " + msg.error;
              return;
            }

            if (msg.projects) {
              // Final message — inject all projects
              const projectsList = document.querySelector("[data-card-list-key='projects']");
              if (projectsList && msg.projects.length) {
                msg.projects.forEach(proj => {
                  const idx = projectsList.querySelectorAll(".mem-card").length;
                  projectsList.appendChild(buildCard(proj, idx, projectsList));
                });
                addedCount = msg.projects.length;
              }
              statusEl.textContent = `Done — ${addedCount} repo(s) added to Projects below. Review and click Save.`;
            } else if (msg.total) {
              // Progress update
              statusEl.textContent = `Processing… ${msg.done}/${msg.total} — ${msg.repo}`;
            }
          }
        }
      } catch (err) {
        statusEl.textContent = "Network error: " + err.message;
      } finally {
        importBtn.disabled = false;
        importBtn.textContent = "Import repos";
      }
    });
  }

});
