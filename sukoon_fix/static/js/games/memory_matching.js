/* Sukoon — Memory Matching game.
   Show familiar objects, hide them, ask the patient to find matching pairs.
   Records score / accuracy / attempts / response time for the adaptive engine. */

window.SukoonGames.memory_matching = {
  render(container, difficulty, lang, onComplete) {
    const pairCount = Math.min(3 + Math.max(1, difficulty), 8);
    const objects = skPickObjects(pairCount);
    let deck = [];
    objects.forEach((o, i) => {
      deck.push({ ...o, uid: i + "a" });
      deck.push({ ...o, uid: i + "b" });
    });
    // shuffle
    for (let i = deck.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [deck[i], deck[j]] = [deck[j], deck[i]];
    }

    let attempts = 0, correct = 0, responseTimes = [];
    let firstPick = null, lock = false, matchedCount = 0;
    let attemptStart = null;
    let previewing = true;

    container.innerHTML = `
      <div class="p-section-title" style="padding:0 0 4px;">🧠 ${lang === "as" ? "স্মৃতি মিলোৱা" : "Memory Matching"}</div>
      <p style="color:var(--sukoon-ink-500); font-size:1rem;">${lang === "as" ? "প্ৰথমে বস্তুবোৰ মনত ৰাখক..." : "First, remember where each object is..."}</p>
      <div class="p-game-board" id="board" style="grid-template-columns: repeat(${Math.min(4, pairCount)}, 1fr);"></div>
    `;
    const board = container.querySelector("#board");
    const tiles = deck.map((card) => {
      const tile = document.createElement("div");
      tile.className = "p-tile";
      tile.textContent = card.emoji;
      tile.dataset.uid = card.uid;
      tile.dataset.code = card.code;
      board.appendChild(tile);
      return tile;
    });

    // Preview phase: show all face up briefly, then flip down.
    setTimeout(() => {
      previewing = false;
      tiles.forEach((t) => t.classList.add("face-down", "selectable"));
      attemptStart = Date.now();
      tiles.forEach((tile) => tile.addEventListener("click", () => handlePick(tile)));
    }, 1800 + pairCount * 500);

    function handlePick(tile) {
      if (previewing || lock || tile.classList.contains("correct") || tile === firstPick) return;
      reveal(tile);

      if (!firstPick) {
        firstPick = tile;
        return;
      }

      attempts++;
      lock = true;
      const isMatch = firstPick.dataset.code === tile.dataset.code;
      const elapsed = Date.now() - attemptStart;
      responseTimes.push(elapsed);

      setTimeout(() => {
        if (isMatch) {
          correct++;
          firstPick.classList.add("correct");
          tile.classList.add("correct");
          matchedCount++;
        } else {
          hide(firstPick);
          hide(tile);
        }
        firstPick = null;
        lock = false;
        attemptStart = Date.now();

        if (matchedCount === pairCount) finish();
      }, isMatch ? 350 : 750);
    }

    function reveal(tile) {
      tile.classList.remove("face-down");
      tile.textContent = tile.dataset.code ? SukoonObjects.find(o => o.code === tile.dataset.code).emoji : tile.textContent;
    }
    function hide(tile) {
      tile.classList.add("face-down");
    }

    function finish() {
      const accuracy = attempts > 0 ? Math.min(1, correct / attempts) : 0;
      const avgMs = responseTimes.length ? Math.round(responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length) : 0;
      const score = Math.round(accuracy * 100);
      onComplete({
        activity_code: "memory_matching",
        difficulty, score, accuracy: Math.round(accuracy * 100) / 100,
        attempts, correct_attempts: correct, avg_response_time_ms: avgMs,
      });
    }
  },
};
