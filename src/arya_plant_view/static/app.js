/* ARYA Industrial Demo - pantalla de operacion de la planta (sin dependencias externas).
   Toda la telemetria proviene de /api/telemetry/latest, que plant-view llena con su
   cliente OPC UA. Esta pagina no inventa datos: si faltan, lo indica. */
(function () {
  "use strict";

  const ANALOG = [
    { tag: "P101.MOTOR_TEMP", isa: "TI-101", name: "Temperatura motor", short: "TEMP. MOTOR", unit: "°C", dec: 1, scale: [40, 110], normal: [50, 65], span: 10, hi: "P101.MOTOR_TEMP.HI", hihi: "P101.MOTOR_TEMP.HIHI" },
    { tag: "P101.VIBRATION", isa: "VI-101", name: "Vibración", short: "VIBRACIÓN", unit: "mm/s", dec: 2, scale: [0, 10], normal: [1.4, 2.8], span: 2, hi: "P101.VIBRATION.HI", hihi: "P101.VIBRATION.HIHI" },
    { tag: "P101.CURRENT", isa: "II-101", name: "Corriente motor", short: "CORRIENTE", unit: "A", dec: 2, scale: [8, 16], normal: [10.8, 12.2], span: 1.5 },
    { tag: "P101.DISCHARGE_PRESSURE", isa: "PI-101", name: "Presión descarga", short: "PRESIÓN DESC.", unit: "bar", dec: 2, scale: [3, 6], normal: [4.55, 5.05], span: 0.6 },
    { tag: "P101.FLOW", isa: "FI-101", name: "Caudal", short: "CAUDAL", unit: "m³/h", dec: 1, scale: [30, 80], normal: [58, 66], span: 8, lo: "P101.FLOW.LO", lolo: "P101.FLOW.LOLO" },
    { tag: "P101.RPM", isa: "SI-101", name: "Velocidad", short: "VELOCIDAD", unit: "rpm", dec: 0, scale: [1440, 1520], normal: [1472, 1488], span: 30 },
  ];
  const BY_TAG = {}; ANALOG.forEach((a) => { BY_TAG[a.tag] = a; });
  // codigo -> [descripcion, nivel, prioridad, tag analogico]
  const ALARMS = {
    "P101.VIBRATION.HI": ["Vibración alta", "WARNING", 2, "P101.VIBRATION"],
    "P101.VIBRATION.HIHI": ["Vibración muy alta", "ALARM", 1, "P101.VIBRATION"],
    "P101.MOTOR_TEMP.HI": ["Temperatura de motor alta", "WARNING", 2, "P101.MOTOR_TEMP"],
    "P101.MOTOR_TEMP.HIHI": ["Temperatura de motor muy alta", "ALARM", 1, "P101.MOTOR_TEMP"],
    "P101.FLOW.LO": ["Caudal bajo", "WARNING", 2, "P101.FLOW"],
    "P101.FLOW.LOLO": ["Caudal muy bajo", "ALARM", 1, "P101.FLOW"],
  };
  const WINDOW_MS = 10 * 60 * 1000; // ventana visible de tendencias
  const MAX_POINTS = 3600;
  const GAP_MS = 3500; // un hueco mayor corta la linea: no se interpola lo no observado
  const SVG = "http://www.w3.org/2000/svg";

  const $ = (id) => document.getElementById(id);
  // /compact: misma pantalla y mismos datos, con menos paneles (media pantalla junto al agente).
  if (/\/compact\/?$/.test(window.location.pathname)) document.body.classList.add("compact");
  const state = {
    config: null, limits: {}, trends: {}, lastSeq: null, runId: null, token: "", pollMs: 1000,
    prevActive: null, seen: {}, acked: {}, journal: [], connState: null,
  };
  ANALOG.forEach((a) => { state.trends[a.tag] = []; });

  function el(name, attrs, text) {
    const node = document.createElementNS(SVG, name);
    Object.keys(attrs || {}).forEach((k) => node.setAttribute(k, attrs[k]));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function fmt(value, dec) { return typeof value === "number" && isFinite(value) ? value.toFixed(dec) : "—"; }
  function hhmmss(date) { return date.toLocaleTimeString("es-CL", { hour12: false }); }

  // ---------------------------------------------------------------- construccion
  ANALOG.forEach((a) => {
    // caja de instrumento en el diagrama
    const g = $("inst-" + a.tag);
    g.appendChild(el("rect", { class: "box", x: 0, y: 0, width: 180, height: 44 }));
    g.appendChild(el("text", { class: "i-tag", x: 7, y: 14 }, a.isa + " · " + a.short));
    g.appendChild(el("text", { class: "i-val", x: 104, y: 37, "text-anchor": "end" }, "—"));
    g.appendChild(el("text", { class: "i-unit", x: 110, y: 37 }, a.unit));
    const pa = el("g", { class: "i-pri a" });
    pa.appendChild(el("rect", { x: 154, y: 20, width: 20, height: 20, fill: "#d6001c" }));
    pa.appendChild(el("text", { x: 164, y: 35, "text-anchor": "middle", fill: "#fff", "font-size": 13, "font-weight": 800 }, "1"));
    const pw = el("g", { class: "i-pri w" });
    pw.appendChild(el("path", { d: "M164 19 l11 21 h-22 z", fill: "#f2b200" }));
    pw.appendChild(el("text", { x: 164, y: 38, "text-anchor": "middle", fill: "#1a1300", "font-size": 11, "font-weight": 800 }, "2"));
    g.appendChild(pa); g.appendChild(pw);

    // barra analogica en el faceplate
    const bar = document.createElement("div");
    bar.className = "bar"; bar.id = "bar-" + a.tag;
    bar.innerHTML = '<span class="b-name"></span><span class="b-val">—<small></small></span>';
    bar.querySelector(".b-name").innerHTML = "";
    bar.querySelector(".b-name").appendChild(document.createTextNode(a.name));
    const code = document.createElement("code"); code.textContent = a.isa + " · " + a.tag;
    bar.querySelector(".b-name").appendChild(code);
    const svg = el("svg", { viewBox: "0 0 300 22", preserveAspectRatio: "none" });
    const fx = (v) => Math.max(0, Math.min(300, ((v - a.scale[0]) / (a.scale[1] - a.scale[0])) * 300));
    svg.appendChild(el("rect", { class: "trk", x: 0, y: 8, width: 300, height: 8 }));
    svg.appendChild(el("rect", { class: "norm", x: fx(a.normal[0]), y: 8, width: fx(a.normal[1]) - fx(a.normal[0]), height: 8 }));
    svg.appendChild(el("g", { class: "lims" }));
    svg.appendChild(el("path", { class: "ptr", d: "M0 0", visibility: "hidden" }));
    bar.appendChild(svg);
    bar._fx = fx;
    $("bars").appendChild(bar);

    // tendencia
    const box = document.createElement("div");
    box.className = "trend"; box.id = "trend-" + a.tag;
    if (!a.hi && !a.lo) box.classList.add("secondary"); // sin limites de alarma: se oculta en la vista compacta
    box.innerHTML = '<div class="t-head"><b></b><span class="t-range"></span></div><canvas></canvas>';
    box.querySelector("b").textContent = a.isa + " " + a.name + " (" + a.unit + ")";
    $("trends").appendChild(box);
  });

  function drawLimits() {
    ANALOG.forEach((a) => {
      const bar = $("bar-" + a.tag); const g = bar.querySelector(".lims");
      while (g.firstChild) g.removeChild(g.firstChild);
      [[a.hi, "lim-w"], [a.lo, "lim-w"], [a.hihi, "lim-a"], [a.lolo, "lim-a"]].forEach((p) => {
        const lim = p[0] ? state.limits[p[0]] : undefined;
        if (typeof lim === "number") { const x = bar._fx(lim); g.appendChild(el("path", { class: p[1], d: "M" + x + " 3 V21" })); }
      });
    });
  }

  // ---------------------------------------------------------------- diario de eventos
  function journal(type, text, when) {
    state.journal.unshift({ t: hhmmss(when || new Date()), type: type, text: text });
    if (state.journal.length > 200) state.journal.pop();
    const body = $("journal"); body.innerHTML = "";
    state.journal.slice(0, 60).forEach((e) => {
      const tr = document.createElement("tr");
      [e.t, e.type, e.text].forEach((v, i) => { const td = document.createElement("td"); td.textContent = v; if (i === 2) td.className = "wrap"; tr.appendChild(td); });
      body.appendChild(tr);
    });
  }

  function alarmLevelOf(a, active) {
    if ((a.hihi && active.indexOf(a.hihi) >= 0) || (a.lolo && active.indexOf(a.lolo) >= 0)) return "ALARM";
    if ((a.hi && active.indexOf(a.hi) >= 0) || (a.lo && active.indexOf(a.lo) >= 0)) return "WARNING";
    return "NORMAL";
  }

  // ---------------------------------------------------------------- render
  function render(data) {
    const conn = data.connection, snap = data.snapshot;
    $("conn").dataset.state = conn.state;
    $("conn-text").textContent = conn.state === "CONNECTED" ? "OPC UA · EN LÍNEA" : conn.state === "CONNECTING" ? "OPC UA · CONECTANDO" : "OPC UA · SIN CONEXIÓN";
    $("d-endpoint").textContent = "OPC UA " + conn.endpoint;
    $("d-error").textContent = conn.last_error || "—";
    if (state.connState !== null && state.connState !== conn.state) {
      if (conn.state === "CONNECTED") journal("SISTEMA", "Comunicación OPC UA restablecida");
      else if (state.connState === "CONNECTED") journal("SISTEMA", "Comunicación OPC UA perdida" + (conn.last_error ? ": " + conn.last_error : ""));
    }
    state.connState = conn.state;

    const stale = !snap || snap.quality !== "GOOD";
    document.body.classList.toggle("is-stale", stale);
    const banner = $("banner");
    if (!snap) {
      banner.hidden = false;
      banner.textContent = "SIN DATOS DE LA PLANTA — " + (conn.last_error ? "error: " + conn.last_error : "esperando la primera lectura OPC UA");
    } else if (snap.quality === "STALE") {
      banner.hidden = false;
      banner.textContent = "DATOS DESACTUALIZADOS — última lectura real hace " + Math.round(snap.age_s) + " s. " + (conn.last_error ? "Error OPC UA: " + conn.last_error : "Conexión OPC UA: " + conn.state);
    } else if (snap.quality === "BAD") {
      banner.hidden = false; banner.textContent = "CALIDAD DE DATOS MALA — el servidor OPC UA reportó estados no válidos";
    } else { banner.hidden = true; }

    const q = $("quality");
    q.dataset.quality = snap ? snap.quality : "NONE"; q.textContent = snap ? snap.quality : "SIN DATOS";
    const proc = $("process");
    if (!snap) { proc.dataset.running = "false"; renderAlarmBar([], {}, true); return; }

    const tags = snap.tags;
    const level = tags["P101.ALARM_LEVEL"].value;
    const active = tags["P101.ACTIVE_ALARMS"].value || [];
    const status = tags["P101.STATUS"].value;
    const when = snap.source_timestamp ? new Date(snap.source_timestamp) : new Date();

    // cambio de ensayo
    if (snap.run_id !== state.runId) {
      if (state.runId !== null) {
        ANALOG.forEach((a) => { state.trends[a.tag] = []; });
        state.prevActive = null; state.seen = {}; state.acked = {};
        $("trend-note").textContent = "Nuevo ensayo detectado: tendencias reiniciadas";
        journal("SISTEMA", "Nuevo ensayo " + snap.run_id, when);
      }
      state.runId = snap.run_id; state.lastSeq = null;
    }

    // transiciones de alarma (solo con datos buenos)
    if (!stale) {
      if (state.prevActive === null) {
        active.forEach((c) => { state.seen[c] = hhmmss(when); journal("ALARMA", (ALARMS[c] || [c])[0] + " (" + c + ") ya activa al abrir la pantalla", when); });
      } else {
        active.forEach((c) => { if (state.prevActive.indexOf(c) < 0) { state.seen[c] = hhmmss(when); delete state.acked[c]; journal("ALARMA", "ACTIVA · " + (ALARMS[c] || [c])[0] + " (" + c + ")", when); } });
        state.prevActive.forEach((c) => { if (active.indexOf(c) < 0) { delete state.seen[c]; delete state.acked[c]; journal("ALARMA", "NORMALIZADA · " + (ALARMS[c] || [c])[0] + " (" + c + ")", when); } });
      }
      state.prevActive = active.slice();
    }

    proc.dataset.level = stale ? "UNKNOWN" : level;
    proc.dataset.running = String(!stale && status === "RUNNING");
    $("pid-state").textContent = stale ? "?" : (status === "RUNNING" ? "EN MARCHA" : status);
    $("fp-status").textContent = (status || "—") + (stale ? " (último)" : "");
    const fl = $("fp-level"); fl.dataset.level = stale ? "UNKNOWN" : level; fl.textContent = (level || "—") + (stale ? " (último)" : "");

    ANALOG.forEach((a) => {
      const v = tags[a.tag] ? tags[a.tag].value : null;
      const lv = stale ? "NORMAL" : alarmLevelOf(a, active);
      const unack = !stale && active.some((c) => ALARMS[c] && ALARMS[c][3] === a.tag && !state.acked[c]);
      const g = $("inst-" + a.tag);
      g.dataset.level = lv; g.dataset.unack = String(unack);
      g.querySelector(".i-val").textContent = fmt(v, a.dec);
      const bar = $("bar-" + a.tag);
      bar.dataset.level = lv;
      bar.querySelector(".b-val").firstChild.nodeValue = fmt(v, a.dec);
      bar.querySelector(".b-val small").textContent = a.unit;
      const ptr = bar.querySelector(".ptr");
      if (typeof v === "number") { const x = bar._fx(v); ptr.setAttribute("d", "M" + (x - 5) + " 0 H" + (x + 5) + " L" + x + " 9 z M" + (x - 1.2) + " 8 h2.4 v12 h-2.4 z"); ptr.setAttribute("visibility", "visible"); }
      else ptr.setAttribute("visibility", "hidden");
    });

    renderAlarmBar(active, tags, stale);

    $("d-ts").textContent = snap.source_timestamp ? snap.source_timestamp.replace("T", " ").replace("Z", " UTC") : "—";
    $("d-age").textContent = snap.age_s.toFixed(1) + " s";
    $("d-run").textContent = snap.run_id;
    $("d-seq").textContent = "#" + snap.seq + " · " + snap.sim_time_s.toFixed(0) + " s";

    if (snap.quality === "GOOD" && snap.seq !== state.lastSeq && snap.source_timestamp) {
      state.lastSeq = snap.seq;
      const t = Date.parse(snap.source_timestamp);
      ANALOG.forEach((a) => {
        const v = tags[a.tag] ? tags[a.tag].value : null;
        if (typeof v === "number") { const arr = state.trends[a.tag]; arr.push([t, v]); if (arr.length > MAX_POINTS) arr.shift(); }
      });
    }
    drawTrends();
  }

  function renderAlarmBar(active, tags, stale) {
    const sorted = active.slice().sort((x, y) => ((ALARMS[x] || [0, 0, 9])[2] - (ALARMS[y] || [0, 0, 9])[2]));
    const p1 = active.filter((c) => (ALARMS[c] || [])[1] === "ALARM").length;
    const p2 = active.length - p1;
    $("cnt-p1").textContent = stale ? "?" : String(p1);
    $("cnt-p2").textContent = stale ? "?" : String(p2);
    const bar = $("alarmbar");
    const unack = !stale && active.some((c) => !state.acked[c]);
    bar.dataset.unack = String(unack);
    $("ack").disabled = !unack;
    const body = $("alarms"); body.innerHTML = "";
    if (stale) {
      bar.dataset.level = "NONE";
      $("latest").textContent = "Datos desactualizados: el estado actual de las alarmas es desconocido";
    } else if (!sorted.length) {
      bar.dataset.level = "NONE"; $("latest").textContent = "Sin alarmas activas";
    } else {
      const c = sorted[0], info = ALARMS[c] || [c, "WARNING", 2, null], a = BY_TAG[info[3]];
      bar.dataset.level = info[1];
      $("latest").textContent = (state.seen[c] || "") + "   P" + info[2] + "   " + c + "   " + info[0] +
        (a && tags[a.tag] ? "   " + fmt(tags[a.tag].value, a.dec) + " " + a.unit : "");
    }
    if (!sorted.length) {
      const tr = document.createElement("tr"); tr.className = "empty";
      const td = document.createElement("td"); td.colSpan = 7;
      td.textContent = stale ? "Sin alarmas en la última lectura (desactualizada)" : "Sin alarmas activas";
      tr.appendChild(td); body.appendChild(tr);
    }
    sorted.forEach((c) => {
      const info = ALARMS[c] || [c, "WARNING", 2, null], a = BY_TAG[info[3]];
      const tr = document.createElement("tr");
      tr.dataset.level = stale ? "" : info[1]; tr.dataset.unack = String(!stale && !state.acked[c]);
      const cells = [state.seen[c] || "—", String(info[2]), c, info[0],
        a && tags[a.tag] ? fmt(tags[a.tag].value, a.dec) + " " + a.unit : "—",
        typeof state.limits[c] === "number" && a ? state.limits[c] + " " + a.unit : "—",
        stale ? "último conocido" : (state.acked[c] ? "RECONOCIDA" : "NO RECONOCIDA")];
      cells.forEach((v, i) => { const td = document.createElement("td"); if (i === 2) { const k = document.createElement("code"); k.textContent = v; td.appendChild(k); } else td.textContent = v; tr.appendChild(td); });
      body.appendChild(tr);
    });
    $("alarm-count").textContent = stale ? "estado desconocido" : active.length + " activas";
  }

  $("ack").addEventListener("click", () => {
    (state.prevActive || []).forEach((c) => { state.acked[c] = true; });
    journal("OPERADOR", "Alarmas reconocidas");
    $("alarmbar").dataset.unack = "false"; $("ack").disabled = true;
  });

  function renderApiDown(err) {
    $("conn").dataset.state = "API_DOWN";
    $("conn-text").textContent = "SERVIDOR HMI · SIN RESPUESTA";
    document.body.classList.add("is-stale");
    const banner = $("banner"); banner.hidden = false;
    banner.textContent = "DATOS DESACTUALIZADOS — el servicio plant-view no responde (" + err + "). Los valores en pantalla son los últimos recibidos.";
    const q = $("quality"); q.dataset.quality = "STALE"; q.textContent = "STALE";
    $("process").dataset.running = "false"; $("pid-state").textContent = "?";
    if (state.connState !== "API_DOWN") journal("SISTEMA", "Servidor de la pantalla sin respuesta");
    state.connState = "API_DOWN";
  }

  // ---------------------------------------------------------------- tendencias
  function drawTrends() {
    ANALOG.forEach((a) => {
      const box = $("trend-" + a.tag), canvas = box.querySelector("canvas");
      const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
      if (w === 0) return;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const all = state.trends[a.tag];
      const tEnd = all.length ? all[all.length - 1][0] : Date.now();
      const tStart = Math.max(tEnd - WINDOW_MS, all.length ? all[0][0] : tEnd);
      const pts = all.filter((p) => p[0] >= tStart);
      let lo = Infinity, hi = -Infinity;
      pts.forEach((p) => { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); });
      lo = Math.min(lo, a.normal[0]); hi = Math.max(hi, a.normal[1]);
      [a.hi, a.lo].forEach((n) => { const lim = n ? state.limits[n] : undefined; if (typeof lim === "number") { lo = Math.min(lo, lim); hi = Math.max(hi, lim); } });
      if (hi - lo < a.span) { const mid = (hi + lo) / 2; lo = mid - a.span / 2; hi = mid + a.span / 2; }
      const pad = (hi - lo) * 0.08; hi += pad; lo = a.scale[0] === 0 ? Math.max(0, lo - pad) : lo - pad;
      const L = 2, R = w - 2, T = 4, B = h - 4;
      const x = (t) => (tEnd === tStart ? R : L + ((t - tStart) / (tEnd - tStart)) * (R - L));
      const y = (v) => B - ((v - lo) / (hi - lo)) * (B - T);
      ctx.fillStyle = "#c9d3e0"; ctx.fillRect(L, y(a.normal[1]), R - L, y(a.normal[0]) - y(a.normal[1])); // banda normal
      ctx.strokeStyle = "#aab0b6"; ctx.lineWidth = 1;
      for (let i = 0; i <= 2; i++) { const gy = T + ((B - T) * i) / 2; ctx.beginPath(); ctx.moveTo(L, gy); ctx.lineTo(R, gy); ctx.stroke(); }
      [[a.hi, "#a87c00"], [a.lo, "#a87c00"], [a.hihi, "#d6001c"], [a.lolo, "#d6001c"]].forEach((pair) => {
        const lim = pair[0] ? state.limits[pair[0]] : undefined;
        if (typeof lim !== "number" || lim < lo || lim > hi) return;
        ctx.save(); ctx.setLineDash([6, 4]); ctx.strokeStyle = pair[1]; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(L, y(lim)); ctx.lineTo(R, y(lim)); ctx.stroke(); ctx.restore();
      });
      if (pts.length) {
        ctx.strokeStyle = "#0a3a86"; ctx.lineWidth = 1.8; ctx.lineJoin = "round"; ctx.beginPath();
        pts.forEach((p, i) => { if (i === 0 || p[0] - pts[i - 1][0] > GAP_MS) ctx.moveTo(x(p[0]), y(p[1])); else ctx.lineTo(x(p[0]), y(p[1])); });
        ctx.stroke();
        const last = pts[pts.length - 1];  // marca el valor actual (visible aunque haya una sola muestra)
        ctx.fillStyle = "#0a3a86"; ctx.beginPath(); ctx.arc(Math.min(x(last[0]), R - 3), y(last[1]), 3, 0, Math.PI * 2); ctx.fill();
      } else {
        ctx.fillStyle = "#4c545c"; ctx.font = "12px sans-serif"; ctx.textAlign = "center"; ctx.fillText("Sin muestras todavía", w / 2, h / 2);
      }
      const secs = Math.round((tEnd - tStart) / 1000);
      box.querySelector(".t-range").textContent = fmt(lo, a.dec) + "–" + fmt(hi, a.dec) + (pts.length ? " · " + (secs >= 120 ? Math.round(secs / 60) + " min" : secs + " s") : "");
    });
  }
  window.addEventListener("resize", drawTrends);

  // ---------------------------------------------------------------- sondeo
  async function fetchJson(url, options) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 4000);
    try {
      const res = await fetch(url, Object.assign({ cache: "no-store", signal: ctl.signal }, options || {}));
      let body = null;
      try { body = await res.json(); } catch (e) { /* cuerpo no JSON */ }
      return { ok: res.ok, status: res.status, body: body };
    } finally { clearTimeout(timer); }
  }
  async function loadConfig() {
    try {
      const r = await fetchJson("/api/config");
      if (r.ok) { state.config = r.body; state.limits = r.body.limits || {}; state.pollMs = Math.max(250, (r.body.sample_seconds || 1) * 1000); drawLimits(); }
    } catch (e) { /* se reintenta */ }
  }
  async function poll() {
    try {
      const r = await fetchJson("/api/telemetry/latest");
      if (!r.ok || !r.body) throw new Error("HTTP " + r.status);
      if (!state.config || Object.keys(state.limits).length === 0) await loadConfig();
      render(r.body);
    } catch (e) { renderApiDown(e.name === "AbortError" ? "tiempo de espera agotado" : (e.message || "error de red")); }
    setTimeout(poll, state.pollMs);
  }
  function tick() {
    const now = new Date();
    $("clock-time").textContent = hhmmss(now);
    $("clock-date").textContent = now.toLocaleDateString("es-CL", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
  }
  tick(); setInterval(tick, 1000);

  // ---------------------------------------------------------------- controles del presentador
  const drawer = $("drawer"), toggle = $("demo-toggle");
  function setDrawer(open) {
    drawer.hidden = !open; toggle.setAttribute("aria-pressed", String(open));
    try { sessionStorage.setItem("arya-demo-drawer", open ? "1" : "0"); } catch (e) { /* sin almacenamiento */ }
  }
  toggle.addEventListener("click", () => setDrawer(drawer.hidden));

  function controlUrl() { return "http://" + window.location.hostname + ":" + ((state.config && state.config.control_port) || 9001); }
  function setToken(token) {
    state.token = token.trim();
    try { if (state.token) sessionStorage.setItem("arya-demo-token", state.token); else sessionStorage.removeItem("arya-demo-token"); } catch (e) { /* sin almacenamiento */ }
    document.querySelectorAll(".btn.act").forEach((b) => { b.disabled = !state.token; });
    $("token").value = "";
    $("token").placeholder = state.token ? "Token cargado (oculto)" : "Token local de control (.env)";
    if (state.token) refreshScenario();
  }
  function controlMessage(kind, text) { const m = $("control-msg"); m.hidden = false; m.dataset.kind = kind; m.textContent = text; }
  const MODE_TEXT = { NORMAL: "Operación normal", DEGRADATION: "Falla inyectada (degradación en curso)", RECOVERY: "Falla retirada (recuperación gradual)" };
  const SCEN_TEXT = { alpha: "Escenario A", bravo: "Escenario B" };
  function showScenario(s) {
    let text = "Escenario: " + (MODE_TEXT[s.mode] || s.mode);
    if (s.mode !== "NORMAL") text += " · " + (SCEN_TEXT[s.scenario] || "") + " · avance " + Math.round(s.fault_progress * 100) + " %";
    if (s.scheduled_fault) text += " — Programada: " + (SCEN_TEXT[s.scheduled_fault.scenario] || "") + " en " + Math.ceil(s.scheduled_fault.starts_in_s / 60) + " min";
    $("scenario").textContent = text;
  }
  async function refreshScenario() {
    if (!state.token) return;
    try {
      const r = await fetchJson(controlUrl() + "/api/demo/state", { headers: { Authorization: "Bearer " + state.token } });
      if (r.ok) showScenario(r.body); else if (r.status === 401) $("scenario").textContent = "Token rechazado por la API de control.";
    } catch (e) { $("scenario").textContent = "API de control sin respuesta."; }
  }
  const ACTION_OK = {
    "inject-fault": "Falla inyectada: las señales evolucionarán gradualmente.",
    "normal": "Falla retirada: los valores vuelven gradualmente a lo normal (la temperatura tarda por su inercia). Para reiniciar de inmediato use RESET DEMO.",
    "reset": "Simulación reiniciada al estado inicial con un nuevo ensayo.",
    "schedule-fault": "Falla programada: comenzará sola.",
    "cancel-schedule": "Programación cancelada.",
  };
  const ACTION_LOG = { "inject-fault": "INJECT FAULT", "normal": "NORMAL OPERATION", "reset": "RESET DEMO", "schedule-fault": "Falla programada", "cancel-schedule": "Programación cancelada" };
  async function sendAction(action) {
    let body = {};
    const scenario = $("scenario-select").value;
    if (action === "inject-fault") body = { scenario: scenario };
    try {
      const r = await fetchJson(controlUrl() + "/api/demo/" + action, {
        method: "POST", headers: { Authorization: "Bearer " + state.token, "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (r.ok) {
        const noop = action === "normal" && r.body && r.body.mode !== "RECOVERY";
        controlMessage("ok", noop ? "No había una falla activa que retirar." : ACTION_OK[action]);
        showScenario(r.body);
        if (!noop) journal("DEMO", ACTION_LOG[action] + " (presentador)");
      } else if (r.status === 401) controlMessage("error", "Token rechazado. Verifique el token de .env.");
      else if (r.status === 409) controlMessage("error", "No se puede inyectar ahora: ya hay una falla activa o la planta aún se está recuperando. Espere a NORMAL o use RESET DEMO.");
      else controlMessage("error", "La API de control respondió " + r.status + ".");
    } catch (e) { controlMessage("error", "No se pudo contactar la API de control en " + controlUrl() + "."); }
  }
  document.querySelectorAll(".btn.act").forEach((b) => b.addEventListener("click", () => sendAction(b.dataset.action)));
  $("token-save").addEventListener("click", () => setToken($("token").value));
  $("token").addEventListener("keydown", (e) => { if (e.key === "Enter") setToken($("token").value); });

  // El script open-scada entrega el token en el fragmento (#token=...), que el
  // navegador nunca envia al servidor; se retira de la URL de inmediato.
  let initial = "", drawerOpen = false;
  const m = /[#&]token=([^&]+)/.exec(window.location.hash);
  if (m) { initial = decodeURIComponent(m[1]); history.replaceState(null, "", window.location.pathname + window.location.search); }
  else { try { initial = sessionStorage.getItem("arya-demo-token") || ""; } catch (e) { /* sin almacenamiento */ } }
  try { drawerOpen = sessionStorage.getItem("arya-demo-drawer") === "1"; } catch (e) { /* sin almacenamiento */ }
  setDrawer(drawerOpen);

  loadConfig().then(() => { if (initial) setToken(initial); poll(); });
  setInterval(refreshScenario, 2000);
})();
