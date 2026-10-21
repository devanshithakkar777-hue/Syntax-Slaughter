/* Sukoon — Caregiver dashboard controller. */

(() => {
  let user = null;
  let patients = [];
  let selectedPatientId = null;
  let dashboard = null;
  let activeTab = "overview";
  let chartInstance = null;
  let safetyMap = null;
  let safetyMapLayers = { circle: null, patientMarker: null, homeMarker: null };

  const DOMAIN_BY_ACTIVITY = {
    memory_matching: "memory",
    pattern_recognition: "attention",
    object_recognition: "recognition",
    routine_recall: "engagement",
  };
  const DOMAIN_COLORS = { memory: "#1f9d8a", attention: "#c98a1f", recognition: "#2f6fb0", engagement: "#8e5fc9" };
  const MOOD_ICON = { good: "😊", okay: "🙂", unsure: "😐", sad: "🙁" };

  const content = () => document.getElementById("tabContent");

  async function init() {
    user = skRequireAuth("caregiver");
    if (!user) return;
    document.getElementById("cgUserName").textContent = user.full_name;
    document.getElementById("logoutBtn").addEventListener("click", skLogout);
    document.querySelectorAll(".sk-tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
    if (typeof SukoonVoice !== "undefined") SukoonVoice.attachReadAloud(content());

    try {
      patients = await SukoonAPI.get("/api/caregiver/patients");
    } catch (e) {
      content().innerHTML = `<div class="sk-empty">${e.message}</div>`;
      return;
    }
    renderPatientList();
    if (patients.length) selectPatient(patients[0].id);
    else content().innerHTML = `<div class="sk-empty">No patients are linked to your account yet.</div>`;
  }

  function renderPatientList() {
    const list = document.getElementById("patientList");
    list.innerHTML = "";
    patients.forEach((p) => {
      const el = document.createElement("div");
      el.className = "cg-patient-item" + (p.id === selectedPatientId ? " active" : "");
      el.innerHTML = `
        <div class="cg-patient-avatar">${skEscape((p.full_name || "?")[0])}</div>
        <div>
          <div class="cg-patient-name">${skEscape(p.full_name)}</div>
          <div class="cg-patient-sub">${p.age ? p.age + " yrs · " : ""}${skEscape(p.home_region || "")}</div>
          ${p.open_alerts ? `<span class="sk-badge sk-badge-warn" style="margin-top:4px;">${p.open_alerts} alert${p.open_alerts > 1 ? "s" : ""}</span>` : ""}
        </div>
      `;
      el.addEventListener("click", () => selectPatient(p.id));
      list.appendChild(el);
    });
  }

  async function selectPatient(id) {
    selectedPatientId = id;
    renderPatientList();
    content().innerHTML = `<div class="sk-loading">Loading dashboard…</div>`;
    try {
      dashboard = await SukoonAPI.get(`/api/caregiver/patients/${id}/dashboard`);
    } catch (e) {
      content().innerHTML = `<div class="sk-empty">${e.message}</div>`;
      return;
    }
    switchTab("overview");
  }

  function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll(".sk-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
    const renderers = {
      overview: renderOverview, agents: renderAgents, medicines: renderMedicines, reminders: renderReminders, routines: renderRoutines,
      appointments: renderAppointments, contacts: renderContacts, doctors: renderDoctors, safety: renderSafety, alerts: renderAlerts,
    };
    renderers[tab]();
  }

  function patientHeader() {
    const p = dashboard.patient;
    return `
      <div class="sk-card" style="margin-bottom:18px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px;">
          <div>
            <div style="font-size:1.3rem; font-weight:800; color:var(--sukoon-teal-900);">${skEscape(p.full_name)}</div>
            <div style="color:var(--sukoon-ink-500); font-size:0.88rem;">${p.age ? p.age + " years · " : ""}${skEscape(p.gender || "")} · ${skEscape(p.home_region || "")}</div>
            <div style="color:var(--sukoon-ink-500); font-size:0.82rem; margin-top:4px;">${skEscape(p.condition_notes || "")}</div>
          </div>
          <span class="sk-badge sk-badge-info">Difficulty level ${p.current_difficulty_level}/5</span>
        </div>
      </div>
    `;
  }

  // ---- Overview -------------------------------------------------------------
  function renderOverview() {
    const perf = dashboard.performance_30d || [];
    const latestInsight = perf.length ? perf[perf.length - 1] : null;
    const alerts = (dashboard.alerts || []).filter((a) => !a.acknowledged);

    content().innerHTML = `
      ${patientHeader()}
      ${alerts.length ? `<div class="sk-card" style="margin-bottom:18px; border-color:#f4c7c1;">
        <strong style="color:var(--sukoon-critical);">⚠ ${alerts.length} unresolved alert${alerts.length > 1 ? "s" : ""}</strong>
        <div style="margin-top:8px; font-size:0.88rem;">${skEscape(alerts[0].message_en)}</div>
      </div>` : ""}
      <div class="sk-grid sk-grid-2" style="margin-bottom:18px;">
        <div class="sk-card">
          <h3 style="margin:0 0 10px; font-size:0.95rem;">Cognitive trend (30 days, average accuracy by domain)</h3>
          <div class="chart-wrap"><canvas id="perfChart"></canvas></div>
        </div>
        <div class="sk-card">
          <h3 style="margin:0 0 10px; font-size:0.95rem;">Mood (last 14 check-ins)</h3>
          <div id="moodTrend" style="display:flex; gap:6px; flex-wrap:wrap;"></div>
        </div>
      </div>
      ${latestInsight ? `<div class="sk-disclaimer" style="margin-bottom:18px;">
        <strong>AI-assisted activity insight — not a medical diagnosis.</strong><br>${skEscape(latestInsight.adaptive_explanation_en)}
      </div>` : ""}
      <div class="sk-grid sk-grid-3">
        <div class="sk-card"><strong>Reminder adherence</strong><div style="margin-top:6px; color:var(--sukoon-ink-500); font-size:0.85rem;">See the Reminders tab for full log.</div></div>
        <div class="sk-card"><strong>Wearable</strong><div style="margin-top:6px; font-size:0.85rem;">${dashboard.wearable_latest ? `❤️ ${dashboard.wearable_latest.heart_rate_bpm} bpm · 👣 ${dashboard.wearable_latest.steps} steps <span class="sk-badge sk-badge-demo">Demo Data</span>` : "No data yet"}</div></div>
        <div class="sk-card"><strong>Location</strong><div style="margin-top:6px; font-size:0.85rem;">${dashboard.location_latest ? (dashboard.location_latest.within_safe_zone ? "✅ Within safe zone" : "⚠️ Outside safe zone") : "Not enabled"}</div></div>
      </div>
    `;

    renderPerfChart(perf);
    renderMoodTrend(dashboard.mood_30d || []);
  }

  function renderPerfChart(perf) {
    const canvas = document.getElementById("perfChart");
    if (!canvas || typeof Chart === "undefined") return;
    const byDate = {};
    perf.forEach((r) => {
      const date = (r.timestamp || "").slice(0, 10);
      const domain = DOMAIN_BY_ACTIVITY[r.activity_code] || "other";
      byDate[date] = byDate[date] || {};
      byDate[date][domain] = byDate[date][domain] || [];
      byDate[date][domain].push(r.accuracy);
    });
    const dates = Object.keys(byDate).sort();
    const domains = ["memory", "attention", "recognition", "engagement"];
    const datasets = domains.map((d) => ({
      label: d.charAt(0).toUpperCase() + d.slice(1),
      data: dates.map((date) => {
        const vals = (byDate[date] || {})[d];
        return vals ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) : null;
      }),
      borderColor: DOMAIN_COLORS[d],
      backgroundColor: DOMAIN_COLORS[d],
      spanGaps: true,
      tension: 0.3,
    }));

    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(canvas, {
      type: "line",
      data: { labels: dates.map((d) => d.slice(5)), datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } } },
        plugins: { legend: { position: "bottom" } },
      },
    });
  }

  function renderMoodTrend(moods) {
    const wrap = document.getElementById("moodTrend");
    if (!wrap) return;
    if (!moods.length) { wrap.innerHTML = `<span class="sk-empty">No mood check-ins yet</span>`; return; }
    wrap.innerHTML = moods.slice(-14).map((m) => `
      <div style="text-align:center; font-size:0.7rem; color:var(--sukoon-ink-500);">
        <div style="font-size:1.6rem;">${MOOD_ICON[m.mood] || "🙂"}</div>${m.date.slice(5)}
      </div>
    `).join("");
  }

  // ---- Medicines (dual sign-off checklist, mirrors the patient app) --------
  // ---- AI Care Agent Network -------------------------------------------
  async function renderAgents() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Waking up the care agent network…</div>`;
    let data;
    try {
      data = await SukoonAPI.get(`/api/caregiver/patients/${selectedPatientId}/agentic`);
    } catch (e) {
      content().innerHTML = `${patientHeader()}<div class="sk-empty">${e.message}</div>`;
      return;
    }
    content().innerHTML = patientHeader() + renderAgentNetworkHTML(data);
    wireAgentNetworkExtras("/api/caregiver", selectedPatientId, patients);
  }

  async function renderMedicines() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading medicines…</div>`;
    const items = await SukoonAPI.get(`/api/caregiver/patients/${selectedPatientId}/medicines/today`);
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card">
        <h3 style="margin-top:0;">Today's medicines</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">A medicine only counts as taken once both the patient and you confirm it.</p>
        <div id="medicineCards">${items.map(medicineCardHtml).join("") || '<div class="sk-empty">No medicines due yet today</div>'}</div>
      </div>
    `;
    content().querySelectorAll("[data-confirm]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await SukoonAPI.post(`/api/caregiver/reminders/${btn.dataset.confirm}/confirm`);
          renderMedicines();
        } catch (e) {
          alert(e.message);
        }
      });
    });
  }

  function medicineCardHtml(r) {
    const bothDone = r.status === "completed";
    return `
      <div class="sk-card" style="margin-bottom:10px; ${bothDone ? "border-color:var(--sukoon-good);" : ""}">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap;">
          <div>
            <strong>${skEscape(r.title_en)}</strong>
            <div style="color:var(--sukoon-ink-500); font-size:0.85rem;">${skEscape(r.detail || "")} · ${r.scheduled_time}</div>
            <div style="margin-top:6px; font-size:0.85rem;">
              ${r.patient_confirmed ? "✅" : "⬜"} Patient confirmed
              &nbsp;&nbsp;${r.caregiver_confirmed ? "✅" : "⬜"} You confirmed
            </div>
          </div>
          ${bothDone
            ? `<span class="sk-badge sk-badge-good">✓ Taken (confirmed by both)</span>`
            : r.caregiver_confirmed
              ? `<span class="sk-badge sk-badge-neutral">Waiting for patient</span>`
              : `<button class="sk-btn sk-btn-primary" data-confirm="${r.id}">I confirm this was given</button>`
          }
        </div>
      </div>
    `;
  }

  // ---- Reminders -------------------------------------------------------------
  async function renderReminders() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading reminders…</div>`;
    const [reminders, log] = await Promise.all([
      SukoonAPI.get(`/api/caregiver/reminders/${selectedPatientId}`),
      SukoonAPI.get(`/api/caregiver/reminders/${selectedPatientId}/log`),
    ]);

    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-grid sk-grid-2">
        <div class="sk-card">
          <h3 style="margin-top:0;">Active reminders</h3>
          <div id="reminderCards">${reminders.map(reminderCardHtml).join("") || '<div class="sk-empty">None yet</div>'}</div>
          <details style="margin-top:16px;">
            <summary style="cursor:pointer; font-weight:600; color:var(--sukoon-teal-700);">+ Add reminder</summary>
            <form id="reminderForm" style="margin-top:12px;">
              <div class="cg-form-row">
                <div class="sk-field"><label>Type</label>
                  <select name="kind"><option value="medicine">Medicine</option><option value="hydration">Hydration</option><option value="appointment">Appointment</option><option value="routine">Routine</option></select>
                </div>
                <div class="sk-field"><label>Time</label><input type="time" name="scheduled_time" required></div>
              </div>
              <div class="sk-field"><label>Title (English)</label><input name="title_en" required placeholder="e.g. Blood pressure tablet"></div>
              <div class="sk-field"><label>Title (Assamese, optional)</label><input name="title_as" placeholder="উদাহৰণ"></div>
              <div class="sk-field"><label>Detail (optional)</label><input name="detail" placeholder="Dosage / notes"></div>
              <div class="cg-form-row">
                <div class="sk-field"><label>Gentle follow-up after (minutes)</label><input type="number" name="escalation_minutes" value="15" min="1" max="180"></div>
                <div class="sk-field"><label>Alert caregiver after (minutes)</label><input type="number" name="escalation_final_minutes" value="30" min="2" max="360"></div>
              </div>
              <button class="sk-btn sk-btn-primary" type="submit">Add reminder</button>
            </form>
          </details>
        </div>
        <div class="sk-card">
          <h3 style="margin-top:0;">Recent reminder log</h3>
          <table class="sk-table">
            <thead><tr><th>Time</th><th>Reminder</th><th>Status</th></tr></thead>
            <tbody>${log.map((r) => `<tr><td>${r.scheduled_time} (${r.date})</td><td>${skEscape(r.title_en)}</td><td>${statusBadge(r.status)}</td></tr>`).join("") || '<tr><td colspan="3" class="sk-empty">No history yet</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    `;

    document.getElementById("reminderForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = Object.fromEntries(fd.entries());
      payload.patient_id = selectedPatientId;
      payload.escalation_minutes = parseInt(payload.escalation_minutes, 10);
      payload.escalation_final_minutes = parseInt(payload.escalation_final_minutes, 10);
      try {
        await SukoonAPI.post("/api/caregiver/reminders", payload);
        skToast("Reminder added", "good");
        renderReminders();
      } catch (err) { skToast(err.message, "critical"); }
    });

    content().querySelectorAll("[data-deactivate]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try { await SukoonAPI.del(`/api/caregiver/reminders/${btn.dataset.deactivate}`); renderReminders(); }
        catch (e) { skToast(e.message, "critical"); }
      });
    });
  }

  function reminderCardHtml(r) {
    return `<div class="sk-card" style="margin-bottom:8px; padding:12px 16px; display:flex; justify-content:space-between; align-items:center;">
      <div><strong>${skEscape(r.title_en)}</strong><div style="font-size:0.8rem; color:var(--sukoon-ink-500);">${r.kind} · ${r.scheduled_time} · alert after ${r.escalation_final_minutes}m</div></div>
      <button class="sk-btn sk-btn-danger" data-deactivate="${r.id}">Remove</button>
    </div>`;
  }

  function statusBadge(status) {
    const map = { completed: "good", pending: "neutral", missed: "critical", escalated: "warn", snoozed: "neutral" };
    return `<span class="sk-badge sk-badge-${map[status] || "neutral"}">${status}</span>`;
  }

  // ---- Routines -------------------------------------------------------------
  async function renderRoutines() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading routine…</div>`;
    const routines = await SukoonAPI.get(`/api/caregiver/routines/${selectedPatientId}`);
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card">
        <h3 style="margin-top:0;">Daily routine</h3>
        ${routines.sort((a, b) => a.scheduled_time.localeCompare(b.scheduled_time)).map((r) => `
          <div style="display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid var(--sukoon-line);">
            <div><strong>${skEscape(r.title_en)}</strong> <span style="color:var(--sukoon-ink-500); font-size:0.82rem;">(${skEscape(r.title_as || "")})</span></div>
            <div style="color:var(--sukoon-ink-500); font-size:0.85rem;">${r.period} · ${r.scheduled_time}</div>
          </div>
        `).join("") || '<div class="sk-empty">No routine items configured</div>'}
        <details style="margin-top:16px;">
          <summary style="cursor:pointer; font-weight:600; color:var(--sukoon-teal-700);">+ Add routine item</summary>
          <form id="routineForm" style="margin-top:12px;">
            <div class="cg-form-row">
              <div class="sk-field"><label>Period</label>
                <select name="period"><option value="morning">Morning</option><option value="afternoon">Afternoon</option><option value="evening">Evening</option><option value="custom">Custom</option></select>
              </div>
              <div class="sk-field"><label>Time</label><input type="time" name="scheduled_time" required></div>
            </div>
            <div class="sk-field"><label>Title (English)</label><input name="title_en" required></div>
            <div class="sk-field"><label>Title (Assamese, optional)</label><input name="title_as"></div>
            <button class="sk-btn sk-btn-primary" type="submit">Add</button>
          </form>
        </details>
      </div>
    `;
    document.getElementById("routineForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = Object.fromEntries(new FormData(e.target).entries());
      payload.patient_id = selectedPatientId;
      payload.is_custom = payload.period === "custom";
      try { await SukoonAPI.post("/api/caregiver/routines", payload); skToast("Routine item added", "good"); renderRoutines(); }
      catch (err) { skToast(err.message, "critical"); }
    });
  }

  // ---- Appointments -------------------------------------------------------------
  async function renderAppointments() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading…</div>`;
    const appts = await SukoonAPI.get(`/api/caregiver/appointments/${selectedPatientId}`);
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card">
        <h3 style="margin-top:0;">Appointments</h3>
        <table class="sk-table">
          <thead><tr><th>Date</th><th>Doctor</th><th>Location</th></tr></thead>
          <tbody>${appts.map((a) => `<tr><td>${a.date} ${a.time}</td><td>${skEscape(a.doctor_name)}</td><td>${skEscape(a.location || a.hospital_or_clinic || "")}</td></tr>`).join("") || '<tr><td colspan="3" class="sk-empty">No appointments yet</td></tr>'}</tbody>
        </table>
        <details style="margin-top:16px;">
          <summary style="cursor:pointer; font-weight:600; color:var(--sukoon-teal-700);">+ Add appointment</summary>
          <form id="apptForm" style="margin-top:12px;">
            <div class="sk-field"><label>Doctor name</label><input name="doctor_name" required></div>
            <div class="sk-field"><label>Hospital / clinic</label><input name="hospital_or_clinic"></div>
            <div class="cg-form-row">
              <div class="sk-field"><label>Date</label><input type="date" name="date" required></div>
              <div class="sk-field"><label>Time</label><input type="time" name="time" required></div>
            </div>
            <div class="sk-field"><label>Location</label><input name="location"></div>
            <button class="sk-btn sk-btn-primary" type="submit">Add appointment</button>
          </form>
        </details>
      </div>
    `;
    document.getElementById("apptForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = Object.fromEntries(new FormData(e.target).entries());
      payload.patient_id = selectedPatientId;
      try { await SukoonAPI.post("/api/caregiver/appointments", payload); skToast("Appointment added", "good"); renderAppointments(); }
      catch (err) { skToast(err.message, "critical"); }
    });
  }

  // ---- Family & Contacts (family tree + call-for-comfort management) -----------
  const CONTACT_TYPE_ICON = { family: "👨‍👩‍👧", caregiver: "🧑‍🤝‍🧑", nurse: "👩‍⚕️", other: "👤" };
  let contactsCache = [];
  let editingContactId = null;

  async function renderContacts() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading…</div>`;
    contactsCache = await SukoonAPI.get(`/api/caregiver/contacts/${selectedPatientId}`);
    const p = dashboard.patient;
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card" style="margin-bottom:18px;">
        <h3 style="margin-top:0;">📞 Call the patient</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">Set the patient's phone number so anyone here can reach them directly, e.g. if they seem upset or miss a check-in.</p>
        <form id="patientPhoneForm" class="cg-form-row" style="align-items:end;">
          <div class="sk-field" style="margin-bottom:0;"><label>Patient's phone number</label><input name="phone" value="${p.phone ? skEscape(p.phone) : ""}" placeholder="+91 ..."></div>
          <button class="sk-btn sk-btn-secondary" type="submit">Save number</button>
        </form>
        ${p.phone ? `<button class="sk-btn sk-btn-primary" id="callPatientBtn" style="margin-top:12px;">📞 Call ${skEscape(p.full_name)} now</button>` : ""}
      </div>

      <div class="sk-card">
        <h3 style="margin-top:0;">Family tree &amp; call list</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">These are the people shown on the patient's own "My Family" screen, with photos to help them remember who's who — and who they can call if they're upset.</p>
        <div id="contactCards">${contactsCache.map((c) => contactCardHtml(c)).join("") || '<div class="sk-empty">No family members added yet</div>'}</div>
        <details style="margin-top:16px;" ${editingContactId ? "" : "open"} id="addContactDetails">
          <summary style="cursor:pointer; font-weight:600; color:var(--sukoon-teal-700);">+ Add family member / contact</summary>
          ${contactFormHtml(null)}
        </details>
      </div>
    `;

    document.getElementById("patientPhoneForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const phone = new FormData(e.target).get("phone");
      try {
        await SukoonAPI.put(`/api/caregiver/patients/${selectedPatientId}/phone`, { phone });
        dashboard.patient.phone = phone;
        skToast("Patient's phone number saved", "good");
        renderContacts();
      } catch (err) { skToast(err.message, "critical"); }
    });
    const callBtn = document.getElementById("callPatientBtn");
    if (callBtn) callBtn.addEventListener("click", () => { window.location.href = "tel:" + p.phone.replace(/\s+/g, ""); });

    wireContactForm(document.getElementById("contactForm"), null);
    if (editingContactId) {
      const editing = contactsCache.find((x) => x.id === editingContactId);
      if (editing) wireContactForm(document.getElementById(`contactForm-edit-${editing.id}`), editing);
    }
    content().querySelectorAll("[data-edit-contact]").forEach((btn) => {
      btn.addEventListener("click", () => { editingContactId = btn.dataset.editContact; renderContacts(); });
    });
    content().querySelectorAll("[data-cancel-edit]").forEach((btn) => {
      btn.addEventListener("click", () => { editingContactId = null; renderContacts(); });
    });
    content().querySelectorAll("[data-delete-contact]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try { await SukoonAPI.del(`/api/caregiver/contacts/${btn.dataset.deleteContact}`); skToast("Removed", "good"); editingContactId = null; renderContacts(); }
        catch (err) { skToast(err.message, "critical"); }
      });
    });
  }

  function contactCardHtml(c) {
    if (editingContactId === c.id) {
      return `<div class="sk-card" style="margin-bottom:8px; padding:14px 16px;">
        <strong>Editing ${skEscape(c.name)}</strong>
        ${contactFormHtml(c)}
        <button class="sk-btn sk-btn-ghost" data-cancel-edit="${c.id}" style="margin-top:8px;">Cancel</button>
      </div>`;
    }
    const avatar = c.photo_url
      ? `<img src="${c.photo_url}" style="width:44px;height:44px;border-radius:50%;object-fit:cover;">`
      : `<div class="fm-people-avatar" style="background:var(--sukoon-teal-50); color:var(--sukoon-teal-800); width:44px; height:44px; font-size:1.3rem;">${CONTACT_TYPE_ICON[c.contact_type] || "👤"}</div>`;
    return `<div class="sk-card" style="margin-bottom:8px; padding:12px 16px; display:flex; justify-content:space-between; align-items:center; gap:10px;">
      <div style="display:flex; align-items:center; gap:12px;">
        ${avatar}
        <div><strong>${skEscape(c.name)}</strong><div style="font-size:0.8rem; color:var(--sukoon-ink-500);">${skEscape(c.relationship_label || "")}${c.phone ? " · " + skEscape(c.phone) : ""}</div></div>
      </div>
      <div style="display:flex; gap:6px;">
        <button class="sk-btn sk-btn-ghost" data-edit-contact="${c.id}">Edit</button>
        <button class="sk-btn sk-btn-danger" data-delete-contact="${c.id}">Remove</button>
      </div>
    </div>`;
  }

  function contactFormHtml(c) {
    const id = c ? `contactForm-edit-${c.id}` : "contactForm";
    return `
      <form id="${id}" class="contact-form" style="margin-top:12px;" data-contact-id="${c ? c.id : ""}">
        <div class="cg-form-row">
          <div class="sk-field"><label>Name</label><input name="name" required value="${c ? skEscape(c.name) : ""}"></div>
          <div class="sk-field"><label>Relationship</label><input name="relationship_label" placeholder="e.g. Son, Visiting Nurse" value="${c ? skEscape(c.relationship_label || "") : ""}"></div>
        </div>
        <div class="cg-form-row">
          <div class="sk-field"><label>Type</label>
            <select name="contact_type">
              <option value="family" ${c && c.contact_type === "family" ? "selected" : ""}>Family</option>
              <option value="caregiver" ${c && c.contact_type === "caregiver" ? "selected" : ""}>Caregiver</option>
              <option value="nurse" ${c && c.contact_type === "nurse" ? "selected" : ""}>Nurse</option>
              <option value="other" ${c && c.contact_type === "other" ? "selected" : ""}>Other</option>
            </select>
          </div>
          <div class="sk-field"><label>Phone number</label><input name="phone" value="${c ? skEscape(c.phone || "") : ""}" placeholder="+91 ..."></div>
        </div>
        <div class="sk-field"><label>Photo (optional — helps the patient recognize them)</label><input type="file" name="photo" accept="image/*"></div>
        <button class="sk-btn sk-btn-primary" type="submit">${c ? "Save changes" : "Add to family list"}</button>
      </form>
    `;
  }

  function readPhotoAsDataUrl(fileInput) {
    return new Promise((resolve, reject) => {
      const file = fileInput && fileInput.files && fileInput.files[0];
      if (!file) { resolve(undefined); return; }
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("Could not read photo"));
      reader.readAsDataURL(file);
    });
  }

  function wireContactForm(form, existing) {
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      let photoDataUrl;
      try { photoDataUrl = await readPhotoAsDataUrl(e.target.querySelector('input[type="file"]')); }
      catch (err) { skToast(err.message, "critical"); return; }
      const payload = {
        name: fd.get("name"), relationship_label: fd.get("relationship_label"),
        contact_type: fd.get("contact_type"), phone: fd.get("phone") || null,
      };
      if (photoDataUrl !== undefined) payload.photo_data_url = photoDataUrl;
      try {
        if (existing) {
          payload.display_order = existing.display_order;
          await SukoonAPI.put(`/api/caregiver/contacts/${existing.id}`, payload);
          skToast("Saved", "good");
          editingContactId = null;
        } else {
          payload.patient_id = selectedPatientId;
          payload.display_order = 99;
          await SukoonAPI.post("/api/caregiver/contacts", payload);
          skToast("Added", "good");
        }
        renderContacts();
      } catch (err) { skToast(err.message, "critical"); }
    });
  }

  // ---- Doctors (read-only) -------------------------------------------------------------
  // Requesting / approving / rejecting / revoking doctor access now lives only in the
  // Family dashboard (see family.js) — the caregiver app shows visibility only, so a
  // caregiver always knows who currently has authorized access to their patient.
  async function renderDoctors() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading…</div>`;
    const auths = await SukoonAPI.get(`/api/authorization/patient/${selectedPatientId}`);
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card">
        <h3 style="margin-top:0;">Authorized doctors</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">This is a read-only view. Doctor access is requested, approved and revoked from the <strong>Family dashboard</strong>.</p>
        ${auths.map(authCardHtml).join("") || '<div class="sk-empty">No doctors added yet</div>'}
      </div>
    `;
  }

  function authCardHtml(a) {
    const statusColor = { pending: "warn", approved: "good", rejected: "critical", revoked: "neutral" }[a.status] || "neutral";
    const scopes = [
      ["Cognitive performance", a.scope_cognitive_performance], ["Activity history", a.scope_activity_history],
      ["Reminder adherence", a.scope_reminder_adherence], ["Location", a.scope_location],
      ["Wearable data", a.scope_wearable_data], ["Medical records", a.scope_medical_records],
    ];
    return `<div class="sk-card" style="margin-bottom:10px; padding:14px 16px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div><strong>${skEscape(a.doctor_name)}</strong><div style="font-size:0.8rem; color:var(--sukoon-ink-500);">${skEscape(a.hospital_or_clinic || "")}</div></div>
        <span class="sk-badge sk-badge-${statusColor}">${a.status}</span>
      </div>
      <div style="margin-top:8px; font-size:0.8rem;">
        ${scopes.map(([label, on]) => `<span style="margin-right:10px;">${on ? "✓" : "✕"} ${label}</span>`).join("")}
      </div>
    </div>`;
  }

  // ---- Location & wearable -------------------------------------------------------------
  async function renderSafety() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading…</div>`;
    const [locData, wearable] = await Promise.all([
      SukoonAPI.get(`/api/caregiver/location/${selectedPatientId}`),
      SukoonAPI.get(`/api/caregiver/wearable/${selectedPatientId}`),
    ]);
    const sz = locData.safe_zone;

    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-disclaimer" style="margin-bottom:16px;">This is a safety feature, not covert surveillance. Location tracking requires explicit authorization and can be turned off at any time.</div>
      <div class="sk-card sk-device-card" style="margin-bottom:18px;">
        <div style="font-size:2.4rem;">🏷️</div>
        <div style="flex:1; min-width:220px;">
          <h3 style="margin:0 0 4px;">SafeTag Tracker™ <span class="sk-badge sk-badge-info">Our hardware design</span></h3>
          <div style="font-size:0.85rem; color:var(--sukoon-ink-700); line-height:1.5;">A discreet GNSS + cellular tracker module built to embed into a pendant or ring, purpose-designed for Sukoon by Team SevaTech. The readings below simulate what a paired SafeTag Tracker reports live.</div>
          <div class="sk-device-specs">
            <div><b>Location</b> Multi-constellation GNSS + LTE-M/NB-IoT</div>
            <div><b>SOS</b> Press-and-hold alert → instant caregiver push</div>
            <div><b>Fall/motion</b> 3-axis accelerometer detection</div>
            <div><b>Geofencing</b> Hysteresis-based, spam-free alerts</div>
            <div><b>Tamper</b> Hall-sensor removal detection</div>
            <div><b>Battery</b> Fuel-gauge monitored, magnetic charging</div>
          </div>
        </div>
      </div>
      <div class="sk-card" style="margin-bottom:18px;">
        <h3 style="margin-top:0;">Live map ${locData.history[0] && locData.history[0].is_demo_data ? '<span class="sk-badge sk-badge-demo">Demo Data</span>' : ""}</h3>
        <div id="safetyMap" style="height:340px; border-radius:10px; overflow:hidden; border:1px solid var(--sukoon-line);"></div>
      </div>
      <div class="sk-grid sk-grid-2">
        <div class="sk-card">
          <h3 style="margin-top:0;">Safe zone &amp; location</h3>
          <form id="safeZoneForm">
            <div class="sk-field"><label>Label</label><input name="label" value="${sz ? skEscape(sz.label) : "Home"}"></div>
            <div class="cg-form-row">
              <div class="sk-field"><label>Latitude</label><input name="center_lat" type="number" step="0.0001" value="${sz ? sz.center_lat : 26.1445}" required></div>
              <div class="sk-field"><label>Longitude</label><input name="center_lng" type="number" step="0.0001" value="${sz ? sz.center_lng : 91.7362}" required></div>
            </div>
            <div class="sk-field"><label>Radius (metres)</label><input name="radius_m" type="number" value="${sz ? sz.radius_m : 500}" required></div>
            <div class="sk-checkbox-row"><input type="checkbox" name="tracking_enabled" ${sz && sz.tracking_enabled ? "checked" : ""}> Enable location tracking</div>
            <div class="sk-checkbox-row"><input type="checkbox" name="consented" ${sz && sz.consented ? "checked" : ""}> Patient/caregiver consent confirmed</div>
            <button class="sk-btn sk-btn-primary" type="submit" style="margin-top:10px;">Save safe zone</button>
          </form>
          <div style="margin-top:16px; padding-top:16px; border-top:1px solid var(--sukoon-line);">
            <strong>Current status:</strong>
            ${locData.history[0] ? `<div style="margin-top:6px;">${locData.history[0].within_safe_zone ? "✅ Within safe zone" : "⚠️ Outside safe zone"} — ${locData.history[0].distance_from_safe_zone_m}m from ${sz ? skEscape(sz.label) : "home"}<br><span style="color:var(--sukoon-ink-500); font-size:0.8rem;">${skTimeAgo(locData.history[0].timestamp)} <span class="sk-badge sk-badge-demo">Demo Data</span></span></div>` : '<div class="sk-empty">No location data yet</div>'}
            <div style="margin-top:10px; display:flex; gap:8px;">
              <button class="sk-btn sk-btn-secondary" id="simulateInBtn">Simulate: within zone</button>
              <button class="sk-btn sk-btn-secondary" id="simulateOutBtn">Simulate: moved outside</button>
            </div>
          </div>
        </div>
        <div class="sk-card">
          <h3 style="margin-top:0;">SafeTag Tracker — live vitals <span class="sk-badge sk-badge-demo">Demo Data</span></h3>
          ${wearable[0] ? `
            <div class="stat-row">
              <span class="stat-chip">❤️ ${wearable[0].heart_rate_bpm} bpm</span>
              <span class="stat-chip">👣 ${wearable[0].steps} steps</span>
              <span class="stat-chip">⚡ ${wearable[0].activity_level}</span>
              <span class="stat-chip">🔋 ${wearable[0].battery_pct}%</span>
            </div>
            <div style="color:var(--sukoon-ink-500); font-size:0.8rem;">${skTimeAgo(wearable[0].timestamp)}</div>
          ` : '<div class="sk-empty">No wearable data yet</div>'}
          <button class="sk-btn sk-btn-secondary" id="simulateWearableBtn" style="margin-top:12px;">Simulate new reading</button>
          <div class="sk-disclaimer" style="margin-top:14px;">Wearable data provides supporting activity information only — it does not diagnose dementia.</div>
        </div>
      </div>
    `;

    document.getElementById("safeZoneForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = {
        label: fd.get("label"), center_lat: parseFloat(fd.get("center_lat")), center_lng: parseFloat(fd.get("center_lng")),
        radius_m: parseInt(fd.get("radius_m"), 10), tracking_enabled: !!fd.get("tracking_enabled"), consented: !!fd.get("consented"),
      };
      try { await SukoonAPI.post(`/api/caregiver/location/${selectedPatientId}/safe-zone`, payload); skToast("Safe zone saved", "good"); renderSafety(); }
      catch (err) { skToast(err.message, "critical"); }
    });
    document.getElementById("simulateInBtn").addEventListener("click", () => simulateMove(100));
    document.getElementById("simulateOutBtn").addEventListener("click", () => simulateMove(750));
    document.getElementById("simulateWearableBtn").addEventListener("click", async () => {
      try { await SukoonAPI.post(`/api/caregiver/wearable/${selectedPatientId}/simulate-tick`); skToast("New reading generated", "good"); renderSafety(); }
      catch (err) { skToast(err.message, "critical"); }
    });

    renderSafetyMap(locData, sz);
  }

  function renderSafetyMap(locData, sz) {
    const mapDiv = document.getElementById("safetyMap");
    if (!mapDiv || typeof L === "undefined") return;

    const centerLat = sz ? sz.center_lat : 26.1445;
    const centerLng = sz ? sz.center_lng : 91.7362;
    const latest = locData.history[0];

    if (safetyMap) { safetyMap.remove(); safetyMap = null; }
    safetyMap = L.map(mapDiv, { scrollWheelZoom: false }).setView([centerLat, centerLng], 14);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(safetyMap);

    L.marker([centerLat, centerLng]).addTo(safetyMap)
      .bindPopup(`🏠 ${sz ? skEscape(sz.label) : "Home"} (safe zone centre)`);

    if (sz) {
      L.circle([centerLat, centerLng], {
        radius: sz.radius_m, color: "#1f9d8a", fillColor: "#1f9d8a", fillOpacity: 0.12, weight: 2,
      }).addTo(safetyMap);
    }

    if (latest) {
      const within = latest.within_safe_zone;
      const icon = L.divIcon({
        className: "", html: `<div style="font-size:26px; transform:translate(-50%,-90%);">${within ? "🟢" : "🔴"}</div>`,
        iconSize: [0, 0],
      });
      L.marker([latest.latitude, latest.longitude], { icon })
        .addTo(safetyMap)
        .bindPopup(`${within ? "✅ Within safe zone" : "⚠️ Outside safe zone"} — ${latest.distance_from_safe_zone_m}m from centre<br><span style="font-size:0.75rem;">${skTimeAgo(latest.timestamp)} · Demo Data</span>`)
        .openPopup();
      const bounds = L.latLngBounds([[centerLat, centerLng], [latest.latitude, latest.longitude]]);
      safetyMap.fitBounds(bounds.pad(0.4));
    }

    setTimeout(() => safetyMap && safetyMap.invalidateSize(), 150);
  }

  async function simulateMove(distanceM) {
    try {
      await SukoonAPI.post(`/api/caregiver/location/${selectedPatientId}/simulate-move`, { distance_m: distanceM });
      skToast(distanceM > 500 ? "⚠️ Simulated: patient outside safe zone" : "Simulated: patient within safe zone", distanceM > 500 ? "warn" : "good");
      renderSafety();
    } catch (err) { skToast(err.message, "critical"); }
  }

  // ---- Alerts -------------------------------------------------------------
  async function renderAlerts() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading…</div>`;
    const alerts = await SukoonAPI.get(`/api/caregiver/alerts/${selectedPatientId}`);
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card">
        <h3 style="margin-top:0;">Alerts</h3>
        ${alerts.map((a) => `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:12px 0; border-bottom:1px solid var(--sukoon-line);">
            <div>
              <span class="sk-badge sk-badge-${a.severity === "critical" ? "critical" : "warn"}">${a.severity}</span>
              <span style="margin-left:8px;">${skEscape(a.message_en)}</span>
              <div style="font-size:0.78rem; color:var(--sukoon-ink-500); margin-top:2px;">${skTimeAgo(a.created_at)}</div>
            </div>
            ${a.acknowledged ? '<span class="sk-badge sk-badge-good">Acknowledged</span>' : `<button class="sk-btn sk-btn-ghost" data-ack="${a.id}">Acknowledge</button>`}
          </div>
        `).join("") || '<div class="sk-empty">No alerts</div>'}
      </div>
    `;
    content().querySelectorAll("[data-ack]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try { await SukoonAPI.post(`/api/caregiver/alerts/${btn.dataset.ack}/acknowledge`); renderAlerts(); }
        catch (err) { skToast(err.message, "critical"); }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
