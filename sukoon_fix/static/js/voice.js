/* Sukoon — voice assistance layer (Web Speech API).
   Provides text-to-speech (both English and, where the browser/OS exposes an
   Assamese voice, Assamese) and speech-to-text where the browser supports it.
   Command *understanding* lives in patient.js — this module only wraps the
   browser APIs, so a future Assamese ASR/TTS engine can be dropped in here
   without touching any calling code. */

const SukoonVoice = (() => {
  const synth = window.speechSynthesis;
  const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;

  function speak(text, lang) {
    if (!synth) return;
    synth.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = lang === "as" ? "as-IN" : "en-IN";
    utter.rate = 0.95;
    const voices = synth.getVoices();
    const match = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(utter.lang.toLowerCase()));
    if (match) utter.voice = match;
    else if (lang === "as") {
      // Most browsers/OSes don't ship an Assamese TTS voice yet; fall back to
      // a generic Indian-English voice rather than staying silent, and say so.
      utter.lang = "en-IN";
    }
    synth.speak(utter);
  }

  function sttSupported() { return !!RecognitionCtor; }
  function ttsSupported() { return !!synth; }

  /* Read-aloud for the caregiver / doctor / family dashboards: a small
     floating button that reads whatever is currently in `container` (its
     live text content at click time, so it stays correct across tab
     switches without any caller bookkeeping). Idempotent — safe to call
     once per page during init. */
  function attachReadAloud(container, opts) {
    if (!container || !ttsSupported()) return null;
    if (document.querySelector(".sk-voice-fab")) return null; // already mounted
    opts = opts || {};
    const btn = document.createElement("button");
    btn.className = "sk-voice-fab";
    btn.type = "button";
    btn.title = "Read this page aloud";
    btn.innerHTML = "🔊";
    document.body.appendChild(btn);

    let speaking = false;
    const reset = () => { speaking = false; btn.innerHTML = "🔊"; btn.classList.remove("speaking"); };

    btn.addEventListener("click", () => {
      if (speaking) { synth.cancel(); reset(); return; }
      const raw = (typeof opts.getText === "function" ? opts.getText() : container.innerText) || "";
      const text = raw.replace(/\s+/g, " ").trim();
      if (!text) return;
      speaking = true;
      btn.innerHTML = "⏹";
      btn.classList.add("speaking");
      synth.cancel();
      const utter = new SpeechSynthesisUtterance(text.slice(0, 4000));
      utter.lang = opts.lang === "as" ? "as-IN" : "en-IN";
      utter.rate = 0.95;
      utter.onend = reset;
      utter.onerror = reset;
      synth.speak(utter);
    });
    return btn;
  }

  function listenOnce(lang, onResult, onError, onEnd) {
    if (!RecognitionCtor) {
      onError && onError("Speech recognition is not supported in this browser.");
      return null;
    }
    const rec = new RecognitionCtor();
    rec.lang = lang === "as" ? "as-IN" : "en-IN";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      const text = event.results[0][0].transcript;
      onResult && onResult(text);
    };
    rec.onerror = (event) => { onError && onError(event.error); };
    rec.onend = () => { onEnd && onEnd(); };
    rec.start();
    return rec;
  }

  return { speak, sttSupported, ttsSupported, listenOnce, attachReadAloud };
})();
