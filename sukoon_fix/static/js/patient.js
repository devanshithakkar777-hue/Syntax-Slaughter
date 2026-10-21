/* Sukoon — Patient app controller. */

(() => {
  let user = null;
  let homeData = null;
  let currentGame = null;
  let recognizer = null;

  const views = ["homeView", "routineView", "remindersView", "hydrationView", "mealsView", "medicineView", "journalView", "chatView", "apptView", "moodView", "gamesView", "playView", "helpView", "familyView"];
  function show(viewId) {
    views.forEach((v) => document.getElementById(v).classList.toggle("sk-hidden", v !== viewId));
    window.scrollTo(0, 0);
  }

  function applyI18nAttrs() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = SukoonI18N.t(el.getAttribute("data-i18n"));
    });
  }

  function setLangUI(lang) {
    document.querySelectorAll(".p-lang-btn").forEach((b) => b.classList.toggle("active", b.dataset.lang === lang));
    applyI18nAttrs();
    renderHome();
  }

  async function init() {
    user = skRequireAuth("patient");
    if (!user) return;
    SukoonOffline.init(document.getElementById("offlineBanner"));

    document.getElementById("logoutBtn").addEventListener("click", skLogout);
    document.querySelectorAll(".p-lang-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        SukoonI18N.setLang(btn.dataset.lang);
        setLangUI(btn.dataset.lang);
        try { await SukoonAPI.patch("/api/auth/language", { preferred_language: btn.dataset.lang }); } catch (e) {}
      });
    });
    document.querySelectorAll("[data-back]").forEach((btn) => btn.addEventListener("click", () => show("homeView")));

    document.getElementById("helpFab").addEventListener("click", () => show("helpView"));
    document.getElementById("confirmHelpBtn").addEventListener("click", triggerHelp);
    document.getElementById("familyNavBtn").addEventListener("click", () => navigateTo("familyView"));

    document.querySelectorAll(".p-mood-btn").forEach((btn) => btn.addEventListener("click", () => submitMood(btn.dataset.mood, btn)));

    setupVoice();
    setLangUI(SukoonI18N.getLang());
    await loadHome();
    document.addEventListener("sukoon:synced", loadHome);
  }

  async function loadHome() {
    const grid = document.getElementById("homeGrid");
    try {
      homeData = await SukoonAPI.get("/api/patient/home");
      localStorage.setItem("sukoon_home_cache", JSON.stringify(homeData));
    } catch (e) {
      const cached = localStorage.getItem("sukoon_home_cache");
      if (cached) {
        homeData = JSON.parse(cached);
        skToast(SukoonI18N.t("offline_msg"));
      } else {
        grid.innerHTML = `<div class="sk-empty">${e.message}</div>`;
        return;
      }
    }
    renderHome();
  }

  function renderHome() {
    if (!homeData) return;
    const lang = SukoonI18N.getLang();
    document.getElementById("greeting").innerHTML =
      `${SukoonI18N.t("good_morning")}, ${skEscape(homeData.greeting_name)}!<span class="p-date">${new Date().toLocaleDateString(lang === "as" ? "en-IN" : "en-IN", { weekday: "long", day: "numeric", month: "long" })}</span>`;

    const grid = document.getElementById("homeGrid");
    const nextMed = homeData.next_medicine;
    const hyd = homeData.hydration_progress;
    const meals = homeData.meals_today;
    const mealsDone = meals ? meals.meals.filter((m) => m.done).length : 0;
    const routineProg = homeData.routine_progress;
    const nextAppt = homeData.next_appointment;
    const mood = homeData.mood_today;

    grid.innerHTML = `
      <div class="p-card p-card--purple ${homeData.cognitive_activity_done_today ? "" : "urgent"}">
        <div class="p-card-icon">🧠</div>
        <div class="p-card-title">${SukoonI18N.t("cognitive_activity")}</div>
        <div class="p-card-detail">${homeData.cognitive_activity_done_today ? (lang === "as" ? "আজিৰ কাৰ্যকলাপ সম্পূৰ্ণ হৈছে ✓" : "Completed for today ✓") : (lang === "as" ? "এতিয়াও কৰা হোৱা নাই" : "Not done yet today")}</div>
        <button class="p-card-cta" data-nav="gamesView">${SukoonI18N.t("play_now")}</button>
      </div>

      <div class="p-card p-card--orange">
        <div class="p-card-icon">📅</div>
        <div class="p-card-title">${SukoonI18N.t("today_routine")}</div>
        <div class="p-card-detail">${routineProg.completed} / ${routineProg.total} ${lang === "as" ? "সম্পূৰ্ণ" : "done"}</div>
        <div class="p-progress-bar"><div class="p-progress-fill" style="width:${routineProg.total ? (100 * routineProg.completed / routineProg.total) : 0}%"></div></div>
        <button class="p-card-cta" data-nav="routineView">${SukoonI18N.t("view")}</button>
      </div>

      <div class="p-card p-card--rose ${nextMed ? "urgent" : ""}">
        <div class="p-card-icon">💊</div>
        <div class="p-card-title">${SukoonI18N.t("next_medicine")}</div>
        <div class="p-card-detail">${nextMed ? `${skEscape(lang === "as" ? (nextMed.title_as || nextMed.title_en) : nextMed.title_en)} — ${nextMed.scheduled_time}` : (lang === "as" ? "কোনো বাকী নাই" : "None pending")}</div>
        <button class="p-card-cta" data-nav="medicineView">${SukoonI18N.t("view")}</button>
      </div>

      <div class="p-card p-card--blue">
        <div class="p-card-icon">💧</div>
        <div class="p-card-title">${SukoonI18N.t("hydration")}</div>
        <div class="p-card-detail">${hyd.completed} / ${hyd.total} ${lang === "as" ? "সম্পূৰ্ণ" : "glasses today"}</div>
        <button class="p-card-cta" data-nav="hydrationView">${SukoonI18N.t("view")}</button>
      </div>

      <div class="p-card p-card--orange">
        <div class="p-card-icon">🍽️</div>
        <div class="p-card-title">${lang === "as" ? "আহাৰ" : "Meals"}</div>
        <div class="p-card-detail">${mealsDone} / 3 ${lang === "as" ? "সম্পূৰ্ণ" : "logged today"}</div>
        <button class="p-card-cta" data-nav="mealsView">${SukoonI18N.t("view")}</button>
      </div>

      <div class="p-card p-card--teal">
        <div class="p-card-icon">🩺</div>
        <div class="p-card-title">${SukoonI18N.t("doctor_appointment")}</div>
        <div class="p-card-detail">${nextAppt ? `${skEscape(nextAppt.doctor_name)} — ${nextAppt.date} ${nextAppt.time}` : (lang === "as" ? "কোনো নিৰ্ধাৰিত নাই" : "None scheduled")}</div>
        <button class="p-card-cta" data-nav="apptView">${SukoonI18N.t("view")}</button>
      </div>

      <div class="p-card p-card--pink">
        <div class="p-card-icon">${mood ? moodEmoji(mood.mood) : "🙂"}</div>
        <div class="p-card-title">${SukoonI18N.t("mood")}</div>
        <div class="p-card-detail">${mood ? (lang === "as" ? "আজিৰ বাবে লিখা হৈছে" : "Recorded for today") : (lang === "as" ? "এতিয়াও লিখা হোৱা নাই" : "Not checked in yet")}</div>
        <button class="p-card-cta" data-nav="moodView">${mood ? SukoonI18N.t("view") : SukoonI18N.t("how_are_you_feeling")}</button>
      </div>

      <div class="p-card p-card--purple">
        <div class="p-card-icon">👨‍👩‍👧</div>
        <div class="p-card-title" data-i18n="my_family">My Family</div>
        <div class="p-card-detail">${lang === "as" ? "আপোনাৰ পৰিয়াল আৰু কল কৰক" : "See your family & call someone"}</div>
        <button class="p-card-cta" data-nav="familyView">${lang === "as" ? "খোলক" : "Open"}</button>
      </div>

      <div class="p-card p-card--blue">
        <div class="p-card-icon">📔</div>
        <div class="p-card-title">${lang === "as" ? "মোৰ জাৰ্নেল" : "My Journal"}</div>
        <div class="p-card-detail">${lang === "as" ? "আজিৰ কথা লিখক বা ক'ব পাৰে" : "Write or speak about your day"}</div>
        <button class="p-card-cta" data-nav="journalView">${lang === "as" ? "খোলক" : "Open"}</button>
      </div>

      <div class="p-card p-card--rose">
        <div class="p-card-icon">💬</div>
        <div class="p-card-title">${lang === "as" ? "সংগী চেট" : "Companion Chat"}</div>
        <div class="p-card-detail">${lang === "as" ? "অকলশৰীয়া লাগিলে কথা কওক" : "Someone to talk to if you're feeling lonely"}</div>
        <button class="p-card-cta" data-nav="chatView">${lang === "as" ? "খোলক" : "Open"}</button>
      </div>
    `;
    grid.querySelectorAll("[data-nav]").forEach((btn) => btn.addEventListener("click", () => navigateTo(btn.dataset.nav)));
  }

  function moodEmoji(m) { return { good: "😊", okay: "🙂", unsure: "😐", sad: "🙁" }[m] || "🙂"; }

  function navigateTo(viewId) {
    if (viewId === "routineView") renderRoutine();
    if (viewId === "remindersView") renderReminders();
    if (viewId === "hydrationView") renderHydration();
    if (viewId === "mealsView") renderMeals();
    if (viewId === "medicineView") renderMedicineChecklist();
    if (viewId === "journalView") renderJournal();
    if (viewId === "chatView") renderChat();
    if (viewId === "apptView") renderAppointments();
    if (viewId === "gamesView") renderGamesPicker();
    if (viewId === "familyView") renderFamily();
    if (viewId === "moodView") {
      const sel = homeData.mood_today ? homeData.mood_today.mood : null;
      document.querySelectorAll(".p-mood-btn").forEach((b) => b.classList.toggle("selected", b.dataset.mood === sel));
    }
    show(viewId);
  }

  // ---- Routine -------------------------------------------------------------
  function renderRoutine() {
    const lang = SukoonI18N.getLang();
    const list = document.getElementById("routineList");
    list.innerHTML = "";
    (homeData.today_routine || []).forEach((r) => {
      const card = document.createElement("div");
      card.className = "p-card " + periodAccent(r.period);
      const done = r.status_today === "completed";
      card.innerHTML = `
        <div class="p-card-icon">${periodIcon(r.period)}</div>
        <div class="p-card-title">${skEscape(lang === "as" ? (r.title_as || r.title_en) : r.title_en)}</div>
        <div class="p-card-detail">${r.scheduled_time}</div>
        <button class="p-card-cta" ${done ? "disabled" : ""} style="${done ? "background:var(--sukoon-good);" : ""}">${done ? "✓ " + SukoonI18N.t("completed") : SukoonI18N.t("mark_taken")}</button>
      `;
      if (!done) card.querySelector("button").addEventListener("click", () => completeRoutine(r));
      list.appendChild(card);
    });
  }
  function periodIcon(p) { return { morning: "🌅", afternoon: "☀️", evening: "🌙", custom: "⭐" }[p] || "📅"; }
  function periodAccent(p) { return { morning: "p-card--orange", afternoon: "p-card--blue", evening: "p-card--purple", custom: "p-card--pink" }[p] || "p-card--teal"; }

  async function completeRoutine(r) {
    try {
      if (SukoonOffline.isOnline()) {
        await SukoonAPI.post(`/api/patient/routine/${r.id}/complete`);
      } else {
        SukoonOffline.enqueue("routine_completion", { routine_id: r.id, date: new Date().toISOString().slice(0, 10) });
      }
      r.status_today = "completed";
      renderRoutine();
      const completedNow = homeData.today_routine.filter((x) => x.status_today === "completed").length;
      homeData.routine_progress = { completed: completedNow, total: homeData.today_routine.length };
      skToast("✓ " + SukoonI18N.t("completed"), "good");
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  // ---- Reminders -------------------------------------------------------------
  async function renderReminders() {
    const list = document.getElementById("remindersList");
    list.innerHTML = `<div class="sk-loading">…</div>`;
    let items;
    try {
      items = await SukoonAPI.get("/api/patient/reminders/today");
    } catch (e) {
      items = homeData.reminders_today || [];
    }
    const lang = SukoonI18N.getLang();
    list.innerHTML = "";
    if (!items.length) {
      list.innerHTML = `<div class="sk-empty">${lang === "as" ? "আজিৰ বাবে কোনো ৰিমাইণ্ডাৰ নাই" : "No reminders yet today"}</div>`;
      return;
    }
    items.forEach((r) => {
      const card = document.createElement("div");
      const done = r.status === "completed";
      card.className = "p-card " + kindAccent(r.kind) + (r.status === "escalated" ? " urgent" : "");
      card.innerHTML = `
        <div class="p-card-icon">${kindIcon(r.kind)}</div>
        <div class="p-card-title">${skEscape(lang === "as" ? (r.title_as || r.title_en) : r.title_en)}</div>
        <div class="p-card-detail">${r.scheduled_time} — ${skEscape(statusLabel(r.status, lang))}</div>
        <button class="p-card-cta" ${done ? "disabled" : ""} style="${done ? "background:var(--sukoon-good);" : ""}">${done ? "✓ " + SukoonI18N.t("completed") : SukoonI18N.t("mark_taken")}</button>
      `;
      if (!done) card.querySelector("button").addEventListener("click", () => respondReminder(r, card));
      list.appendChild(card);
    });
  }
  function kindIcon(k) { return { medicine: "💊", hydration: "💧", appointment: "🩺", routine: "📅" }[k] || "🔔"; }
  function kindAccent(k) { return { medicine: "p-card--rose", hydration: "p-card--blue", appointment: "p-card--teal", routine: "p-card--orange" }[k] || "p-card--purple"; }
  function statusLabel(status, lang) {
    const map = {
      pending: { en: "Pending", as: "বাকী আছে" },
      completed: { en: "Completed", as: "সম্পূৰ্ণ" },
      missed: { en: "Missed", as: "মিছ হৈছে" },
      snoozed: { en: "Snoozed", as: "পিছুৱাই দিয়া হৈছে" },
      escalated: { en: "Caregiver notified", as: "যত্নকাৰীক জনোৱা হৈছে" },
    };
    return (map[status] && map[status][lang]) || status;
  }

  async function respondReminder(r, card) {
    try {
      if (SukoonOffline.isOnline()) {
        await SukoonAPI.post(`/api/patient/reminders/${r.id}/respond`, { status: "completed" });
      } else {
        SukoonOffline.enqueue("reminder_response", { response_id: r.id, status: "completed" });
      }
      r.status = "completed";
      renderReminders();
      skToast("✓ " + SukoonI18N.t("completed"), "good");
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  // ---- Hydration (daily glass checklist) ------------------------------------
  let hydrationData = null;

  async function renderHydration() {
    const grid = document.getElementById("hydrationGrid");
    const summary = document.getElementById("hydrationSummary");
    grid.innerHTML = `<div class="sk-loading">…</div>`;
    try {
      hydrationData = await SukoonAPI.get("/api/patient/water-intake");
    } catch (e) {
      hydrationData = homeData.water_intake || { completed: 0, target: 8, glasses: [] };
    }
    paintHydration(summary, grid);
  }

  function paintHydration(summary, grid) {
    const lang = SukoonI18N.getLang();
    const { completed, target, glasses } = hydrationData;
    summary.innerHTML = `
      <div class="p-hydration-count">💧 ${completed} / ${target}</div>
      <div class="p-hydration-caption">${lang === "as" ? "আজি গিলাচ" : "glasses today"}</div>
      <div class="p-hydration-bar"><div class="p-hydration-bar-fill" style="width:${Math.min(100, (completed / target) * 100)}%"></div></div>
      ${completed >= target ? `<div class="p-hydration-goal-met">🎉 ${lang === "as" ? "আজিৰ লক্ষ্য পূৰণ হ'ল!" : "Today's goal reached!"}</div>` : ""}
    `;
    grid.innerHTML = "";
    (glasses || []).forEach((g) => {
      const card = document.createElement("button");
      card.className = "p-glass-card" + (g.done ? " done" : "");
      card.innerHTML = `
        <div class="p-glass-icon">${g.done ? "✅" : "🥛"}</div>
        <div class="p-glass-label">${lang === "as" ? "গিলাচ" : "Glass"} ${g.number}</div>
        <div class="p-glass-status">${g.done ? (lang === "as" ? "সম্পূৰ্ণ" : "done") : (lang === "as" ? "বাকী আছে" : "pending")}</div>
      `;
      // Tapping a pending glass logs the next glass; tapping the most recently
      // completed one undoes it (simple, forgiving tap-to-toggle UX).
      card.addEventListener("click", () => {
        if (!g.done) logWater(); else if (g.number === completed) unlogWater();
      });
      grid.appendChild(card);
    });
  }

  async function logWater() {
    try {
      hydrationData = await SukoonAPI.post("/api/patient/water-intake/log");
      homeData.hydration_progress = { completed: hydrationData.completed, total: hydrationData.target };
      homeData.water_intake = hydrationData;
      paintHydration(document.getElementById("hydrationSummary"), document.getElementById("hydrationGrid"));
      skToast("✓ " + SukoonI18N.t("completed"), "good");
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  async function unlogWater() {
    try {
      hydrationData = await SukoonAPI.post("/api/patient/water-intake/unlog");
      homeData.hydration_progress = { completed: hydrationData.completed, total: hydrationData.target };
      homeData.water_intake = hydrationData;
      paintHydration(document.getElementById("hydrationSummary"), document.getElementById("hydrationGrid"));
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  // ---- Meals (breakfast/lunch/dinner checklist) ------------------------------
  async function renderMeals() {
    const grid = document.getElementById("mealsGrid");
    grid.innerHTML = `<div class="sk-loading">…</div>`;
    let data;
    try {
      data = await SukoonAPI.get("/api/patient/meals");
    } catch (e) {
      data = homeData.meals_today || { meals: [] };
    }
    const lang = SukoonI18N.getLang();
    grid.innerHTML = "";
    (data.meals || []).forEach((m) => {
      const card = document.createElement("button");
      card.className = "p-glass-card" + (m.done ? " done" : "");
      card.innerHTML = `
        <div class="p-glass-icon">${m.done ? "✅" : mealIcon(m.key)}</div>
        <div class="p-glass-label">${skEscape(lang === "as" ? m.label_as : m.label_en)}</div>
        <div class="p-glass-status">${m.done ? (lang === "as" ? "সম্পূৰ্ণ" : "done") : (lang === "as" ? "বাকী আছে" : "pending")}</div>
      `;
      card.addEventListener("click", () => toggleMeal(m.key));
      grid.appendChild(card);
    });
  }
  function mealIcon(k) { return { breakfast: "🌅", lunch: "🍛", dinner: "🌙" }[k] || "🍽️"; }

  async function toggleMeal(key) {
    try {
      const data = await SukoonAPI.post(`/api/patient/meals/${key}/toggle`);
      homeData.meals_today = data;
      renderMeals();
      skToast("✓", "good");
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  // ---- Medicine checklist (name, what it's for, dual sign-off) --------------
  async function renderMedicineChecklist() {
    const list = document.getElementById("medicineList");
    list.innerHTML = `<div class="sk-loading">…</div>`;
    let items;
    try {
      items = await SukoonAPI.get("/api/patient/reminders/today");
    } catch (e) {
      items = homeData.reminders_today || [];
    }
    items = items.filter((r) => r.kind === "medicine");
    const lang = SukoonI18N.getLang();
    list.innerHTML = "";
    if (!items.length) {
      list.innerHTML = `<div class="sk-empty">${lang === "as" ? "আজিৰ বাবে কোনো ঔষধ নাই" : "No medicines due yet today"}</div>`;
      return;
    }
    items.forEach((r) => {
      const card = document.createElement("div");
      const bothDone = r.status === "completed";
      const waitingCaregiver = r.patient_confirmed && !r.caregiver_confirmed;
      card.className = "p-card p-card--rose" + (r.status === "escalated" && !r.patient_confirmed ? " urgent" : "");
      card.innerHTML = `
        <div class="p-card-icon">💊</div>
        <div class="p-card-title">${skEscape(lang === "as" ? (r.title_as || r.title_en) : r.title_en)}</div>
        <div class="p-card-detail">
          ${r.detail ? skEscape(r.detail) + "<br>" : ""}${r.scheduled_time}
          <br><span class="p-medicine-signoff">
            ${r.patient_confirmed ? "✅" : "⬜"} ${lang === "as" ? "ৰোগী" : "Patient"}
            &nbsp;&nbsp;${r.caregiver_confirmed ? "✅" : "⬜"} ${lang === "as" ? "যত্নকাৰী" : "Caregiver"}
          </span>
        </div>
        <button class="p-card-cta" ${r.patient_confirmed ? "disabled" : ""} style="${bothDone ? "background:var(--sukoon-good);" : waitingCaregiver ? "background:#e0a10a;" : ""}">
          ${bothDone ? "✓ " + SukoonI18N.t("completed") : waitingCaregiver ? (lang === "as" ? "যত্নকাৰীৰ প্ৰতীক্ষাত" : "Waiting for caregiver") : SukoonI18N.t("mark_taken")}
        </button>
      `;
      if (!r.patient_confirmed) card.querySelector("button").addEventListener("click", () => confirmMedicineTaken(r));
      list.appendChild(card);
    });
  }

  async function confirmMedicineTaken(r) {
    try {
      const updated = await SukoonAPI.post(`/api/patient/reminders/${r.id}/respond`, { status: "completed" });
      const idx = (homeData.reminders_today || []).findIndex((x) => x.id === r.id);
      if (idx >= 0) homeData.reminders_today[idx] = updated;
      renderMedicineChecklist();
      skToast(updated.status === "completed" ? "✓ " + SukoonI18N.t("completed") : (SukoonI18N.getLang() === "as" ? "যত্নকাৰীৰ প্ৰতীক্ষাত" : "Waiting for caregiver to confirm too"), "good");
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  // ---- Journal -------------------------------------------------------------
  let journalMicRec = null;

  async function renderJournal() {
    const lang = SukoonI18N.getLang();
    const todayBox = document.getElementById("journalTextToday");
    todayBox.value = "…";
    let today = { text: "" }, yesterday = { has_entry: false };
    try {
      [today, yesterday] = await Promise.all([
        SukoonAPI.get("/api/patient/journal/today"),
        SukoonAPI.get("/api/patient/journal/yesterday"),
      ]);
    } catch (e) { skToast(e.message, "critical"); }
    todayBox.value = today.text || "";

    const ytext = document.getElementById("journalYesterdayText");
    const yactions = document.getElementById("journalYesterdayActions");
    if (!yesterday.has_entry) {
      ytext.innerHTML = `<span class="sk-empty">${lang === "as" ? "কালিলৈ কোনো জাৰ্নেল নাই" : "No journal entry from yesterday"}</span>`;
      yactions.innerHTML = "";
    } else {
      ytext.textContent = yesterday.text;
      if (yesterday.remembered === null || yesterday.remembered === undefined) {
        yactions.innerHTML = `
          <button class="sk-btn sk-btn-ghost" id="journalReadBtn" type="button">🔊 ${lang === "as" ? "শুনক" : "Read aloud"}</button>
          <span style="margin-left:10px;">${lang === "as" ? "আপুনি মনত পেলাইছেনে?" : "Do you remember this?"}</span>
          <button class="sk-btn" id="journalYesBtn" type="button">${lang === "as" ? "হয়" : "Yes"}</button>
          <button class="sk-btn sk-btn-ghost" id="journalNoBtn" type="button">${lang === "as" ? "নহয়" : "No"}</button>
        `;
        document.getElementById("journalReadBtn").addEventListener("click", () => SukoonVoice.speak(yesterday.text, lang));
        document.getElementById("journalYesBtn").addEventListener("click", () => recallYesterday(true));
        document.getElementById("journalNoBtn").addEventListener("click", () => recallYesterday(false));
      } else {
        yactions.innerHTML = `
          <button class="sk-btn sk-btn-ghost" id="journalReadBtn" type="button">🔊 ${lang === "as" ? "শুনক" : "Read aloud"}</button>
          <span class="p-journal-remembered">${yesterday.remembered ? "✓ " + (lang === "as" ? "মনত আছে" : "You remembered this") : "○ " + (lang === "as" ? "মনত নাই" : "Not recalled")}</span>
        `;
        document.getElementById("journalReadBtn").addEventListener("click", () => SukoonVoice.speak(yesterday.text, lang));
      }
    }

    document.getElementById("journalSaveBtn").onclick = saveJournalToday;
    const micBtn = document.getElementById("journalMicBtn");
    micBtn.onclick = () => {
      if (!SukoonVoice.sttSupported()) { skToast("Voice input isn't supported in this browser", "critical"); return; }
      micBtn.textContent = "🎙️ …";
      journalMicRec = SukoonVoice.listenOnce(lang, (text) => {
        todayBox.value = (todayBox.value ? todayBox.value + " " : "") + text;
        micBtn.textContent = "🎙️ Speak";
      }, (err) => { skToast("Voice error: " + err, "critical"); micBtn.textContent = "🎙️ Speak"; }, () => { micBtn.textContent = "🎙️ Speak"; });
    };
  }

  async function saveJournalToday() {
    const text = document.getElementById("journalTextToday").value;
    try {
      await SukoonAPI.put("/api/patient/journal/today", { text, recorded_via_voice: false });
      skToast("✓ Journal saved", "good");
    } catch (e) { skToast(e.message, "critical"); }
  }

  async function recallYesterday(remembered) {
    try {
      await SukoonAPI.post("/api/patient/journal/yesterday/recall", { remembered });
      renderJournal();
    } catch (e) { skToast(e.message, "critical"); }
  }

  // ---- Companion Chat -------------------------------------------------------------
  async function renderChat() {
    const box = document.getElementById("chatMessages");
    box.innerHTML = `<div class="sk-loading">…</div>`;
    try {
      const { messages } = await SukoonAPI.get("/api/patient/companion/history");
      box.innerHTML = "";
      if (!messages.length) {
        appendChatBubble("bot", "Hello! I'm here to keep you company. How are you feeling today?");
      } else {
        messages.forEach((m) => appendChatBubble(m.sender, m.text));
      }
    } catch (e) { box.innerHTML = `<div class="sk-empty">${e.message}</div>`; }

    document.getElementById("chatSendBtn").onclick = sendChatMessage;
    document.getElementById("chatInput").onkeydown = (e) => { if (e.key === "Enter") sendChatMessage(); };
    const micBtn = document.getElementById("chatMicBtn");
    micBtn.onclick = () => {
      if (!SukoonVoice.sttSupported()) { skToast("Voice input isn't supported in this browser", "critical"); return; }
      const lang = SukoonI18N.getLang();
      micBtn.textContent = "…";
      SukoonVoice.listenOnce(lang, (text) => {
        document.getElementById("chatInput").value = text;
        micBtn.textContent = "🎙️";
        sendChatMessage();
      }, (err) => { skToast("Voice error: " + err, "critical"); micBtn.textContent = "🎙️"; }, () => { micBtn.textContent = "🎙️"; });
    };
  }

  function appendChatBubble(sender, text) {
    const box = document.getElementById("chatMessages");
    const bubble = document.createElement("div");
    bubble.className = "p-chat-bubble " + (sender === "patient" ? "p-chat-me" : "p-chat-bot");
    bubble.textContent = text;
    box.appendChild(bubble);
    box.scrollTop = box.scrollHeight;
  }

  async function sendChatMessage() {
    const input = document.getElementById("chatInput");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    appendChatBubble("patient", text);
    try {
      const reply = await SukoonAPI.post("/api/patient/companion/send", { text });
      appendChatBubble("bot", reply.text);
      if (SukoonVoice.ttsSupported()) SukoonVoice.speak(reply.text, SukoonI18N.getLang());
    } catch (e) { skToast(e.message, "critical"); }
  }

  // ---- Appointments -------------------------------------------------------------
  async function renderAppointments() {
    const list = document.getElementById("apptList");
    list.innerHTML = `<div class="sk-loading">…</div>`;
    let items = [];
    try { items = await SukoonAPI.get("/api/patient/appointments"); } catch (e) { items = homeData.next_appointment ? [homeData.next_appointment] : []; }
    list.innerHTML = "";
    if (!items.length) { list.innerHTML = `<div class="sk-empty">No appointments scheduled</div>`; return; }
    items.forEach((a) => {
      const card = document.createElement("div");
      card.className = "p-card p-card--teal";
      card.innerHTML = `
        <div class="p-card-icon">🩺</div>
        <div class="p-card-title">${skEscape(a.doctor_name)}</div>
        <div class="p-card-detail">${skEscape(a.hospital_or_clinic || "")}<br>${a.date} · ${a.time}<br>${skEscape(a.location || "")}</div>
      `;
      list.appendChild(card);
    });

    // Past visit notes from the doctor, in plain simple language.
    const notesTitle = document.getElementById("apptNotesTitle");
    const notesList = document.getElementById("apptNotesList");
    notesTitle.classList.add("sk-hidden");
    notesList.innerHTML = "";
    try {
      const records = await SukoonAPI.get("/api/patient/medical-records");
      if (records.length) {
        const lang = SukoonI18N.getLang();
        notesTitle.textContent = lang === "as" ? "চিকিৎসকৰ নোট" : "Doctor's notes from past visits";
        notesTitle.classList.remove("sk-hidden");
        records.forEach((r) => {
          const card = document.createElement("div");
          card.className = "p-card p-card--purple";
          card.innerHTML = `
            <div class="p-card-icon">📋</div>
            <div class="p-card-title">${r.visit_date}</div>
            <div class="p-card-detail"><strong>${lang === "as" ? "নিৰ্ণয়" : "Diagnosis"}:</strong> ${skEscape(r.diagnosis)}${r.follow_up_instructions ? `<br><strong>${lang === "as" ? "পৰৱৰ্তী পদক্ষেপ" : "Follow-up"}:</strong> ${skEscape(r.follow_up_instructions)}` : ""}</div>
          `;
          notesList.appendChild(card);
        });
      }
    } catch (e) { /* medical records are optional context; ignore quietly if unavailable */ }
  }

  // ---- Mood -------------------------------------------------------------
  async function submitMood(mood, btn) {
    document.querySelectorAll(".p-mood-btn").forEach((b) => b.classList.remove("selected"));
    btn.classList.add("selected");
    try {
      if (SukoonOffline.isOnline()) {
        await SukoonAPI.post("/api/patient/mood", { mood });
      } else {
        SukoonOffline.enqueue("mood", { mood, date: new Date().toISOString().slice(0, 10) });
      }
      homeData.mood_today = { mood };
      skToast("✓ " + SukoonI18N.t("completed"), "good");
      setTimeout(() => show("homeView"), 600);
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  // ---- Family tree & call for comfort -------------------------------------------------------------
  let familyContacts = null;
  async function renderFamily() {
    const lang = SukoonI18N.getLang();
    const list = document.getElementById("familyList");
    list.innerHTML = `<div class="sk-loading">…</div>`;
    try {
      familyContacts = await SukoonAPI.get("/api/patient/contacts");
    } catch (e) {
      list.innerHTML = `<div class="sk-empty">${e.message}</div>`;
      return;
    }
    if (!familyContacts.length) {
      list.innerHTML = `<div class="sk-empty">${lang === "as" ? "এতিয়াও কোনো পৰিয়ালৰ সদস্য যোগ কৰা হোৱা নাই" : "No family members added yet — your caregiver or family can add them."}</div>`;
      return;
    }
    list.innerHTML = "";
    familyContacts.forEach((c) => {
      const card = document.createElement("div");
      card.className = "p-card p-card--purple p-family-card";
      const avatar = c.photo_url
        ? `<img src="${c.photo_url}" alt="${skEscape(c.name)}" class="p-family-photo">`
        : `<div class="p-family-photo p-family-photo--initial">${skEscape((c.name || "?")[0])}</div>`;
      card.innerHTML = `
        ${avatar}
        <div class="p-card-title">${skEscape(c.name)}</div>
        <div class="p-card-detail">${skEscape(c.relationship_label || "")}</div>
        <button class="p-card-cta">📞 ${lang === "as" ? "কল কৰক" : "Call"}</button>
      `;
      card.querySelector("button").addEventListener("click", () => callContact(c));
      list.appendChild(card);
    });
  }

  async function callContact(c) {
    const lang = SukoonI18N.getLang();
    try {
      const res = await SukoonAPI.post(`/api/patient/contacts/${c.id}/call`, { reason: "upset" });
      skToast(lang === "as" ? `${res.name}লৈ জনোৱা হৈছে` : `${res.name} has been notified`, "good");
      if (res.phone) {
        window.location.href = "tel:" + res.phone.replace(/\s+/g, "");
      }
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  // ---- Games -------------------------------------------------------------
  const GAME_META = [
    { code: "memory_matching", icon: "🧠", en: "Memory Matching", as: "স্মৃতি মিলোৱা", accent: "p-card--purple" },
    { code: "pattern_recognition", icon: "🔷", en: "Pattern Recognition", as: "আকৃতি চিনাক্তকৰণ", accent: "p-card--blue" },
    { code: "object_recognition", icon: "👁️", en: "Object Recognition", as: "বস্তু চিনাক্তকৰণ", accent: "p-card--teal" },
    { code: "routine_recall", icon: "📅", en: "Daily Routine Recall", as: "দৈনন্দিন কাৰ্যসূচী স্মৰণ", accent: "p-card--orange" },
  ];

  function renderGamesPicker() {
    const lang = SukoonI18N.getLang();
    const list = document.getElementById("gamesList");
    list.innerHTML = "";
    GAME_META.forEach((g) => {
      const card = document.createElement("div");
      card.className = "p-card " + g.accent;
      card.innerHTML = `
        <div class="p-card-icon">${g.icon}</div>
        <div class="p-card-title">${lang === "as" ? g.as : g.en}</div>
        <button class="p-card-cta">${SukoonI18N.t("play_now")}</button>
      `;
      card.querySelector("button").addEventListener("click", () => startGame(g.code));
      list.appendChild(card);
    });
  }

  function startGame(code) {
    currentGame = code;
    const lang = SukoonI18N.getLang();
    const container = document.getElementById("playView");
    show("playView");
    const difficulty = homeData.current_difficulty_level || 2;
    const extra = code === "routine_recall" ? homeData.today_routine : null;
    SukoonGames[code].render(container, difficulty, lang, (result) => onGameComplete(result), extra);
  }

  async function onGameComplete(result) {
    const container = document.getElementById("playView");
    const lang = SukoonI18N.getLang();
    let explanation = lang === "as" ? "আপোনাৰ প্ৰগতি সংৰক্ষিত হৈছে।" : "Great effort! Your progress has been saved.";
    let synced = true;

    const clientId = "sess_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
    try {
      if (SukoonOffline.isOnline()) {
        const perf = await SukoonAPI.post("/api/games/sessions", { ...result, client_generated_id: clientId });
        explanation = lang === "as" ? perf.adaptive_explanation_as : perf.adaptive_explanation_en;
        homeData.current_difficulty_level = perf.new_difficulty;
        homeData.cognitive_activity_done_today = true;
      } else {
        SukoonOffline.enqueue("game_session", { ...result });
        synced = false;
        explanation = SukoonI18N.t("offline_msg");
      }
    } catch (e) {
      SukoonOffline.enqueue("game_session", { ...result });
      synced = false;
      explanation = SukoonI18N.t("offline_msg");
    }

    if (!result.skipped) {
      container.innerHTML = `
        <div class="p-result-banner good">
          🎉 ${lang === "as" ? "সম্পূৰ্ণ হ'ল!" : "Well done!"}
          <div class="p-result-explain">${skEscape(explanation)}</div>
          ${!synced ? `<div class="sk-badge sk-badge-warn" style="margin-top:10px;">${lang === "as" ? "অফলাইনত সংৰক্ষিত" : "Saved offline"}</div>` : ""}
        </div>
        <div style="display:flex; gap:12px;">
          <button class="p-card-cta" id="playAgainBtn" style="flex:1;">${lang === "as" ? "পুনৰ খেলক" : "Play again"}</button>
          <button class="p-back-btn" id="doneBtn" style="flex:1; margin:0;">${lang === "as" ? "ঘৰলৈ যাওক" : "Back to home"}</button>
        </div>
      `;
      container.querySelector("#playAgainBtn").addEventListener("click", () => startGame(currentGame));
      container.querySelector("#doneBtn").addEventListener("click", () => { navigateTo("homeView"); loadHome(); });
    } else {
      navigateTo("homeView");
    }
  }

  // ---- Help -------------------------------------------------------------
  async function triggerHelp() {
    try {
      const res = await SukoonAPI.post("/api/patient/help");
      skToast(res.message || "Caregiver notified", "good");
      show("homeView");
    } catch (e) {
      skToast(e.message, "critical");
    }
  }

  // ---- Voice assistant -------------------------------------------------------------
  function setupVoice() {
    const fab = document.getElementById("voiceFab");
    const panel = document.getElementById("voicePanel");
    if (!SukoonVoice.sttSupported()) {
      fab.title = "Voice input not supported in this browser — tap to hear today's summary";
    }
    fab.addEventListener("click", () => {
      const lang = SukoonI18N.getLang();
      if (!SukoonVoice.sttSupported()) {
        speakSummary(lang);
        return;
      }
      fab.classList.add("listening");
      panel.classList.remove("sk-hidden");
      panel.textContent = lang === "as" ? "শুনি আছোঁ..." : "Listening…";
      recognizer = SukoonVoice.listenOnce(
        lang,
        (text) => { panel.textContent = `"${text}"`; handleVoiceCommand(text.toLowerCase(), lang); },
        (err) => { panel.textContent = "Could not hear that — please try again."; },
        () => { fab.classList.remove("listening"); setTimeout(() => panel.classList.add("sk-hidden"), 3500); }
      );
    });
  }

  function speakSummary(lang) {
    const text = summaryText(lang);
    document.getElementById("voicePanel").classList.remove("sk-hidden");
    document.getElementById("voicePanel").textContent = text;
    SukoonVoice.speak(text, lang);
    setTimeout(() => document.getElementById("voicePanel").classList.add("sk-hidden"), 5000);
  }

  function summaryText(lang) {
    const nextMed = homeData.next_medicine;
    if (lang === "as") {
      return nextMed ? `আজি আপোনাৰ কাৰ্যসূচী আৰু ${nextMed.scheduled_time} বজাত ঔষধ আছে।` : "আজি আপোনাৰ কাৰ্যসূচী আছে।";
    }
    return nextMed
      ? `Today you have your routine, and medicine at ${nextMed.scheduled_time}.`
      : "Today you have your routine activities. No medicine reminders are pending right now.";
  }

  function handleVoiceCommand(text, lang) {
    const panel = document.getElementById("voicePanel");
    let response;
    if (text.includes("medicine") || text.includes("ঔষধ")) {
      const nextMed = homeData.next_medicine;
      response = nextMed
        ? (lang === "as" ? `আপোনাৰ পৰৱৰ্তী ঔষধ ৰিমাইণ্ডাৰ ${nextMed.scheduled_time} বজাত।` : `Your next medicine reminder is at ${nextMed.scheduled_time}.`)
        : (lang === "as" ? "এতিয়া কোনো ঔষধ বাকী নাই।" : "You have no medicine reminders pending right now.");
    } else if (text.includes("today") || text.includes("routine") || text.includes("আজি")) {
      response = summaryText(lang);
    } else if (text.includes("help") || text.includes("emergency") || text.includes("sos") || text.includes("সহায়")) {
      response = lang === "as" ? "আপোনাৰ যত্নকাৰীক জনোৱা হ'ব।" : "I will notify your caregiver now.";
      triggerHelp();
    } else {
      response = lang === "as"
        ? "মই আজিৰ কাৰ্যসূচী বা ঔষধৰ বিষয়ে সহায় কৰিব পাৰোঁ।"
        : "I can tell you about today's routine or your next medicine. Try asking 'What do I have to do today?'";
    }
    panel.textContent = response;
    SukoonVoice.speak(response, lang);
  }

  document.addEventListener("DOMContentLoaded", init);

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/app/service-worker.js", { scope: "/app/" }).catch(() => {}));
  }
})();
