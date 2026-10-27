/* ARYA POR DENTRO - tablero que se ilumina con lo que el agente usa.
   Todo proviene de los eventos reales del agente. Como una herramienta tarda milisegundos,
   los eventos se muestran en su orden real pero a un ritmo visible (cola con tiempo minimo
   por paso). No se inventa ningun paso: si no hubo evento, nada se enciende. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const ICONS = {
    modelo: '<circle cx="12" cy="14" r="6"/><circle cx="38" cy="10" r="6"/><circle cx="34" cy="38" r="6"/><circle cx="10" cy="38" r="5"/><path d="M18 13 L32 11 M37 16 L35 32 M16 18 L30 34 M11 20 L10 33 M15 38 H28"/>',
    prompt: '<path d="M12 6 H38 V44 H12 Z M18 16 H32 M18 24 H32 M18 32 H27"/>',
    contexto: '<rect x="6" y="8" width="38" height="34" rx="3"/><path d="M6 18 H44 M20 18 V42"/>',
    memoria: '<circle cx="26" cy="26" r="18"/><path d="M26 15 V26 L34 31 M5 14 V24 H15"/>',
    rag: '<path d="M25 12 C19 7 11 7 6 9 V40 C11 38 19 38 25 43 C31 38 39 38 44 40 V9 C39 7 31 7 25 12 Z M25 12 V43"/>',
    percepcion: '<path d="M4 25 C12 12 38 12 46 25 C38 38 12 38 4 25 Z"/><circle cx="25" cy="25" r="6"/>',
    herramientas: '<path d="M41 9 A10 10 0 1 0 28 22 L9 41 A3.5 3.5 0 0 0 14 46 L33 27 A10 10 0 0 0 46 14 L39 21 L34 16 Z"/>',
    mcp: '<path d="M17 5 V15 M33 5 V15 M11 15 H39 V24 A14 14 0 0 1 11 24 Z M25 38 V47"/>',
    guardrails: '<path d="M25 5 L43 11 V25 C43 35 35 43 25 46 C15 43 7 35 7 25 V11 Z M17 25 L23 31 L34 19"/>',
    observabilidad: '<path d="M7 38 A20 20 0 1 1 43 38 M25 28 L35 17"/><circle cx="25" cy="29" r="3"/>',
  };
  const CARDS = [
    ["modelo", "Modelo", "Razonamiento local en la GB10"],
    ["prompt", "Prompt de sistema", "Rol y 5 reglas fijas del agente"],
    ["contexto", "Ventana de contexto", "Lo que el modelo ve en cada paso"],
    ["memoria", "Memoria", "Sesión e historial de incidentes"],
    ["rag", "RAG", "Manuales y procedimientos"],
    ["percepcion", "Percepción", "Preguntas, alarmas y señales de planta"],
    ["herramientas", "Herramientas", "Consulta sistemas y prepara órdenes"],
    ["mcp", "MCP", "Estándar abierto para conectar herramientas"],
    ["guardrails", "Guardrails y control humano", "Límites en el código; aprueba una persona"],
    ["observabilidad", "Observabilidad", "Qué hizo, con qué fuente y cuánto tardó"],
  ];
  // herramienta -> tarjetas adicionales que usa y fuente legible
  const TOOL_MAP = {
    get_current_tags: [["percepcion"], "planta en vivo (OPC UA)"], get_equipment_status: [["percepcion"], "planta en vivo (OPC UA)"],
    get_active_alarms: [["percepcion"], "planta en vivo (OPC UA)"], get_historian_data: [[], "historian"], compare_signals: [[], "historian"],
    search_maintenance_documents: [["rag"], "documentos de planta"], search_previous_work_orders: [[], "CMMS"], get_work_order: [[], "CMMS"],
    search_agent_memory: [["memoria"], "memoria de largo plazo"], create_work_order_draft: [["guardrails"], "CMMS (solo borrador)"],
  };
  const root = $("inside");
  if (!root) return;

  // ------------------------------------------------------------ construccion
  CARDS.forEach((c, i) => {
    const el = document.createElement("div");
    el.className = "in-card" + (c[0] === "mcp" ? " off" : ""); el.id = "in-" + c[0];
    el.innerHTML = '<svg viewBox="0 0 50 50" class="in-ico" fill="none" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">' + ICONS[c[0]] + "</svg>" +
      '<div class="in-body"><b></b><small></small><span class="in-live"></span><span class="in-count"></span></div>';
    el.querySelector("b").textContent = c[1]; el.querySelector("small").textContent = c[2];
    if (c[0] === "mcp") { el.querySelector(".in-live").textContent = "No implementado en esta demo"; }
    if (c[0] === "contexto") { const bar = document.createElement("div"); bar.className = "in-bar"; bar.appendChild(document.createElement("i")); el.querySelector(".in-body").appendChild(bar); }
    $(i < 5 ? "in-left" : "in-right").appendChild(el);
  });
  const live = (id, text) => { const n = $("in-" + id); if (n) { const l = n.querySelector(".in-live"); l.textContent = text || ""; l.title = text || ""; } };
  const count = (id, text) => { const n = $("in-" + id); if (n) n.querySelector(".in-count").textContent = text || ""; };

  // ------------------------------------------------------------ reproductor
  const queue = []; let playing = false, clearTimer = null, replaying = false;
  const turn = { tools: 0, events: 0, ms: 0 };
  const limits = { tools: 8, context: null };
  const fmtN = (n) => Number(n || 0).toLocaleString("es-CL");
  function contextBar(tokens) {
    const bar = document.querySelector("#in-contexto .in-bar i");
    if (bar && limits.context && tokens) bar.style.width = Math.min(100, (tokens / limits.context) * 100).toFixed(1) + "%";
  }
  let lastTurn = [], currentTurn = [], currentTurnId = null;
  // Franja central: tokens, TTFT y TPOT de la ultima respuesta (valores reales del modelo).
  let conversationTokens = 0, nodeLabel = "";
  function metricsFoot(e) {
    const tps = e && e.tpot_ms ? " · ≈ " + fmtN(Math.round(1000 / e.tpot_ms)) + " tokens/s" : "";
    $("mt-foot").textContent = (e ? "Última respuesta" + tps : "Sin respuestas todavía") + " · total: " + fmtN(conversationTokens) + " tokens" + (nodeLabel ? " · " + nodeLabel : "");
  }
  function metrics(e) {
    $("mt-in").textContent = e ? fmtN(e.prompt_tokens) : "—";
    $("mt-out").textContent = e ? fmtN(e.completion_tokens) : "—";
    $("mt-ttft").textContent = e && e.ttft_ms != null ? fmtN(e.ttft_ms) : "—";
    $("mt-tpot").textContent = e && e.tpot_ms != null ? e.tpot_ms.toFixed(1).replace(".", ",") : "—";
    if (e && e.conversation_tokens != null) conversationTokens = e.conversation_tokens;
    metricsFoot(e);
    const box = document.querySelector(".in-metrics"); box.classList.add("fresh"); setTimeout(() => box.classList.remove("fresh"), 2500);
  }

  const RESET_ON_NEW_QUESTION = ["prompt", "contexto", "rag", "herramientas", "guardrails", "observabilidad", "percepcion"];
  function light(step) {
    if (step.reset) RESET_ON_NEW_QUESTION.forEach((id) => live(id, ""));  // cada pregunta empieza con el tablero limpio
    document.querySelectorAll(".in-card.on, .in-node.on").forEach((n) => n.classList.remove("on"));
    $("in-center").classList.toggle("on", !!step.center);
    (step.cards || []).forEach((id) => { const n = $("in-" + id); if (n) n.classList.add("on"); });
    if (step.node) $("in-node-" + step.node).classList.add("on");
    Object.keys(step.live || {}).forEach((id) => live(id, step.live[id]));
    Object.keys(step.count || {}).forEach((id) => count(id, step.count[id]));
    if (step.ctx) contextBar(step.ctx);
    if (step.metrics) metrics(step.metrics);
    $("in-now").textContent = (replaying ? "REPETICIÓN · " : "") + (step.now || "");
  }
  function next() {
    if (!queue.length) {
      playing = false;
      if (replaying) { replaying = false; $("in-replay").disabled = lastTurn.length === 0; }
      clearTimer = setTimeout(() => { light({ now: "En espera de la próxima pregunta o alarma" }); }, 1600);
      return;
    }
    playing = true; clearTimeout(clearTimer);
    const step = queue.shift();
    light(step);
    setTimeout(next, step.hold * (replaying ? 1.7 : 1));
  }
  function push(step) { queue.push(step); if (!playing) next(); }

  function stepsFor(e) {
    switch (e.type) {
      case "user_message": turn.tools = 0; turn.events = 0; turn.ms = 0;
        return [{ reset: true, node: 1, cards: ["percepcion"], hold: 900, live: { percepcion: "Pregunta: «" + e.text + "»" }, count: { herramientas: "0 / " + limits.tools, observabilidad: "" }, now: "1 · Percibe la pregunta del operador" }];
      case "system_trigger": turn.tools = 0; turn.events = 0; turn.ms = 0;
        return [{ reset: true, node: 1, cards: ["percepcion"], hold: 1100, live: { percepcion: "Alarma detectada: interviene sin que le pregunten" }, count: { herramientas: "0 / " + limits.tools }, now: "1 · Percibe una alarma nueva en la planta" }];
      case "state":
        if (e.state === "THINKING") return [{ node: 2, cards: ["modelo", "prompt", "contexto"], center: true, hold: 600, live: { prompt: "Enviado al modelo en este paso" }, now: "2 · Razona: el modelo recibe el contexto (paso " + e.step + ")" }];
        return [];
      case "llm_call": {
        const asks = e.requested_tools && e.requested_tools.length;
        return [{ node: 2, cards: ["modelo", "prompt", "contexto"], center: true, hold: 700,
          live: { modelo: fmtN(e.completion_tokens) + " tokens generados en " + fmtN(e.latency_ms) + " ms",
                  contexto: e.prompt_tokens ? fmtN(e.prompt_tokens) + (limits.context ? " de " + fmtN(limits.context) : "") + " tokens en el contexto" : "tokens no informados por el modelo" },
          ctx: e.prompt_tokens,
          now: "2 · El modelo decide: " + (asks ? "pedir " + e.requested_tools.join(", ") : "redactar la respuesta") }];
      }
      case "llm_error":
        return [{ node: 2, cards: ["modelo", "guardrails"], hold: 1400, live: { modelo: "sin respuesta", guardrails: "Sin modelo: se entrega un aviso fijo, nada inventado" }, now: "Guardrail: el modelo no está disponible" }];
      case "tool_start": {
        const m = TOOL_MAP[e.tool] || [[], "—"];
        return [{ node: 3, cards: ["herramientas"].concat(m[0]), hold: 650, live: { herramientas: e.tool + " → " + m[1] }, now: "3 · Actúa: consulta " + m[1] + " con " + e.tool }];
      }
      case "tool_end": {
        const m = TOOL_MAP[e.tool] || [[], "—"]; turn.tools += 1; turn.ms += e.duration_ms || 0;
        const lv = { herramientas: e.tool + " · " + e.duration_ms + " ms · " + (e.ok ? "OK" : "ERROR"), observabilidad: e.tool + " · " + e.source + " · " + e.duration_ms + " ms" };
        if (e.tool === "search_maintenance_documents" && e.ok) lv.rag = "Recuperó: " + e.summary;
        if (e.tool === "search_agent_memory" && e.ok) lv.memoria = e.summary;
        if (e.tool === "create_work_order_draft" && e.ok) lv.guardrails = "Creó solo un BORRADOR: " + e.summary;
        if (m[0].indexOf("percepcion") >= 0 && e.ok) lv.percepcion = "Planta: " + e.summary;
        const cards = ["herramientas", "observabilidad"].concat(m[0]);
        if (!e.ok) { cards.push("guardrails"); lv.guardrails = "Error controlado: el modelo recibe el aviso, no datos"; }
        return [{ node: 4, cards: cards, hold: 850, live: lv, count: { herramientas: turn.tools + " / " + limits.tools }, now: "4 · Observa el resultado de " + e.tool + ": " + e.summary }];
      }
      case "guardrail":
        return [{ cards: ["guardrails"], hold: e.rule === "tool_required" ? 500 : 1300, live: { guardrails: e.message }, now: "Guardrail: " + e.message }];
      case "work_order_draft":
        return [{ cards: ["guardrails"], hold: 1500, live: { guardrails: "Borrador " + e.work_order.id + " espera la decisión de una persona" }, now: "Control humano: la orden queda en borrador hasta que alguien decida" }];
      case "human_decision":
        return [{ cards: ["guardrails", "memoria"], hold: 1800, live: { guardrails: e.work_order_id + " · " + (e.status === "OPEN" ? "aprobada" : "rechazada") + (e.decided_by ? " por " + e.decided_by : ""), memoria: "Decisión verificada en el CMMS y guardada" }, now: "Control humano: decisión registrada y recordada" }];
      case "assistant_message": {
        const used = (e.prompt_tokens || 0) + (e.completion_tokens || 0);
        const lv = { observabilidad: "Pregunta: " + (e.total_ms / 1000).toFixed(1).replace(".", ",") + " s · " + fmtN(used) + " tokens (" + fmtN(e.prompt_tokens) + " entrada, " + fmtN(e.completion_tokens) + " salida)" };
        const cards = ["observabilidad"];
        if (e.status === "limit_reached") { cards.push("guardrails"); lv.guardrails = "Límite de consultas alcanzado: el ciclo se detuvo"; }
        if (e.status === "timeout") { cards.push("guardrails"); lv.guardrails = "Tiempo máximo alcanzado: el ciclo se detuvo"; }
        return [{ center: true, cards: cards, hold: 1800, live: lv, metrics: e, count: { observabilidad: "Conversación: " + fmtN(e.conversation_tokens) + " tokens" }, now: "Responde" + (e.sources && e.sources.length ? " citando: " + e.sources.join(" · ") : "") }];
      }
    }
    return [];
  }

  // ------------------------------------------------------------ interfaz publica
  window.AryaInside = {
    /* animate=false para el historial que se recibe al abrir la pagina */
    onEvent(e, animate) {
      if (e.type === "conversation_cleared") {
        queue.length = 0; lastTurn = []; currentTurn = []; currentTurnId = null; $("in-replay").disabled = true;
        RESET_ON_NEW_QUESTION.forEach((id) => live(id, "")); count("herramientas", ""); count("observabilidad", "Conversación: 0 tokens"); contextBar(0.0001);
        conversationTokens = 0; metrics(null);
        light({ now: "Conversación reiniciada · en espera de la próxima pregunta o alarma" });
        return;
      }
      if (e.turn_id) {
        if (e.turn_id !== currentTurnId) { currentTurnId = e.turn_id; currentTurn = []; }
        currentTurn.push(e);
        if (e.type === "assistant_message") { lastTurn = currentTurn.slice(); if (!replaying) $("in-replay").disabled = false; }
      } else if (e.type === "human_decision" && lastTurn.length) lastTurn.push(e);
      const steps = stepsFor(e);
      if (animate) steps.forEach(push);
      else steps.forEach((s) => { Object.keys(s.live || {}).forEach((id) => live(id, s.live[id])); Object.keys(s.count || {}).forEach((id) => count(id, s.count[id])); if (s.metrics) metrics(s.metrics); });
    },
    setStatus(s) {
      limits.tools = (s.limits && s.limits.max_tool_calls) || 8;
      if (s.llm.context_limit) { limits.context = s.llm.context_limit; count("contexto", "límite " + fmtN(limits.context)); }
      if (s.tokens) count("observabilidad", "Conversación: " + fmtN(s.tokens.conversation.prompt + s.tokens.conversation.completion) + " tokens");
      nodeLabel = ""; if ($("mt-in").textContent === "—") metricsFoot(null);
      count("memoria", s.memory_incidents + " incidente" + (s.memory_incidents === 1 ? "" : "s"));
      count("rag", s.documents + " documentos");
      if (!s.llm.reachable) count("modelo", s.llm.configured ? "Sin respuesta del modelo" : "Modelo no configurado");
      $("in-modelo").classList.toggle("warn", !s.llm.reachable);
      if (!$("in-modelo").querySelector(".in-live").textContent) live("modelo", s.llm.model ? s.llm.model.replace(/^nvidia\//, "") + (limits.context ? " · contexto " + fmtN(limits.context / 1000) + "k" : "") : "Nemotron aún no conectado");
    },
    replay() {
      if (!lastTurn.length || playing) return;
      replaying = true; $("in-replay").disabled = true; turn.tools = 0;
      lastTurn.forEach((e) => stepsFor(e).forEach((s) => queue.push(s)));
      next();
    },
  };
  $("in-replay").addEventListener("click", () => window.AryaInside.replay());
  light({ now: "En espera de la próxima pregunta o alarma" });
})();
