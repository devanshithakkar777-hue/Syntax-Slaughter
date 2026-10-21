/* Sukoon — Pattern Recognition game.
   Show a short repeating sequence of familiar objects, ask what comes next. */

window.SukoonGames.pattern_recognition = {
  render(container, difficulty, lang, onComplete) {
    const totalRounds = 5;
    const unitLen = difficulty <= 2 ? 2 : (difficulty <= 4 ? 3 : 4);
    const numChoices = Math.min(3 + Math.floor(difficulty / 2), 5);

    let round = 0, attempts = 0, correct = 0, responseTimes = [];
    let roundStart = null;

    container.innerHTML = `
      <div class="p-section-title" style="padding:0 0 4px;">🔷 ${lang === "as" ? "আকৃতি চিনাক্তকৰণ" : "Pattern Recognition"}</div>
      <p style="color:var(--sukoon-ink-500); font-size:1rem;" id="roundLabel"></p>
      <div id="sequenceRow" style="display:flex; gap:10px; flex-wrap:wrap; justify-content:center; margin:20px 0;"></div>
      <div class="p-choice-row" id="choiceRow"></div>
    `;
    const seqRow = container.querySelector("#sequenceRow");
    const choiceRow = container.querySelector("#choiceRow");
    const roundLabel = container.querySelector("#roundLabel");

    nextRound();

    function nextRound() {
      round++;
      if (round > totalRounds) return finish();
      roundLabel.textContent = (lang === "as" ? "ৰাউণ্ড" : "Round") + ` ${round} / ${totalRounds}`;

      const unitObjects = skPickObjects(unitLen);
      const seqLen = unitLen * 2 + (Math.random() > 0.5 ? 1 : 0);
      const sequence = [];
      for (let i = 0; i < seqLen; i++) sequence.push(unitObjects[i % unitLen]);
      const answer = unitObjects[seqLen % unitLen];

      seqRow.innerHTML = "";
      sequence.forEach((obj) => {
        const tile = document.createElement("div");
        tile.className = "p-tile";
        tile.style.width = "64px";
        tile.style.fontSize = "2rem";
        tile.textContent = obj.emoji;
        seqRow.appendChild(tile);
      });
      const q = document.createElement("div");
      q.className = "p-tile";
      q.style.width = "64px";
      q.style.fontSize = "2rem";
      q.style.borderStyle = "dashed";
      q.textContent = "?";
      seqRow.appendChild(q);

      let choiceObjects = skPickObjects(numChoices).filter((o) => o.code !== answer.code);
      choiceObjects = choiceObjects.slice(0, numChoices - 1);
      choiceObjects.push(answer);
      for (let i = choiceObjects.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [choiceObjects[i], choiceObjects[j]] = [choiceObjects[j], choiceObjects[i]];
      }

      choiceRow.innerHTML = "";
      choiceObjects.forEach((obj) => {
        const btn = document.createElement("button");
        btn.className = "p-choice-btn";
        btn.textContent = obj.emoji;
        btn.addEventListener("click", () => pick(obj, answer, btn));
        choiceRow.appendChild(btn);
      });

      roundStart = Date.now();
    }

    function pick(chosen, answer, btn) {
      Array.from(choiceRow.children).forEach((b) => (b.disabled = true));
      attempts++;
      const elapsed = Date.now() - roundStart;
      responseTimes.push(elapsed);
      if (chosen.code === answer.code) {
        correct++;
        btn.classList.add("p-tile-correct");
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
        activity_code: "pattern_recognition",
        difficulty, score: Math.round(accuracy * 100), accuracy: Math.round(accuracy * 100) / 100,
        attempts, correct_attempts: correct, avg_response_time_ms: avgMs,
      });
    }
  },
};
