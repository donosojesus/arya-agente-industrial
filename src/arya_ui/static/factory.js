/* Del agente a la AI Factory - pagina independiente y de solo lectura: no modifica la simulacion.
   La etapa 1 usa mediciones reales de ARYA; si no hay respuestas recientes, las del ensayo del 19-10-2026. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const fmt = (n, d) => Number(n).toLocaleString("es-CL", { maximumFractionDigits: d || 0, minimumFractionDigits: d || 0 });
  // Ensayo con Nemotron real del 19-10-2026 (validation.md): promedio de las respuestas del recorrido.
  const MEASURED_19_10 = { prompt: 8000, completion: 200, seconds: 4.6, ttft: null, tpot: null };
  // Un paso con razonamiento encendido genero 679 tokens frente a 17 apagado (medido el 19-10); unos 5 pasos por consulta.
  const THINKING_OUTPUT_PER_QUERY = 3400;
  let measured = Object.assign({}, MEASURED_19_10), live = false;

  async function loadMeasured() {
    try {
      const r = await fetch("/agent/api/v1/trace?limit=1000", { cache: "no-store" });
      const events = (await r.json()).events.filter((e) => e.type === "assistant_message" && e.status === "ok" && e.prompt_tokens);
      if (events.length) {
        const avg = (k) => events.reduce((s, e) => s + (e[k] || 0), 0) / events.length;
        const withSpeed = events.filter((e) => e.ttft_ms != null);
        measured = { prompt: Math.round(avg("prompt_tokens")), completion: Math.round(avg("completion_tokens")), seconds: avg("total_ms") / 1000,
          ttft: withSpeed.length ? withSpeed.reduce((s, e) => s + e.ttft_ms, 0) / withSpeed.length : null,
          tpot: withSpeed.length ? withSpeed.reduce((s, e) => s + (e.tpot_ms || 0), 0) / withSpeed.length : null, n: events.length };
        live = true;
      }
    } catch (e) { /* agente no disponible: se usan las mediciones del 19-10 */ }
    $("m-tokens").textContent = fmt(measured.prompt) + " entrada · " + fmt(measured.completion) + " salida";
    $("m-time").textContent = fmt(measured.seconds, 1) + " s";
    $("m-speed").textContent = measured.ttft != null ? fmt(measured.ttft) + " ms · " + fmt(measured.tpot, 1) + " ms/token" : "se mide con el modelo conectado";
    $("m-source").textContent = live ? "en vivo · " + measured.n + " respuesta(s) de esta sesión" : "ensayo con Nemotron del 19-10-2026";
    if (!$("a-in").dataset.touched) $("a-in").value = measured.prompt;
    if (!$("a-out").dataset.touched) $("a-out").value = measured.completion;
    compute();
  }

  function val(id) { return Number($(id).value); }
  function compute() {
    const plants = val("plants"), agents = val("agents"), qph = val("qph"), peak = val("peak"), cams = val("cams"), assets = val("assets");
    ["plants", "agents", "qph", "cams", "assets"].forEach((k) => { $("o-" + k).textContent = fmt(val(k)); });
    $("o-peak").textContent = "× " + fmt(peak, 1);
    const tin = val("a-in"), tout = $("think").checked ? Math.max(val("a-out"), THINKING_OUTPUT_PER_QUERY) : val("a-out");
    const queriesH = plants * agents * qph;
    const qpsPeak = (queriesH / 3600) * peak;
    const gpuSecondsPerQuery = tin / val("a-prefill") + tout / val("a-decode");
    const util = Math.min(0.9, Math.max(0.1, val("a-util") / 100));
    const llmGpus = Math.max(1, Math.ceil((qpsPeak * gpuSecondsPerQuery) / util));
    const visionGpus = Math.ceil(plants * cams * val("a-cam"));
    const gpus = llmGpus + visionGpus + 1;  // +1 de respaldo
    const servers = Math.ceil(gpus / 8);
    const clusters = Math.ceil(servers / 16);  // la referencia 2-8-5-200 llega a 16 nodos por clúster
    const bytesYear = plants * assets * val("a-bytes") * 86400 * 365;
    $("r-servers").textContent = fmt(servers);
    $("r-clusters").textContent = "(" + (clusters === 1 ? "1 clúster" : fmt(clusters) + " clústeres") + " de referencia 2-8-5-200 · + 4 PowerEdge R670 de control por clúster)";
    $("r-gpus").textContent = fmt(gpus);
    $("r-gpus-split").textContent = "(" + fmt(llmGpus) + " para agentes · " + fmt(visionGpus) + " para visión · 1 de respaldo)";
    $("r-storage").textContent = bytesYear >= 1e15 ? fmt(bytesYear / 1e15, 1) + " PB" : bytesYear >= 1e12 ? fmt(bytesYear / 1e12, 1) + " TB" : fmt(bytesYear / 1e9, 0) + " GB";
    $("r-queries").textContent = fmt(queriesH) + " por hora";
    $("r-tokens").textContent = fmt(queriesH * 24 * (tin + tout) / 1e6, 1) + " millones";
    $("r-tps").textContent = fmt(qpsPeak * (tin + tout)) + " tokens/s";
  }
  document.querySelectorAll("input").forEach((i) => i.addEventListener("input", () => { if (i.id === "a-in" || i.id === "a-out") i.dataset.touched = "1"; compute(); }));
  loadMeasured(); setInterval(loadMeasured, 15000);

  // ---------------------------------------------------------------- ¿como la protegemos?
  const prot = $("prot");
  function focus(layer) {
    const same = prot.classList.contains("focus") && prot.querySelector('.layer.on[data-layer="' + layer + '"]');
    prot.querySelectorAll("[data-layer]").forEach((n) => n.classList.remove("on"));
    prot.classList.toggle("focus", !same);
    if (!same) prot.querySelectorAll('[data-layer="' + layer + '"]').forEach((n) => n.classList.add("on"));
  }
  prot.querySelectorAll("[data-layer]").forEach((b) => b.addEventListener("click", () => focus(b.dataset.layer)));
  // Vista por capas (principal): pulsar una capa muestra su detalle; la matriz de Dell queda como detalle.
  function pick(l) {
    prot.querySelectorAll(".ring").forEach((r) => r.classList.toggle("sel", r.dataset.l === l));
    prot.querySelectorAll(".pdet section").forEach((sec) => { sec.hidden = sec.dataset.d !== l; });
  }
  prot.querySelectorAll(".ring").forEach((r) => r.addEventListener("click", (ev) => { ev.stopPropagation(); pick(r.dataset.l); }));
  function dellView(on) {
    $("prot-dell").hidden = !on; $("prot-layers").hidden = on; $("prot-layers-foot").hidden = on;
    $("prot-mode").textContent = on ? "VER LAS CAPAS DE PROTECCIÓN" : "VER EL DETALLE SEGÚN DELL";
  }
  $("prot-mode").addEventListener("click", () => dellView($("prot-dell").hidden));
  pick("datos");
  $("protect").addEventListener("click", () => { prot.hidden = false; prot.classList.remove("focus"); dellView(false); pick("datos"); });
  $("prot-close").addEventListener("click", () => { prot.hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") prot.hidden = true; });
  if (/[?&]view=protect/.test(window.location.search)) prot.hidden = false;
  const startLayer = /[?&]layer=(perim|ident|infra|datos|agente)/.exec(window.location.search); if (startLayer) pick(startLayer[1]);
  if (/[?&]detail=dell/.test(window.location.search)) dellView(true);

  // ---------------------------------------------------------------- stack completo
  const stackv = $("stackv");
  // Torre de la AI Factory: pulsar una capa la resalta y muestra su detalle; pulsarla de nuevo vuelve a la lectura general.
  function stackFocus(k) {
    const same = stackv.querySelector('[data-k="' + k + '"].on');
    stackv.querySelectorAll("[data-k]").forEach((n) => n.classList.toggle("on", !same && n.dataset.k === k));
    stackv.classList.toggle("focus", !same);
    const show = same ? "intro" : k;
    stackv.querySelectorAll(".af-det section").forEach((sec) => { sec.hidden = sec.dataset.d !== show; });
  }
  stackv.querySelectorAll("[data-k]").forEach((n) => n.addEventListener("click", (ev) => { if (ev.target.id !== "stack-protect") stackFocus(n.dataset.k); }));
  $("stack-protect").addEventListener("click", () => { stackv.hidden = true; $("protect").click(); });
  $("stack-btn").addEventListener("click", () => { stackv.hidden = false; if (stackv.classList.contains("focus")) stackFocus(stackv.querySelector("[data-k].on").dataset.k); });
  $("stack-close").addEventListener("click", () => { stackv.hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") stackv.hidden = true; });
  if (/[?&]view=stack/.test(window.location.search)) stackv.hidden = false;
  const startK = /[?&]capa=(uc|ai|orq|infra|datos|gest|seg|svc)/.exec(window.location.search); if (startK) stackFocus(startK[1]);

  // ---------------------------------------------------------------- conexión a los datos de la planta
  const datav = $("datav");
  function dataFocus(k) {
    const same = datav.querySelector('[data-k="' + k + '"].on');
    datav.querySelectorAll("[data-k]").forEach((n) => n.classList.toggle("on", !same && n.dataset.k === k));
    datav.classList.toggle("focus", !same);
    const show = same ? "intro" : k;
    datav.querySelectorAll(".dv-det section").forEach((sec) => { sec.hidden = sec.dataset.d !== show; });
  }
  datav.querySelectorAll("[data-k]").forEach((n) => n.addEventListener("click", () => dataFocus(n.dataset.k)));
  $("data-btn").addEventListener("click", () => { datav.hidden = false; });
  $("data-close").addEventListener("click", () => { datav.hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") datav.hidden = true; });
  if (/[?&]view=datos/.test(window.location.search)) datav.hidden = false;
  const startVia = /[?&]via=(medallon|rag|mcp|agente)/.exec(window.location.search); if (startVia) dataFocus(startVia[1]);
})();
