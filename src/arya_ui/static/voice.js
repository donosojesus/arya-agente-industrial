/* Voz de ARYA: lee en voz alta sus respuestas con una voz LOCAL del sistema operativo
   (en Windows: Microsoft Helena, Laura o Pablo, español). Nunca usa voces que requieran
   Internet: si no hay una voz local en español, el boton queda desactivado y lo indica. */
(function () {
  "use strict";
  const btn = document.getElementById("voice");
  if (!btn) return;
  const synth = window.speechSynthesis;
  let voice = null, enabled = false;
  const PREFERRED = ["pablo", "laura", "helena", "sabina", "raul"];

  function pickVoice() {
    if (!synth) return null;
    const local = synth.getVoices().filter((v) => v.localService && /^es(-|_|$)/i.test(v.lang));
    for (const name of PREFERRED) { const v = local.find((x) => x.name.toLowerCase().includes(name)); if (v) return v; }
    return local[0] || null;
  }
  function render() {
    btn.disabled = !voice;
    btn.dataset.on = String(enabled && !!voice);
    btn.textContent = !voice ? "VOZ · NO DISPONIBLE" : (enabled ? "VOZ · ACTIVADA" : "VOZ · APAGADA");
    btn.title = voice ? "Voz local: " + voice.name : "No hay una voz local en español en este equipo";
  }
  function refresh() { voice = pickVoice(); render(); }
  if (synth) { synth.onvoiceschanged = refresh; }
  refresh(); setTimeout(refresh, 1500);
  try { enabled = sessionStorage.getItem("arya-voice") === "1"; } catch (e) { /* sin almacenamiento */ }
  render();

  btn.addEventListener("click", () => {
    enabled = !enabled;
    try { sessionStorage.setItem("arya-voice", enabled ? "1" : "0"); } catch (e) { /* sin almacenamiento */ }
    if (!enabled && synth) synth.cancel();
    render();
  });

  // Forma hablada: unidades y codigos legibles.
  function spoken(text) {
    return text
      .replace(/m³\/h/g, " metros cúbicos por hora").replace(/mm\/s/g, " milímetros por segundo")
      .replace(/°\s?C/g, " grados").replace(/\brpm\b/gi, " revoluciones por minuto").replace(/(\d)\s?A\b/g, "$1 amperes")
      .replace(/\bbar\b/g, " bar").replace(/\bP-101\b/g, "P ciento uno").replace(/\bWO-DRAFT-(\d+)/g, "borrador $1")
      .replace(/\bWO-(\d{4})-(\d{4})/g, "orden $1 $2").replace(/(\d)\.(\d)/g, "$1 coma $2");
  }
  window.AryaVoice = {
    say(text, onStart, onEnd) {
      if (!enabled || !voice || !synth || !text) return false;
      synth.cancel();
      const u = new SpeechSynthesisUtterance(spoken(text));
      u.voice = voice; u.lang = voice.lang; u.rate = 1.05;
      u.onstart = () => onStart && onStart();
      u.onend = u.onerror = () => onEnd && onEnd();
      synth.speak(u);
      return true;
    },
    stop() { if (synth) synth.cancel(); },
  };
})();
