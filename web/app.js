/* Nashmi web UI - plain JavaScript, no build step. Talks to server.py (/api/...). */
(function () {
  "use strict";

  // ------------------------------------------------------------------ state
  var STORE_KEY = "nashmi.conversations.v1";
  var state = { convs: [], activeId: null, busy: false, status: null };

  function load() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
      if (saved && Array.isArray(saved.convs)) {
        state.convs = saved.convs;
        state.activeId = saved.activeId;
      }
    } catch (e) { /* private window or blocked storage: start fresh */ }
    state.convs.forEach(function (c) {  // an answer cut off by a page reload
      c.messages.forEach(function (m) { if (m.pending) { m.pending = false; if (!m.content) m.error = "انقطع الرد. اسأل كمان مرة."; } });
    });
    state.convs = state.convs.filter(function (c) { return c.messages.length; });
    newConversation();
  }

  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ convs: state.convs.slice(0, 30), activeId: state.activeId }));
    } catch (e) { /* ignore */ }
  }

  function uid() {
    return "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function active() {
    for (var i = 0; i < state.convs.length; i++) if (state.convs[i].id === state.activeId) return state.convs[i];
    return null;
  }

  function newConversation() {
    var conv = { id: uid(), title: "محادثة جديدة", messages: [], people: [], created: Date.now() };
    state.convs.unshift(conv);
    state.activeId = conv.id;
    save();
    return conv;
  }

  // ------------------------------------------------------------------ dom helpers
  var $ = function (id) { return document.getElementById(id); };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /** Small, safe markdown: escape first, then **bold**, lists, [1] citations, paragraphs. */
  function renderMarkdown(text) {
    var lines = escapeHtml(text || "").split(/\n/);
    var html = "", list = null;
    function inline(s) {
      return s
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\[(\d{1,2})\]/g, '<span class="cite">$1</span>');
    }
    function closeList() { if (list) { html += "</" + list + ">"; list = null; } }
    lines.forEach(function (raw) {
      var line = raw.trim();
      var h = line.match(/^#{1,4}\s+(.*)$/);
      if (h) { closeList(); html += "<p><strong>" + inline(h[1]) + "</strong></p>"; return; }
      var ul = line.match(/^[-•*]\s+(.*)$/);
      var ol = line.match(/^\d+[.)]\s+(.*)$/);
      if (ul || ol) {
        var kind = ul ? "ul" : "ol";
        if (list !== kind) { closeList(); html += "<" + kind + ">"; list = kind; }
        html += "<li>" + inline((ul || ol)[1]) + "</li>";
      } else if (!line) {
        closeList();
      } else {
        closeList();
        html += "<p>" + inline(line) + "</p>";
      }
    });
    closeList();
    return html;
  }

  var ICON_WARN = '<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 3 2.5 20h19L12 3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 10v4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17.3" r="1" fill="currentColor"/></svg>';
  var ICON_CHAT = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.8 8.8 0 0 1-3.5-.7L4 20l1.5-4A7.2 7.2 0 0 1 4 11.5 7.5 7.5 0 0 1 12 4a7.5 7.5 0 0 1 8 7.5Z" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7"/></svg>';

  // ------------------------------------------------------------------ rendering
  function renderSidebar() {
    var list = $("convList");
    list.innerHTML = "";
    var used = state.convs.filter(function (c) { return c.messages.length || c.id === state.activeId; });
    used.forEach(function (c) {
      var b = el("div", "history-item" + (c.id === state.activeId ? " active" : ""));
      b.setAttribute("role", "button");
      b.tabIndex = 0;
      b.innerHTML = ICON_CHAT;
      b.appendChild(el("span", null, c.title));
      var del = el("button", "delete-conv", "×");
      del.title = "حذف المحادثة";
      del.addEventListener("click", function (e) {
        e.stopPropagation();
        deleteConversation(c.id);
      });
      b.appendChild(del);
      b.addEventListener("click", function () { switchTo(c.id); });
      b.addEventListener("keydown", function (e) { if (e.key === "Enter") switchTo(c.id); });
      list.appendChild(b);
    });
    if (!used.length) list.appendChild(el("p", "empty-note", "ما في محادثات بعد"));
    renderMemory();
  }

  function renderMemory() {
    var conv = active();
    var people = (conv && conv.people) || [];
    $("memoryPanel").hidden = !people.length;
    var box = $("memoryList");
    box.innerHTML = "";
    people.slice(-8).reverse().forEach(function (p) {
      var b = el("button", "memory-person" + (p.focus ? " is-focus" : ""));
      b.title = "اسأل نشمي عن " + p.name;
      b.appendChild(el("span", "initial", (p.name || "؟").charAt(0)));
      var who = el("span", "who");
      who.appendChild(el("strong", null, p.name));
      who.appendChild(el("small", null, p.id));
      b.appendChild(who);
      b.addEventListener("click", function () { send("شو بتعرف عن صاحب الرقم الوطني " + p.id + "؟"); closeSidebar(); });
      box.appendChild(b);
    });
  }

  function renderConversation() {
    var conv = active();
    var has = conv && conv.messages.length;
    $("welcome").hidden = !!has;
    $("messages").hidden = !has;
    var box = $("messages");
    box.innerHTML = "";
    if (has) conv.messages.forEach(function (m) { box.appendChild(renderMessage(m)); });
    scrollToBottom(true);
  }

  function renderMessage(m) {
    if (m.role === "user") {
      var u = el("div", "message user-message", m.content);
      return u;
    }
    var row = el("div", "message-row");
    var img = el("img", "message-avatar");
    img.src = "nashami.jpeg";
    img.alt = "";
    row.appendChild(img);
    var body = el("div", "message-body");
    row.appendChild(body);
    fillAssistant(body, m);
    return row;
  }

  function fillAssistant(body, m) {
    body.innerHTML = "";
    if (m.warning) {
      var w = el("div", "warning-box");
      w.innerHTML = ICON_WARN + "<span>" + escapeHtml(m.warning) + "</span>";
      body.appendChild(w);
    }
    var bubble = el("div", "message assistant-message" + (m.error ? " is-error" : ""));
    if (m.error) {
      bubble.textContent = m.error;
    } else if (!m.content && m.pending) {
      bubble.innerHTML = '<span class="typing"><span class="dots"><i></i><i></i><i></i></span>' +
        escapeHtml(m.table ? "نشمي عم يجهزلك القائمة…" : "نشمي عم يدوّرلك…") + "</span>";
    } else {
      bubble.innerHTML = renderMarkdown(m.content);
      if (m.pending) {
        var last = bubble.lastElementChild || bubble;
        last.classList.add("cursor");
      }
    }
    body.appendChild(bubble);
    if (m.table && m.table.length) body.appendChild(renderTable(m));
    if (!m.pending && m.sources && m.sources.length) body.appendChild(renderSources(m));
  }

  function renderTable(m) {
    var rows = m.table;
    var cols = Object.keys(rows[0]);
    var idCol = cols.indexOf("الرقم الوطني") >= 0 ? "الرقم الوطني" : null;
    var card = el("div", "data-card");
    var head = el("div", "data-head");
    var title = el("div", "data-title", m.warning ? "الأشخاص بنفس الاسم" : (m.family ? "أفراد عيلة " + m.family : "النتائج"));
    var count = el("small", null, rows.length + " شخص");
    title.appendChild(count);
    head.appendChild(title);
    var filter = null;
    if (rows.length > 6) {
      filter = el("input", "data-filter");
      filter.placeholder = "فلترة بالاسم أو الرقم أو المحافظة…";
      head.appendChild(filter);
    }
    var exportBtn = el("button", "chip-button", "تنزيل CSV");
    exportBtn.addEventListener("click", function () { exportCsv(cols, rows, m.family || "nashmi"); });
    head.appendChild(exportBtn);
    card.appendChild(head);

    var scroll = el("div", "table-scroll");
    var table = el("table", "data-table");
    var thead = el("thead");
    var trh = el("tr");
    trh.appendChild(el("th", "row-num", "#"));
    cols.forEach(function (c) { trh.appendChild(el("th", null, c)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el("tbody");
    table.appendChild(tbody);
    scroll.appendChild(table);
    card.appendChild(scroll);

    function draw(q) {
      tbody.innerHTML = "";
      var shown = 0;
      rows.forEach(function (r, i) {
        var hay = cols.map(function (c) { return r[c]; }).join(" ");
        if (q && hay.indexOf(q) === -1) return;
        shown++;
        var tr = el("tr");
        tr.title = "اضغط لتسأل نشمي عن هالشخص";
        tr.appendChild(el("td", "row-num", String(i + 1)));
        cols.forEach(function (c) {
          var v = r[c] == null ? "" : String(r[c]);
          tr.appendChild(el("td", /^[\d\-\s]+$/.test(v) && v ? "num" : null, v));
        });
        tr.addEventListener("click", function () {
          var who = idCol ? "صاحب الرقم الوطني " + r[idCol] : r[cols[0]];
          send("شو بتعرف عن " + who + "؟");
        });
        tbody.appendChild(tr);
      });
      count.textContent = q ? shown + " من " + rows.length : rows.length + " شخص";
    }
    draw("");
    if (filter) filter.addEventListener("input", function () { draw(filter.value.trim()); });
    card.appendChild(el("div", "data-hint", "اضغط على أي سطر عشان تسأل نشمي عن هالشخص."));
    return card;
  }

  var SOURCE_NAMES = { citizens: "سجل المواطنين", events: "سجل الوقائع المدنية", offices: "مكاتب الأحوال المدنية",
    knowledge_base: "دليل الإجراءات" };

  /** "civil_status_dataset.xlsx › knowledge_base › 02_تجديد_البطاقة.md" -> "دليل الإجراءات · تجديد البطاقة" */
  function prettySource(s) {
    var parts = String(s).split(" › ");
    if (parts.length === 1) return s;
    var sheet = parts[1], doc = parts[2];
    var label = SOURCE_NAMES[sheet] || sheet;
    if (doc) label += " · " + doc.replace(/\.(md|txt)$/i, "").replace(/^\d+_/, "").replace(/_/g, " ");
    return label;
  }

  function renderSources(m) {
    var d = el("details", "sources");
    var label = "المصادر (" + m.sources.length + ")" + (m.seconds != null ? " · " + m.seconds + " ث" : "");
    d.appendChild(el("summary", null, label));
    var ol = el("ol");
    m.sources.forEach(function (s) { ol.appendChild(el("li", null, prettySource(s))); });
    d.appendChild(ol);
    return d;
  }

  function exportCsv(cols, rows, name) {
    var esc = function (v) { v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var csv = "﻿" + [cols.map(esc).join(",")].concat(rows.map(function (r) {
      return cols.map(function (c) { return esc(r[c]); }).join(",");
    })).join("\n");
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = name + ".csv";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }

  function scrollToBottom(force) {
    var c = $("conversation");
    var near = c.scrollHeight - c.scrollTop - c.clientHeight < 160;
    if (force || near) c.scrollTop = c.scrollHeight;
  }

  // ------------------------------------------------------------------ chat
  function send(text) {
    text = (text || "").trim();
    if (!text || state.busy) return;
    var conv = active() || newConversation();
    if (!conv.messages.length) conv.title = text.length > 34 ? text.slice(0, 34) + "…" : text;
    conv.messages.push({ role: "user", content: text });
    var reply = { role: "assistant", content: "", pending: true };
    conv.messages.push(reply);
    state.busy = true;
    updateComposer();
    renderSidebar();
    renderConversation();

    var input = $("input");
    input.value = "";
    autoGrow();

    stream(conv, text, reply).then(function () {
      reply.pending = false;
      state.busy = false;
      save();
      updateComposer();
      renderSidebar();
      var body = lastAssistantBody();
      if (body) fillAssistant(body, reply);
      scrollToBottom();
      $("input").focus();
    });
  }

  function lastAssistantBody() {
    var bodies = $("messages").querySelectorAll(".message-body");
    return bodies.length ? bodies[bodies.length - 1] : null;
  }

  function stream(conv, text, reply) {
    var redrawQueued = false;
    function redraw() {
      if (redrawQueued) return;
      redrawQueued = true;
      requestAnimationFrame(function () {
        redrawQueued = false;
        var body = lastAssistantBody();
        if (body) fillAssistant(body, reply);
        scrollToBottom();
      });
    }

    function handle(evt) {
      if (evt.type === "meta") {
        reply.sources = evt.sources || [];
        reply.table = evt.table || null;
        reply.warning = evt.warning || null;
        reply.family = evt.family || null;
        conv.people = evt.people || [];
        renderMemory();
      } else if (evt.type === "token") {
        reply.content += evt.text;
      } else if (evt.type === "done") {
        reply.seconds = evt.seconds;
      } else if (evt.type === "error") {
        reply.error = evt.message;
      }
      redraw();
    }

    return fetch("api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conv.id, message: text }),
    }).then(function (res) {
      if (!res.ok || !res.body) throw new Error("HTTP " + res.status);
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = "";
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) {
            if (buf.trim()) { try { handle(JSON.parse(buf)); } catch (e) { /* partial line */ } }
            return;
          }
          buf += decoder.decode(r.value, { stream: true });
          var lines = buf.split("\n");
          buf = lines.pop();
          lines.forEach(function (l) { if (l.trim()) { try { handle(JSON.parse(l)); } catch (e) { /* skip */ } } });
          return pump();
        });
      }
      return pump();
    }).catch(function () {
      reply.error = "نشمي مش قادر يوصل للخادم. تأكد إن server.py شغّال وجرب كمان مرة.";
      redraw();
    }).then(function () {
      if (!reply.content && !reply.error) reply.error = "ما وصل رد. جرب كمان مرة.";
    });
  }

  function switchTo(id) {
    if (state.busy) return;
    state.activeId = id;
    save();
    renderSidebar();
    renderConversation();
    closeSidebar();
  }

  function deleteConversation(id) {
    if (state.busy) return;
    state.convs = state.convs.filter(function (c) { return c.id !== id; });
    fetch("api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ conversation_id: id }) }).catch(function () {});
    if (state.activeId === id) {
      if (state.convs.length) state.activeId = state.convs[0].id;
      else newConversation();
    }
    save();
    renderSidebar();
    renderConversation();
  }

  // ------------------------------------------------------------------ composer
  function autoGrow() {
    var t = $("input");
    t.style.height = "42px";
    t.style.height = Math.min(t.scrollHeight, 140) + "px";
  }

  function updateComposer() {
    var empty = !$("input").value.trim();
    $("sendBtn").disabled = empty || state.busy;
  }

  // ------------------------------------------------------------------ status
  function pollStatus() {
    fetch("api/status").then(function (r) { return r.json(); }).then(function (s) {
      state.status = s;
      var dot = $("statusDot"), txt = $("statusText");
      dot.className = "status-dot";
      if (!s.index) {
        dot.classList.add("is-offline");
        txt.textContent = "ما في بيانات مفهرسة · شغّل: py rag.py ingest data_excel";
      } else if (s.model === "ready") {
        txt.textContent = s.fake ? "نشمي جاهز (وضع تجريبي بدون نموذج)" : "نشمي جاهز يخدمك الآن";
      } else if (s.model === "loading") {
        dot.classList.add("is-loading");
        txt.textContent = "نشمي عم يصحصح… تحميل النموذج أول مرة بياخد دقيقة";
      } else {
        dot.classList.add("is-offline");
        txt.textContent = "نشمي مش واصل لـ Ollama · شغّل ollama serve";
      }
      var info = $("indexInfo");
      if (s.index) {
        info.innerHTML = "";
        s.files.forEach(function (f) { info.appendChild(el("div", null, "📄 " + f.name)); });
        info.appendChild(el("div", null, s.records.toLocaleString("ar-JO") + " سجل · " + s.model_name));
      } else {
        info.textContent = "لا يوجد فهرس";
      }
      setTimeout(pollStatus, s.model === "ready" ? 30000 : 4000);
    }).catch(function () {
      $("statusDot").className = "status-dot is-offline";
      $("statusText").textContent = "الخادم مش شغّال · شغّل: py server.py";
      setTimeout(pollStatus, 5000);
    });
  }

  // ------------------------------------------------------------------ help
  var HELP = [
    ["الهوية", ["قديش رسوم تجديد الهوية؟", "ضاعت هويتي للمرة الثانية، قديش بدي أدفع؟", "شو الأوراق المطلوبة لهوية أول مرة؟"]],
    ["المواليد والوفيات", ["شو الأوراق المطلوبة لتسجيل مولود جديد؟", "قديش المهلة لتسجيل الوفاة؟"]],
    ["البحث عن شخص", ["شو بتعرف عن محمد أحمد علي العواملة؟", "سارة خالد محمد الخطيب", "شو الحالة الاجتماعية لصاحب الرقم 9040250165؟"]],
    ["العيلة", ["بدي أسماء كل أفراد عيلة العواملة", "دار الزعبي مين فيهم؟"]],
    ["متابعة السؤال (نشمي بتذكّر)", ["وشو أسماء أولاده؟", "التاني", "رجعني للعيلة اللي سألت عنها"]],
    ["الدوام والتواصل", ["شو ساعات الدوام يوم السبت؟", "قديش سعر القيد العائلي؟"]],
  ];

  function buildHelp() {
    var box = $("helpGroups");
    HELP.forEach(function (g) {
      box.appendChild(el("h4", null, g[0]));
      g[1].forEach(function (q) {
        var b = el("button", "help-q", q);
        b.addEventListener("click", function () { closeHelp(); send(q); });
        box.appendChild(b);
      });
    });
  }

  function openHelp() { $("helpModal").hidden = false; }
  function closeHelp() { $("helpModal").hidden = true; }

  // ------------------------------------------------------------------ sidebar (mobile)
  function openSidebar() { $("sidebar").classList.add("is-open"); $("backdrop").classList.add("is-visible"); }
  function closeSidebar() { $("sidebar").classList.remove("is-open"); $("backdrop").classList.remove("is-visible"); }

  // ------------------------------------------------------------------ wire up
  document.addEventListener("DOMContentLoaded", function () {
    load();
    buildHelp();
    renderSidebar();
    renderConversation();
    pollStatus();

    $("composer").addEventListener("submit", function (e) { e.preventDefault(); send($("input").value); });
    $("input").addEventListener("input", function () { autoGrow(); updateComposer(); });
    $("input").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send($("input").value); }
    });
    $("newChat").addEventListener("click", function () {
      if (state.busy) return;
      var cur = active();
      if (!cur || cur.messages.length) newConversation();
      renderSidebar();
      renderConversation();
      closeSidebar();
      $("input").focus();
    });
    document.querySelectorAll(".prompt-card").forEach(function (b) {
      b.addEventListener("click", function () { send(b.getAttribute("data-q")); });
    });
    $("menuBtn").addEventListener("click", openSidebar);
    $("backdrop").addEventListener("click", closeSidebar);
    $("helpBtn").addEventListener("click", openHelp);
    $("helpClose").addEventListener("click", closeHelp);
    $("helpModal").addEventListener("click", function (e) { if (e.target === $("helpModal")) closeHelp(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeHelp(); });
    $("input").focus();
  });
})();
