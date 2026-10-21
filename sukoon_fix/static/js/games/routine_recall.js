/* Sukoon — Daily Routine Recall game.
   Uses the patient's OWN configured routine (set by their caregiver) to ask
   simple "what comes after X?" multiple-choice questions. Falls back
   gracefully if fewer than two routine items are configured. */

const SUKOON_ROUTINE_DISTRACTORS = [
  { en: "Go to the market", as: "বজাৰলৈ যোৱা" },
  { en: "Watch television", as: "দূৰদৰ্শন চোৱা" },
  { en: "Write a letter", as: "চিঠি লিখা" },
  { en: "Feed the cattle", as: "গৰুক আহাৰ দিয়া" },
  { en: "Visit the temple", as: "মন্দিৰলৈ যোৱা" },
];

window.SukoonGames.routine_recall = {
  render(container, difficulty, lang, onComplete, extra) {
    const routines = ((extra && extra.length ? extra : []) || [])
      .slice()
      .sort((a, b) => a.scheduled_time.localeCompare(b.scheduled_time));

    if (routines.length < 2) {
      container.innerHTML = `<div class="sk-empty">${lang === "as" ? "যথেষ্ট কাৰ্যসূচী কনফিগাৰ কৰা হোৱা নাই।" : "Not enough routine items are configured yet to play this activity."}</div>`;
      setTimeout(() => onComplete({ activity_code: "routine_recall", difficulty, score: 0, accuracy: 0, attempts: 0, correct_attempts: 0, avg_response_time_ms: 0, skipped: true }), 1200);
      return;
    }

    const totalRounds = Math.min(routines.length - 1, 4);
    let round = 0, attempts = 0, correct = 0, responseTimes = [];
    let roundStart = null;
    const order = [...Array(routines.length - 1).keys()];
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }

    container.innerHTML = `
      <div class="p-section-title" style="padding:0 0 4px;">📅 ${lang === "as" ? "দৈনন্দিন কাৰ্যসূচী স্মৰণ" : "Daily Routine Recall"}</div>
      <p style="color:var(--sukoon-ink-500); font-size:1rem;" id="roundLabel"></p>
      <div style="text-align:center; margin:18px 0; font-size:1.25rem; font-weight:700; color:var(--sukoon-teal-900);" id="question"></div>
      <div class="p-choice-row" id="choiceRow" style="grid-template-columns: 1fr;"></div>
    `;
    const choiceRow = container.querySelector("#choiceRow");
    const roundLabel = container.querySelector("#roundLabel");
    const question = container.querySelector("#question");

    nextRound();

    function nextRound() {
      if (round >= totalRounds) return finish();
      const idx = order[round];
      round++;
      roundLabel.textContent = (lang === "as" ? "ৰাউণ্ড" : "Round") + ` ${round} / ${totalRounds}`;

      const current = routines[idx];
      const next = routines[idx + 1];
      const currentTitle = lang === "as" ? (current.title_as || current.title_en) : current.title_en;
      const answerTitle = lang === "as" ? (next.title_as || next.title_en) : next.title_en;

      question.textContent = lang === "as"
        ? `"${currentTitle}"ৰ পিছত আপুনি সাধাৰণতে কি কৰে?`
        : `What do you usually do after "${currentTitle}"?`;

      const distractorPool = SUKOON_ROUTINE_DISTRACTORS.filter((d) => (lang === "as" ? d.as : d.en) !== answerTitle);
      const shuffledDistractors = distractorPool.sort(() => Math.random() - 0.5).slice(0, 2);
      const options = [answerTitle, ...shuffledDistractors.map((d) => (lang === "as" ? d.as : d.en))];
      options.sort(() => Math.random() - 0.5);

      choiceRow.innerHTML = "";
      options.forEach((opt) => {
        const btn = document.createElement("button");
        btn.className = "p-choice-btn";
        btn.style.fontSize = "1.15rem";
        btn.textContent = opt;
        btn.addEventListener("click", () => pick(opt, answerTitle, btn));
        choiceRow.appendChild(btn);
      });

      roundStart = Date.now();
    }

    function pick(chosen, answer, btn) {
      Array.from(choiceRow.children).forEach((b) => (b.disabled = true));
      attempts++;
      responseTimes.push(Date.now() - roundStart);
      if (chosen === answer) {
        correct++;
        btn.style.background = "#e5f5ea";
        btn.style.borderColor = "var(--sukoon-good)";
      } else {
        btn.style.background = "#fbe7e4";
        btn.style.borderColor = "var(--sukoon-critical)";
      }
      setTimeout(nextRound, 700);
    }

    function finish() {
      const accuracy = attempts > 0 ? correct / attempts : 0;
      const avgMs = responseTimes.length ? Math.round(responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length) : 0;
      onComplete({
        activity_code: "routine_recall",
        difficulty, score: Math.round(accuracy * 100), accuracy: Math.round(accuracy * 100) / 100,
        attempts, correct_attempts: correct, avg_response_time_ms: avgMs,
      });
    }
  },
};
