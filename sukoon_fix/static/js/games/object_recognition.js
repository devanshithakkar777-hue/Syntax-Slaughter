/* Sukoon — Object Recognition game.
   The name of a familiar object is shown (and spoken, where supported);
   the patient taps the matching picture among a few options. */

window.SukoonGames.object_recognition = {
  render(container, difficulty, lang, onComplete) {
    const totalRounds = 6;
    const numChoices = Math.min(3 + Math.floor(difficulty / 2), 6);

    let round = 0, attempts = 0, correct = 0, responseTimes = [];
    let roundStart = null;

    container.innerHTML = `
      <div class="p-section-title" style="padding:0 0 4px;">👁️ ${lang === "as" ? "বস্তু চিনাক্তকৰণ" : "Object Recognition"}</div>
      <p style="color:var(--sukoon-ink-500); font-size:1rem;" id="roundLabel"></p>
      <div style="text-align:center; margin:18px 0;">
        <div style="font-size:1.6rem; font-weight:800; color:var(--sukoon-teal-800, var(--sukoon-teal-700));" id="targetName"></div>
        <div style="font-size:0.9rem; color:var(--sukoon-ink-500);">${lang === "as" ? "মিলা ছবিখন বাছি উলিয়াওক" : "Tap the matching picture"}</div>
      </div>
      <div class="p-choice-row" id="choiceRow"></div>
    `;
    const choiceRow = container.querySelector("#choiceRow");
    const roundLabel = container.querySelector("#roundLabel");
    const targetName = container.querySelector("#targetName");

    nextRound();

    function nextRound() {
      round++;
      if (round > totalRounds) return finish();
      roundLabel.textContent = (lang === "as" ? "ৰাউণ্ড" : "Round") + ` ${round} / ${totalRounds}`;

      const options = skPickObjects(numChoices);
      const answer = options[Math.floor(Math.random() * options.length)];
      targetName.textContent = lang === "as" ? answer.as : answer.en;

      if (typeof SukoonVoice !== "undefined" && SukoonVoice.ttsSupported()) {
        SukoonVoice.speak(lang === "as" ? answer.as : answer.en, lang);
      }

      choiceRow.innerHTML = "";
      options.forEach((obj) => {
        const btn = document.createElement("button");
        btn.className = "p-choice-btn";
        btn.textContent = obj.emoji;
        btn.style.fontSize = "2.4rem";
        btn.addEventListener("click", () => pick(obj, answer, btn));
        choiceRow.appendChild(btn);
      });

      roundStart = Date.now();
    }

    function pick(chosen, answer, btn) {
      Array.from(choiceRow.children).forEach((b) => (b.disabled = true));
      attempts++;
      responseTimes.push(Date.now() - roundStart);
      if (chosen.code === answer.code) {
        correct++;
        btn.style.background = "#e5f5ea";
        btn.style.borderColor = "var(--sukoon-good)";
      } else {
        btn.style.background = "#fbe7e4";
        btn.style.borderColor = "var(--sukoon-critical)";
      }
      setTimeout(nextRound, 650);
    }

    function finish() {
      const accuracy = attempts > 0 ? correct / attempts : 0;
      const avgMs = responseTimes.length ? Math.round(responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length) : 0;
      onComplete({
        activity_code: "object_recognition",
        difficulty, score: Math.round(accuracy * 100), accuracy: Math.round(accuracy * 100) / 100,
        attempts, correct_attempts: correct, avg_response_time_ms: avgMs,
      });
    }
  },
};
