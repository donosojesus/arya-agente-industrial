/* ARYA - pantalla dividida. Todo lo que se muestra viene del agente (eventos reales);
   esta pagina no genera respuestas ni datos. Sin dependencias externas. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { online: false, busy: false, approver: "", draft: null, lastUse: 0, rows: {}, manualMode: false };
  const STATE_TEXT = { LISTENING: "ESCUCHANDO", IDLE: "LISTA", THINKING: "PENSANDO", USING_TOOL: "USANDO HERRAMIENTA", ANSWERING: "RESPONDIENDO", OFFLINE: "SIN CONEXIÓN" };

  // ------------------------------------------------------------ arranque: tokens por fragmento y planta
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  let controlToken = hash.get("control") || "";
  try { if (controlToken) sessionStorage.setItem("arya-control", controlToken); else controlToken = sessionStorage.getItem("arya-control") || ""; } catch (e) { /* sin almacenamiento */ }
  state.approver = hash.get("approver") || "";
  try {
    if (state.approver) sessionStorage.setItem("arya-approver", state.approver); else state.approver = sessionStorage.getItem("arya-approver") || "";
  } catch (e) { /* sin almacenamiento */ }
  if (window.location.hash) history.replaceState(null, "", window.location.pathname + window.location.search);  // conserva ?mode=... y ?poll=1
  $("approver-token").hidden = !!state.approver;

  fetch("/config.json", { cache: "no-store" }).then((r) => r.json()).catch(() => ({ plant_view_port: 8080 })).then((cfg) => {
    // El fragmento con el token de control nunca sale del navegador.
    $("plant").src = "http://" + window.location.hostname + ":" + cfg.plant_view_port + "/compact" + (controlToken ? "#token=" + encodeURIComponent(controlToken) : "");
  });

  // ------------------------------------------------------------ modos
  const loadedAt = Date.now();
  function setMode(mode, manual) {
    document.body.dataset.mode = mode;
    if (manual) state.manualMode = mode !== "idle";
    state.lastUse = Date.now();
  }
  // Cambio automatico a conversacion: solo desde reposo, para no sacar al presentador de "por dentro".
  function autoTalk() { if (document.body.dataset.mode === "idle") setMode("talk"); state.lastUse = Date.now(); }  // un aviso de ARYA saca la pantalla de REPOSO
  const initialMode = /[?&]mode=(idle|talk|inside)/.exec(window.location.search);
  if (initialMode) setMode(initialMode[1], true);
  // ?replay=1: al abrir, repite por dentro la ultima pregunta ya respondida (util para explicar).
  if (/[?&]replay=1/.test(window.location.search)) setTimeout(() => { if (window.AryaInside) window.AryaInside.replay(); }, 2500);
  document.querySelectorAll(".mode").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode, true)));
  setInterval(() => { // vuelve sola a reposo tras 4 minutos sin actividad, salvo que se haya fijado a mano
    if (document.body.dataset.mode === "talk" && !state.manualMode && !state.busy && Date.now() - state.lastUse > 240000 && !pendingDraft()) setMode("idle");
  }, 5000);
  function pendingDraft() { return state.draft && state.draft.status === "DRAFT_PENDING_APPROVAL"; }

  // ------------------------------------------------------------ utilidades
  function time(iso) { return new Date(iso).toLocaleTimeString("es-CL", { hour12: false }); }
  function node(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
  function notice(text) { const n = $("notice"); n.hidden = !text; n.textContent = text || ""; }
  function enable() {
    if (document.getElementById("talk") && typeof talkRender === "function") setTimeout(talkRender, 0);
    const ok = state.online && !state.busy;
    $("message").disabled = !ok; $("send").disabled = !ok;
    document.querySelectorAll("#suggest button").forEach((b) => { b.disabled = !ok; });
  }
  function bubble(cls, who, text, meta) {
    $("chat-empty").hidden = true;
    const m = node("div", "msg " + cls);
    if (who) m.appendChild(node("small", "", who));
    m.appendChild(node("div", "", text));
    if (meta) m.appendChild(meta);
    $("chat").appendChild(m);
    $("chat").scrollTop = $("chat").scrollHeight;
  }

  // ------------------------------------------------------------ grafico de evidencia (analisis predictivo)
  // Vibracion semanal de 6 meses (capa oro), referencias, limite, cono de proyeccion y paradas programadas.
  async function conditionCard() {
    const card = node("div", "cond-card");
    card.appendChild(node("div", "cond-title", "Evidencia · vibración P-101 en 6 meses (historial simulado, capa oro)"));
    const holder = node("div", "cond-chart", "Cargando…");
    card.appendChild(holder);
    $("chat").appendChild(card);
    try {
      const get = (u) => fetch(u, { cache: "no-store" }).then((r) => r.json());
      const [daily, proj, shut] = await Promise.all([
        get("/gateway/api/v1/assets/P-101/condition/daily?step=week&days=182"),
        get("/gateway/api/v1/assets/P-101/condition/projection?signal=vibration"),
        get("/cmms/api/v1/planned-shutdowns").catch(() => ({ shutdowns: [] }))]);
      holder.innerHTML = conditionSvg(daily.rows || [], proj, (shut.shutdowns || []).filter((s) => s.status === "PROGRAMADA"));
      const w = proj.weeks_to_limit;
      card.appendChild(node("div", "cond-note", proj.trend === "creciente"
        ? "Proyección hasta 4,5 mm/s: entre " + String(w.early).replace(".", ",") + " y " + String(w.late).replace(".", ",") + " semanas. No predice el momento de una falla."
        : "Sin tendencia relevante: no se proyecta un cruce del límite."));
    } catch (err) { holder.textContent = "No se pudo cargar el gráfico de evidencia."; }
    $("chat").scrollTop = $("chat").scrollHeight;
  }
  function conditionSvg(rows, proj, shutdowns) {
    const W = 640, H = 230, L = 38, R = 12, T = 14, B = 34;
    const day = (iso) => Date.parse(iso + "T12:00:00");
    const pts = rows.map((r) => ({ t: day(r.to), v: Number(r.vibration_p95) }));
    if (!pts.length) return "Sin datos.";
    const last = pts[pts.length - 1].t;
    const ends = [last + 14 * 864e5];
    if (proj.date_to_limit) ends.push(day(proj.date_to_limit.late) + 7 * 864e5);
    shutdowns.forEach((s) => ends.push(day(s.date) + 5 * 864e5));
    const t0 = pts[0].t, t1 = Math.max(...ends), vmax = 5;
    const x = (t) => L + (t - t0) / (t1 - t0) * (W - L - R), y = (v) => T + (1 - v / vmax) * (H - T - B);
    const hline = (v, cls, label, below) => `<line class="${cls}" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="lbl ${cls}" x="${L + 6}" y="${y(v) + (below ? 13 : -4)}">${label}</text>`;
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Vibración semanal de 6 meses con proyección">`;
    for (let v = 0; v <= vmax; v++) svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
    svg += hline(1.9, "ref", "referencia 1,9", true) + hline(2.38, "follow", "seguimiento +25 %") + hline(4.5, "limit", "límite 4,5 · zona C");
    if (proj.trend === "creciente" && proj.date_to_limit) {
      const x0 = x(last), y0 = y(Number(proj.current_fitted));
      svg += `<polygon class="cone" points="${x0},${y0} ${x(day(proj.date_to_limit.early))},${y(4.5)} ${x(day(proj.date_to_limit.late))},${y(4.5)}"/>`;
    }
    svg += `<polyline class="vib" points="${pts.map((p) => x(p.t) + "," + y(p.v)).join(" ")}"/>`;
    svg += `<line class="today" x1="${x(last)}" x2="${x(last)}" y1="${T}" y2="${H - B}"/><text class="axis" x="${x(last)}" y="${H - B + 26}" text-anchor="middle">hoy</text>`;
    shutdowns.forEach((s, i) => {
      const xs = x(day(s.date));
      const label = s.date.slice(8, 10) + "/" + s.date.slice(5, 7);
      const right = xs > W - R - 70;  // cerca del borde: la etiqueta va hacia adentro
      const ly = i % 2 === 0 ? H - B - 6 : y(4.5) + 14;  // alternadas abajo y bajo el limite para que no choquen
      svg += `<line class="stop" x1="${xs}" x2="${xs}" y1="${T}" y2="${H - B}"/><text class="lbl stop" x="${right ? xs - 3 : xs + 3}" y="${ly}" text-anchor="${right ? "end" : "start"}">parada ${label}</text>`;
    });
    const months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
    for (let d = new Date(t0); d.getTime() <= t1; d.setMonth(d.getMonth() + 1, 1)) {
      if (d.getTime() < t0) continue;
      svg += `<text class="axis" x="${x(d.getTime())}" y="${H - B + 14}" text-anchor="middle">${months[d.getMonth()]}</text>`;
    }
    return svg + `<text class="axis" x="4" y="${T + 4}">mm/s</text></svg>`;
  }

  // ------------------------------------------------------------ traza
  function traceRow(tr, cells, cls) {
    const body = $("trace");
    const empty = body.querySelector(".empty"); if (empty) empty.remove();
    if (!tr) { tr = node("tr", cls || ""); body.appendChild(tr); }
    tr.innerHTML = "";
    cells.forEach((c, i) => {
      const td = node("td", i === 1 ? "tool" : "");
      if (c && c.badge) td.appendChild(node("span", "badge " + c.badge, c.text)); else { td.textContent = c === null || c === undefined ? "" : String(c); td.title = td.textContent; }
      tr.appendChild(td);
    });
    while (body.children.length > 120) body.removeChild(body.firstChild);
    body.parentElement.scrollTop = body.parentElement.scrollHeight;
    return tr;
  }
  function argsText(a) {
    if (!a || !Object.keys(a).length) return "";
    return Object.keys(a).slice(0, 3).map((k) => k + "=" + (Array.isArray(a[k]) ? a[k].join(",") : String(a[k]).slice(0, 40))).join(" ");
  }

  // ------------------------------------------------------------ orden de trabajo
  function showDraft(order) {
    state.draft = order;
    const card = $("wo"); card.hidden = false; card.dataset.status = order.status;
    $("wo-id").textContent = order.id;
    $("wo-status").textContent = { DRAFT_PENDING_APPROVAL: "BORRADOR · PENDIENTE DE APROBACIÓN", OPEN: "APROBADA · ABIERTA", REJECTED: "RECHAZADA" }[order.status] || order.status;
    $("wo-asset").textContent = order.asset || "—";
    $("wo-problem").textContent = order.problem || "—";
    $("wo-cause").textContent = order.probable_cause || "—";
    $("wo-action").textContent = order.recommended_action || "—";
    $("wo-risk").textContent = { LOW: "Bajo", MEDIUM: "Medio", HIGH: "Alto" }[order.risk] || order.risk || "—";
    $("wo-evidence").textContent = (order.evidence || []).join(" · ") || "—";
    const pending = order.status === "DRAFT_PENDING_APPROVAL";
    $("wo-actions").hidden = !pending;
    if (!pending) {
      const who = order.approved_by || order.rejected_by;
      $("wo-msg").textContent = (order.status === "OPEN" ? "Aprobada" : "Rechazada") + (who ? " por " + who : " por una persona") +
        (order.draft_id ? " · borrador " + order.draft_id : "") + ". Decisión registrada en el CMMS.";
    } else { $("wo-msg").textContent = "Creada por ARYA como borrador. Solo una persona puede aprobarla."; }
  }
  async function decide(action) {
    const draft = state.draft; if (!draft) return;
    const name = $("approver").value.trim();
    const token = state.approver || $("approver-token").value.trim();
    if (name.length < 2) { $("wo-msg").textContent = "Escriba el nombre de quien decide."; $("approver").focus(); return; }
    if (!token) { $("approver-token").hidden = false; $("wo-msg").textContent = "Falta el token de aprobación (CMMS_APPROVER_TOKEN de .env)."; return; }
    $("approve").disabled = $("reject").disabled = true;
    try {
      const r = await fetch("/cmms/api/v1/work-orders/" + encodeURIComponent(draft.id) + "/" + action, {
        method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ approver: name }),
      });
      const body = await r.json().catch(() => ({}));
      if (r.status === 401) { $("approver-token").hidden = false; $("wo-msg").textContent = "Token de aprobación rechazado por el CMMS."; return; }
      if (!r.ok) { $("wo-msg").textContent = "El CMMS no aceptó la decisión (HTTP " + r.status + ")."; return; }
      showDraft(body);
      // El agente verifica la decision en el CMMS antes de guardarla en su memoria.
      await fetch("/agent/api/v1/work-orders/" + encodeURIComponent(draft.id) + "/sync", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ work_order_id: body.id }),
      }).catch(() => {});
    } catch (e) { $("wo-msg").textContent = "No se pudo contactar el CMMS."; }
    finally { $("approve").disabled = $("reject").disabled = false; }
  }
  $("approve").addEventListener("click", () => decide("approve"));
  $("reject").addEventListener("click", () => decide("reject"));

  // ------------------------------------------------------------ controles de la simulacion (a la vista)
  const SB_TEXT = { NORMAL: "Operación normal", DEGRADATION: "Falla en curso", RECOVERY: "Recuperándose: los valores vuelven gradualmente" };
  const SB_SCEN = { alpha: "escenario A", bravo: "escenario B", charlie: "escenario C · desgaste incipiente" };
  function sbRender(s) {
    const st = $("sb-state"); st.dataset.mode = s ? s.mode : "";
    if (!s) return;
    // Preguntas sugeridas: con el historial del escenario C (aun despues de VOLVER A NORMAL) se muestran las predictivas.
    document.body.dataset.qset = s.history_profile === "H2" ? "pred" : "std";
    let text = SB_TEXT[s.mode] || s.mode;
    if (s.mode === "DEGRADATION" && s.scenario === "charlie") text = "Escenario C · sin alarmas · historial de 6 meses con desgaste incipiente";
    else if (s.mode === "DEGRADATION") text += " · " + (SB_SCEN[s.scenario] || "") + " · " + Math.round(s.fault_progress * 100) + " %";
    if (s.scheduled_fault) text += " · falla programada en " + Math.ceil(s.scheduled_fault.starts_in_s / 60) + " min";
    st.textContent = text;
    $("sb-fault").disabled = s.mode !== "NORMAL";
    $("sb-normal").disabled = s.mode !== "DEGRADATION";
  }
  async function sbCall(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    if (controlToken) headers.Authorization = "Bearer " + controlToken;  // si no, lo agrega el servidor de la pantalla
    const r = await fetch("/control/api/demo/" + path, { method: method, headers: headers, body: body ? JSON.stringify(body) : undefined });
    return { status: r.status, body: await r.json().catch(() => null) };
  }
  async function sbPoll() {
    try {
      const r = await sbCall("GET", "state");
      if (r.status === 200) sbRender(r.body);
      else { $("sb-state").textContent = r.status === 401 ? "Controles no habilitados: abra con ./arya.sh open" : "Control de la planta sin respuesta"; $("sb-fault").disabled = $("sb-normal").disabled = true; }
    } catch (e) { $("sb-state").textContent = "Control de la planta sin respuesta"; $("sb-fault").disabled = $("sb-normal").disabled = true; }
  }
  $("sb-fault").addEventListener("click", async () => {
    $("sb-fault").disabled = true;
    const r = await sbCall("POST", "inject-fault", { scenario: $("sb-scenario").value }).catch(() => null);
    if (r && r.status === 200) sbRender(r.body); else $("sb-state").textContent = r && r.status === 409 ? "La planta aún no está en operación normal" : "No se pudo simular la falla";
  });
  $("sb-normal").addEventListener("click", async () => {
    $("sb-normal").disabled = true;
    const r = await sbCall("POST", "normal", {}).catch(() => null);
    if (r && r.status === 200) sbRender(r.body); else $("sb-state").textContent = "No se pudo volver a operación normal";
  });
  sbPoll(); setInterval(sbPoll, 2000);

  // ------------------------------------------------------------ limpiar
  // La limpieza la hace el agente (borra su contexto de corto plazo) y avisa con un evento;
  // la pantalla se vacia al recibirlo, tambien si se recarga la pagina despues.
  function clearScreen() {
    const chat = $("chat");
    Array.from(chat.querySelectorAll(".msg")).forEach((m) => m.remove());
    $("chat-empty").hidden = false;
    const body = $("trace"); body.innerHTML = "";
    const tr = node("tr", "empty"); const td = node("td", "", "Sin eventos"); td.colSpan = 6; tr.appendChild(td); body.appendChild(tr);
    state.rows = {};
    if (!pendingDraft()) { $("wo").hidden = true; state.draft = null; }  // una orden que espera decision sigue a la vista
  }
  $("clear").addEventListener("click", async () => {
    $("clear").disabled = true;
    try {
      const r = await fetch("/agent/api/v1/conversation/clear", { method: "POST" });
      if (r.status === 409) bubble("system", null, "ARYA está respondiendo; se podrá limpiar cuando termine.");
      else if (!r.ok) bubble("system", null, "No se pudo limpiar la conversación (HTTP " + r.status + ").");
    } catch (e) { bubble("system", null, "No se pudo contactar al agente para limpiar."); }
    finally { $("clear").disabled = false; }
  });

  // ------------------------------------------------------------ eventos del agente
  function onEvent(e) {
    switch (e.type) {
      case "user_message": bubble("user", "USTED · " + time(e.time), e.text); autoTalk(); traceRow(null, [time(e.time), "pregunta", e.text, "operador", "", ""]); break;
      case "system_trigger": bubble("system", null, "Aviso automático: se activó una alarma y ARYA la está revisando por su cuenta."); autoTalk();
        traceRow(null, [time(e.time), "disparo automático", "alarma detectada", "vigilancia", "", ""]); break;
      case "state": {
        state.busy = e.state !== "IDLE"; const c = $("state"); c.dataset.state = e.state;
        c.textContent = (STATE_TEXT[e.state] || e.state) + (e.state === "USING_TOOL" && e.tool ? " · " + e.tool : ""); enable(); break;
      }
      case "llm_call": traceRow(null, [time(e.time), "modelo · paso " + e.step, (e.requested_tools && e.requested_tools.length ? "pide: " + e.requested_tools.join(", ") : "redacta la respuesta") +
        (e.completion_tokens ? " · " + (e.prompt_tokens || "?") + "→" + e.completion_tokens + " tokens" : ""), e.model || "modelo", e.latency_ms, { badge: "ok", text: "OK" }], "llm"); break;
      case "llm_error": traceRow(null, [time(e.time), "modelo", e.message, "—", "", { badge: "err", text: "ERROR" }], "llm"); break;
      case "tool_start": {
        const key = e.turn_id + ":" + e.tool;  // filas abiertas, en orden, por si la misma herramienta se usa dos veces
        (state.rows[key] = state.rows[key] || []).push(traceRow(null, [time(e.time), e.tool, argsText(e.arguments), "…", "", { badge: "run", text: "…" }]));
        break;
      }
      case "tool_end": {
        const open = state.rows[e.turn_id + ":" + e.tool] || [];
        traceRow(open.shift() || null, [time(e.time), e.tool, e.summary, e.source, e.duration_ms, { badge: e.ok ? "ok" : "err", text: e.ok ? "OK" : "ERROR" }]);
        break;
      }
      case "assistant_message": {
        const meta = node("div", "meta");
        if (e.sources && e.sources.length) { meta.appendChild(node("b", "", "Fuentes: ")); meta.appendChild(document.createTextNode(e.sources.join(" · ") + "  ")); }
        if (typeof e.total_ms === "number") meta.appendChild(document.createTextNode("· " + (e.total_ms / 1000).toFixed(1) + " s (modelo " + (e.llm_ms / 1000).toFixed(1) + " s, herramientas " + (e.tools_ms / 1000).toFixed(1) + " s)"));
        if (e.prompt_tokens || e.completion_tokens) meta.appendChild(document.createTextNode(" · " + ((e.prompt_tokens || 0) + (e.completion_tokens || 0)).toLocaleString("es-CL") + " tokens"));
        if (e.ttft_ms != null) meta.appendChild(document.createTextNode(" · TTFT " + e.ttft_ms.toLocaleString("es-CL") + " ms" + (e.tpot_ms != null ? " · TPOT " + e.tpot_ms.toFixed(1).replace(".", ",") + " ms/token" : "")));
        bubble("arya" + (e.origin === "proactive" ? " proactive" : "") + (e.status !== "ok" ? " failed" : ""), "ARYA · " + time(e.time), e.text, meta);
        if ((e.sources || []).some((src) => /capa oro/.test(src))) conditionCard();
        autoTalk();
        // Solo se lee en voz alta lo que ocurre ahora, no el historial al abrir la pagina.
        if (window.AryaVoice && Date.parse(e.time) > loadedAt - 3000) {
          window.AryaVoice.say(e.text, () => { $("state").dataset.state = "ANSWERING"; $("state").textContent = "HABLANDO"; },
            () => { if ($("state").textContent === "HABLANDO") { $("state").dataset.state = "IDLE"; $("state").textContent = STATE_TEXT.IDLE; } });
        }
        break;
      }
      case "work_order_draft": showDraft(e.work_order); autoTalk(); break;
      case "human_decision": {
        traceRow(null, [time(e.time), "decisión humana", e.work_order_id + " · " + e.status + (e.decided_by ? " · " + e.decided_by : ""), "CMMS", "", { badge: "ok", text: "OK" }]);
        if (state.draft && (state.draft.id === e.draft_id || state.draft.draft_id === e.draft_id) && state.draft.status === "DRAFT_PENDING_APPROVAL") {
          fetch("/cmms/api/v1/work-orders/" + encodeURIComponent(e.work_order_id)).then((r) => (r.ok ? r.json() : null)).then((o) => { if (o) showDraft(o); }).catch(() => {});
        }
        break;
      }
      case "system": traceRow(null, [time(e.time), "sistema", e.message, "agente", "", ""]); break;
      case "conversation_cleared": clearScreen(); break;
      case "guardrail": traceRow(null, [time(e.time), "guardrail", e.message, "envoltorio", "", { badge: e.rule === "grounding_warning" ? "err" : "ok", text: e.rule === "grounding_warning" ? "AVISO" : "OK" }]); break;
    }
  }

  // Eventos en vivo por EventSource. Si no esta disponible o falla repetidamente (o con ?poll=1),
  // se recurre a consultar la traza cada segundo: mismos eventos, misma pantalla.
  let source = null, lastSeq = 0, failures = 0, polling = false;
  function deliver(e) {
    if (e.seq <= lastSeq) return;
    lastSeq = e.seq; onEvent(e);
    // El tablero "por dentro" solo anima lo ocurrido desde que se abrio la pagina; el historial solo actualiza textos.
    if (window.AryaInside) window.AryaInside.onEvent(e, Date.parse(e.time) > loadedAt - 3000);
  }
  function startPolling() {
    if (polling) return; polling = true;
    if (source) { source.close(); source = null; }
    const tick = async () => {
      try {
        const r = await fetch("/agent/api/v1/trace?since=" + lastSeq, { cache: "no-store" });
        if (r.ok) (await r.json()).events.forEach(deliver);
      } catch (err) { /* se reintenta */ }
      setTimeout(tick, 1000);
    };
    tick();
  }
  function connect() {
    if (!window.EventSource || /[?&]poll=1/.test(window.location.search)) { startPolling(); return; }
    source = new EventSource("/agent/api/v1/feed");
    source.onmessage = (m) => { failures = 0; try { deliver(JSON.parse(m.data)); } catch (err) { /* evento ilegible: se ignora */ } };
    source.onerror = () => { failures += 1; if (failures >= 5) startPolling(); };
  }
  connect();

  // ------------------------------------------------------------ estado del agente
  async function pollStatus() {
    try {
      const r = await fetch("/agent/api/v1/status", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const s = await r.json();
      state.online = true;
      $("node-label").textContent = s.node;
      const llm = $("llm"); llm.dataset.ok = String(!!s.llm.reachable);
      llm.textContent = s.llm.reachable ? "Nemotron · en línea" : (s.llm.configured ? "Nemotron · sin respuesta" : "Nemotron · no configurado");
      llm.title = s.llm.model || s.llm.detail || "";
      const links = $("links"); const ok = s.ot_gateway_reachable && s.cmms_reachable; links.dataset.ok = String(ok);
      links.textContent = ok ? "Enlace planta · OK" : "Enlace planta · " + (!s.ot_gateway_reachable ? "sin gateway" : "sin CMMS");
      $("proactive").checked = !!s.proactive.enabled;
      if (window.AryaInside) window.AryaInside.setStatus(s);
      if ($("state").dataset.state === "OFFLINE") { $("state").dataset.state = s.state; $("state").textContent = STATE_TEXT[s.state] || s.state; }
      notice(s.llm.reachable ? "" : "ARYA no tiene acceso al modelo de lenguaje (" + (s.llm.configured ? "Nemotron no responde" : "Nemotron aún no está configurado") + "). La planta sigue operando; las preguntas recibirán ese aviso.");
    } catch (e) {
      state.online = false; state.busy = false;
      $("state").dataset.state = "OFFLINE"; $("state").textContent = STATE_TEXT.OFFLINE;
      $("llm").dataset.ok = "false"; $("links").dataset.ok = "false";
      notice("Sin conexión con el agente ARYA. La planta sigue operando con su sistema de control.");
    }
    enable();
  }
  pollStatus(); setInterval(pollStatus, 3000);

  $("proactive").addEventListener("change", (ev) => {
    fetch("/agent/api/v1/proactive", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: ev.target.checked }) }).catch(() => {});
  });

  // ------------------------------------------------------------ preguntas
  async function ask(text) {
    text = text.trim(); if (!text || state.busy || !state.online) return;
    state.busy = true; enable(); autoTalk();
    try {
      const r = await fetch("/agent/api/v1/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text }) });
      if (r.status === 409) bubble("system", null, "ARYA está respondiendo otra consulta. Intente en unos segundos.");
      else if (!r.ok) bubble("system", null, "No se pudo enviar la pregunta al agente (HTTP " + r.status + ").");
    } catch (e) { bubble("system", null, "No se pudo contactar al agente."); }
    finally { state.busy = false; enable(); }
  }
  // ------------------------------------------------------------ voz de entrada (reconocedor local de Windows)
  // Servicio local en http://localhost:8095 (scripts/voice-listener.ps1), sin Internet. Si el texto
  // coincide con una frase del guion con buena confianza se envia solo; si no, queda en la caja para revisarlo.
  const VOICE_URL = "http://localhost:8095";
  let voiceReady = false, listening = false;
  function talkRender() {
    const b = $("talk");
    b.disabled = !voiceReady || listening || state.busy || !state.online;
    b.dataset.listening = String(listening);
    b.textContent = listening ? "ESCUCHANDO…" : (voiceReady ? "HABLAR" : "SIN MICRÓFONO");
  }
  async function voiceHealth() {
    try {
      const r = await fetch(VOICE_URL + "/health", { cache: "no-store" });
      const h = await r.json(); voiceReady = !!h.ok;
      $("talk").title = h.ok ? "Reconocedor local " + h.recognizer + " · " + h.phrases + " frases del guion" : "Sin micrófono disponible";
    } catch (e) { voiceReady = false; $("talk").title = "La escucha de voz local no está en marcha (se inicia con ./arya.sh up)"; }
    talkRender();
  }
  voiceHealth(); setInterval(voiceHealth, 10000);
  $("talk").addEventListener("click", async () => {
    if (!voiceReady || listening || state.busy) return;
    if (window.AryaVoice) window.AryaVoice.stop();
    listening = true; talkRender();
    const chip = $("state"); const prev = [chip.dataset.state, chip.textContent];
    chip.dataset.state = "THINKING"; chip.textContent = STATE_TEXT.LISTENING;
    try {
      const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 18000);
      const r = await fetch(VOICE_URL + "/listen", { method: "POST", signal: ctl.signal }); clearTimeout(timer);
      const v = await r.json();
      if (!v.ok || !v.text) { bubble("system", null, "No se entendió la pregunta. Pulse HABLAR e intente de nuevo, o escríbala."); }
      else if ((v.source === "guion" && v.confidence >= 0.55) || (v.source === "dictado" && v.confidence >= 0.75)) { ask(v.text); }
      else { $("message").value = v.text; $("message").focus(); bubble("system", null, "Entendí: «" + v.text + "». Revise el texto y pulse ENVIAR."); }
    } catch (e) { bubble("system", null, "La escucha de voz no respondió. Puede escribir la pregunta."); }
    finally { listening = false; if (chip.textContent === STATE_TEXT.LISTENING) { chip.dataset.state = prev[0]; chip.textContent = prev[1]; } talkRender(); }
  });

  $("ask").addEventListener("submit", (ev) => { ev.preventDefault(); const v = $("message").value; $("message").value = ""; ask(v); });
  document.querySelectorAll("#suggest button").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));
})();
