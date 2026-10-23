(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const feed = $("feed"), form = $("composer"), input = $("message"), sendBtn = $("send");
  const clusterSel = $("cluster"), statusEl = $("status"), historyEl = $("history");

  const SUGGESTIONS = [
    "What is a pod?",
    "Show pods in namespace shop",
    "Describe deployment api in shop",
    "Show logs for pod web-7d9f in namespace shop",
    "Delete pod web-7d9f in shop",
  ];
  let token = null, busy = false;

  // ---------- tiny DOM helpers (all text goes through textContent: no HTML injection) ----------
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function richText(container, text) {
    text.split(/(`[^`]+`)/g).forEach((part) => {
      if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
        container.appendChild(el("code", "inline-code", part.slice(1, -1)));
      } else if (part) {
        container.appendChild(document.createTextNode(part));
      }
    });
    return container;
  }
  function push(node) {
    feed.appendChild(node);
    feed.scrollTop = feed.scrollHeight;
    return node;
  }
  const bubble = (text, who = "bot") => push(richText(el("div", `bubble ${who}`), text));

  // ---------- API ----------
  async function ensureToken() {
    if (token) return token;
    let code = sessionStorage.getItem("ka_code") || "";
    for (let attempt = 0; attempt < 3; attempt++) {
      const res = await fetch("/api/token", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_code: code }),
      });
      if (res.ok) {
        token = (await res.json()).token;
        if (code) sessionStorage.setItem("ka_code", code);
        return token;
      }
      if (res.status !== 403) break;
      code = window.prompt("This server requires an access code:") || "";
    }
    throw new Error("Could not authenticate.");
  }
  async function api(path, body) {
    const t = await ensureToken();
    const res = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  }

  // ---------- rendering ----------
  const RISK_LABEL = { read: "read-only", write: "changes state", destructive: "destructive" };

  function proposalCard(p) {
    const card = el("div", "card");
    const head = el("div", "card-head");
    head.append(el("span", `badge ${p.risk}`, RISK_LABEL[p.risk] || p.risk),
                el("span", "grow", `cluster · ${p.cluster}`),
                el("span", "", p.source === "llm" ? "model" : p.source === "direct" ? "typed" : "rules"));
    card.append(head, el("pre", "cmd", p.command));

    const body = el("div", "card-body");
    if (p.explanation) body.append(el("p", "", p.explanation));
    const actions = el("div", "actions");
    const run = el("button", `btn ${p.risk === "destructive" ? "danger" : "primary"}`,
                   p.risk === "destructive" ? "Run (destructive)" : "Run");
    const cancel = el("button", "btn", "Cancel");
    const retry = el("button", "btn", "Suggest another");
    actions.append(run, cancel, retry);
    body.append(actions);
    card.append(body);

    const lock = () => actions.querySelectorAll("button").forEach((b) => (b.disabled = true));
    run.onclick = () => { lock(); decide("approve", card); };
    cancel.onclick = () => { lock(); decide("reject", card); };
    retry.onclick = async () => {
      lock();
      try { card.replaceWith(render(await api("/api/retry", {}))); }
      catch (e) { bubble(`Error: ${e.message}`); }
    };
    return card;
  }

  function resultCard(r) {
    const card = el("div", `card ${r.ok ? "ok" : "fail"}`);
    const head = el("div", "card-head");
    head.append(el("strong", "", r.ok ? "Completed" : "Failed"),
                el("span", "grow", `${r.command}  ·  ${r.cluster}`));
    card.append(head, el("pre", "output", r.output));
    return card;
  }

  function blockedCard(r) {
    const card = el("div", "card blocked");
    const body = el("div", "card-body");
    body.append(el("p", "", r.text));
    if (r.command) body.append(el("code", "inline-code", r.command));
    card.append(el("div", "card-head", "Not allowed"), body);
    return card;
  }

  function render(data) {
    switch (data.kind) {
      case "proposal": return proposalCard(data);
      case "result": loadHistory(); return resultCard(data);
      case "blocked": return blockedCard(data);
      default: return richText(el("div", "bubble bot"), data.text || "");
    }
  }

  async function decide(decision, card) {
    try {
      const data = await api("/api/approve", { decision });
      card.after(render(data));
      feed.scrollTop = feed.scrollHeight;
    } catch (e) { bubble(`Error: ${e.message}`); }
  }

  async function loadHistory() {
    try {
      const { items } = await api("/api/history");
      historyEl.replaceChildren();
      if (!items.length) { historyEl.append(el("li", "muted", "Nothing run yet.")); return; }
      items.forEach((it) => {
        const li = el("li", `${it.risk} ${it.ok ? "" : "failed"}`, it.command);
        li.append(el("small", "", `${it.cluster} · ${new Date(it.ts * 1000).toLocaleTimeString()}`));
        historyEl.append(li);
      });
    } catch (_) { /* sidebar history is best-effort */ }
  }

  // ---------- events ----------
  async function send(text) {
    if (busy || !text.trim()) return;
    busy = true; sendBtn.disabled = true;
    bubble(text, "user");
    input.value = "";
    const pending = push(el("div", "bubble bot thinking", "Thinking…"));
    try {
      const data = await api("/api/ask", { message: text, cluster: clusterSel.value });
      pending.remove();
      push(render(data));
    } catch (e) {
      pending.remove();
      bubble(`Error: ${e.message}`);
    } finally {
      busy = false; sendBtn.disabled = false; input.focus();
    }
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); send(input.value); });

  async function init() {
    const chips = $("suggestions");
    SUGGESTIONS.forEach((s) => {
      const b = el("button", "chip", s);
      b.type = "button";
      b.onclick = () => send(s);
      chips.append(b);
    });
    try {
      const cfg = await (await fetch("/api/config")).json();
      cfg.clusters.forEach((c) => {
        const o = el("option", "", c); o.value = c; clusterSel.append(o);
      });
      if (cfg.default_cluster) clusterSel.value = cfg.default_cluster;
      if (!cfg.clusters.length) clusterSel.append(el("option", "", "No clusters found"));
      statusEl.textContent = cfg.llm_online ? "Language model online" : "Language model offline — using built-in rules";
      statusEl.className = `status ${cfg.llm_online ? "online" : "offline"}`;
    } catch (_) { statusEl.textContent = "Cannot reach the server."; }
    bubble("Hi! Pick a cluster, then ask a Kubernetes question or describe what you'd like to do. "
         + "I'll always show the command and wait for your approval before running it.");
    loadHistory();
  }
  init();
})();
