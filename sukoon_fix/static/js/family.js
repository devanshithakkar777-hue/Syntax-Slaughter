/* Sukoon — Family dashboard controller.
   A broader household view than a single caregiver's: patient + caregiver +
   doctor data together in one place. This is also the ONLY dashboard (besides
   the patient's own account) that can request/approve/reject/revoke doctor
   authorizations — the caregiver app only shows that list read-only. */

(() => {
  let user = null;
  let patients = [];
  let selectedPatientId = null;
  let dashboard = null;
  let activeTab = "overview";
  let chartInstance = null;
  let safetyMap = null;

  const DOMAIN_BY_ACTIVITY = {
    memory_matching: "memory", pattern_recognition: "attention",
    object_recognition: "recognition", routine_recall: "engagement",
  };
  const DOMAIN_COLORS = { memory: "#1f9d8a", attention: "#c98a1f", recognition: "#2f6fb0", engagement: "#8e5fc9" };
  const MOOD_ICON = { good: "😊", okay: "🙂", unsure: "😐", sad: "🙁" };

  const content = () => document.getElementById("tabContent");

  async function init() {
    user = skRequireAuth("family");
    if (!user) return;
    document.getElementById("fmUserName").textContent = user.full_name;
    document.getElementById("logoutBtn").addEventListener("click", skLogout);
    document.querySelectorAll(".sk-tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
    if (typeof SukoonVoice !== "undefined") SukoonVoice.attachReadAloud(content());

    try {
      patients = await SukoonAPI.get("/api/family/patients");
    } catch (e) {
      content().innerHTML = `<div class="sk-empty">${e.message}</div>`;
      return;
    }
    renderPatientList();
    if (patients.length) selectPatient(patients[0].id);
    else content().innerHTML = `<div class="sk-empty">No patients are linked to your family account yet.</div>`;
  }

  function renderPatientList() {
    const list = document.getElementById("patientList");
    list.innerHTML = "";
    patients.forEach((p) => {
      const el = document.createElement("div");
      el.className = "fm-patient-item" + (p.id === selectedPatientId ? " active" : "");
      el.innerHTML = `
        <div class="fm-patient-avatar">${skEscape((p.full_name || "?")[0])}</div>
        <div>
          <div class="fm-patient-name">${skEscape(p.full_name)}</div>
          <div class="fm-patient-sub">${p.age ? p.age + " yrs · " : ""}${skEscape(p.home_region || "")}</div>
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
    content().innerHTML = `<div class="sk-loading">Loading combined dashboard…</div>`;
    try {
      dashboard = await SukoonAPI.get(`/api/family/patients/${id}/dashboard`);
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
      overview: renderOverview, agents: renderAgents, updates: renderUpdates, doctors: renderDoctors, records: renderRecords,
      appointments: renderAppointments, contacts: renderContacts, safety: renderSafety, alerts: renderAlerts,
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

  // ---- Overview: patient + caregiver + doctor, all together --------------------
  function renderOverview() {
    const d = dashboard;
    const perf = d.performance_30d || [];
    const latestInsight = perf.length ? perf[perf.length - 1] : null;
    const openAlerts = (d.alerts || []).filter((a) => !a.acknowledged);
    const approvedDoctors = (d.doctor_authorizations || []).filter((a) => a.status === "approved");

    content().innerHTML = `
      ${patientHeader()}
      ${openAlerts.length ? `<div class="sk-card" style="margin-bottom:18px; border-color:#f4c7c1;">
        <strong style="color:var(--sukoon-critical);">⚠ ${openAlerts.length} unresolved alert${openAlerts.length > 1 ? "s" : ""}</strong>
        <div style="margin-top:8px; font-size:0.88rem;">${skEscape(openAlerts[0].message_en)}</div>
      </div>` : ""}

      <div class="sk-grid sk-grid-2" style="margin-bottom:18px;">
        <div class="sk-card">
          <h3 style="margin:0 0 10px; font-size:0.95rem;">🧑‍🤝‍🧑 Caregiver(s)</h3>
          ${d.caregivers.length ? d.caregivers.map((c) => `
            <div class="fm-people-card">
              <div class="fm-people-avatar" style="background:var(--sukoon-teal-50); color:var(--sukoon-teal-800);">🧑‍🤝‍🧑</div>
              <div><strong>${skEscape(c.full_name)}</strong><div style="font-size:0.78rem; color:var(--sukoon-ink-500);">${skEscape(c.relationship_to_patient || "")} · ${skEscape(c.email)}</div></div>
            </div>
          `).join("") : '<div class="sk-empty">No caregiver linked yet</div>'}
        </div>
        <div class="sk-card">
          <h3 style="margin:0 0 10px; font-size:0.95rem;">🩺 Authorized doctor(s)</h3>
          ${approvedDoctors.length ? approvedDoctors.map((a) => `
            <div class="fm-people-card">
              <div class="fm-people-avatar" style="background:#eef2ff; color:#3b4fb0;">🩺</div>
              <div><strong>${skEscape(a.doctor_name)}</strong><div style="font-size:0.78rem; color:var(--sukoon-ink-500);">${skEscape(a.hospital_or_clinic || "")}</div></div>
            </div>
          `).join("") : '<div class="sk-empty">No doctor currently authorized — see the Doctor Authorization tab</div>'}
        </div>
      </div>

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
        <div class="sk-card"><strong>Reminder adherence</strong><div style="margin-top:6px; color:var(--sukoon-ink-500); font-size:0.85rem;">${d.reminder_adherence.length} recent entries — see Appointments tab for the full picture.</div></div>
        <div class="sk-card"><strong>Wearable</strong><div style="margin-top:6px; font-size:0.85rem;">${d.wearable_latest ? `❤️ ${d.wearable_latest.heart_rate_bpm} bpm · 👣 ${d.wearable_latest.steps} steps <span class="sk-badge sk-badge-demo">Demo Data</span>` : "No data yet"}</div></div>
        <div class="sk-card"><strong>Location</strong><div style="margin-top:6px; font-size:0.85rem;">${d.location_latest ? (d.location_latest.within_safe_zone ? "✅ Within safe zone" : "⚠️ Outside safe zone") : "Not enabled"}</div></div>
      </div>

      <div class="sk-disclaimer" style="margin-top:18px;">${skEscape(d.disclaimer)}</div>
    `;

    renderPerfChart(perf);
    renderMoodTrend(d.mood_30d || []);
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
      borderColor: DOMAIN_COLORS[d], backgroundColor: DOMAIN_COLORS[d], spanGaps: true, tension: 0.3,
    }));
    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(canvas, {
      type: "line",
      data: { labels: dates.map((d) => d.slice(5)), datasets },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } } }, plugins: { legend: { position: "bottom" } } },
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

  // ---- Doctor authorization: the ONE place this can be managed -----------------
  async function renderDoctors() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading…</div>`;
    const auths = await SukoonAPI.get(`/api/authorization/patient/${selectedPatientId}`);
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card">
        <h3 style="margin-top:0;">Doctor authorizations</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">Requesting, approving, rejecting and revoking doctor access happens here. The caregiver dashboard shows this list read-only.</p>
        ${auths.map(authCardHtml).join("") || '<div class="sk-empty">No doctors added yet</div>'}
        <details style="margin-top:16px;">
          <summary style="cursor:pointer; font-weight:600; color:var(--sukoon-teal-700);">+ Add doctor</summary>
          <form id="doctorForm" style="margin-top:12px;">
            <div class="sk-field"><label>Doctor name</label><input name="doctor_name" required></div>
            <div class="sk-field"><label>Hospital / clinic</label><input name="hospital_or_clinic"></div>
            <div class="sk-field"><label>Email / identifier</label><input name="doctor_email" type="email" required></div>
            <div>
              <div class="sk-checkbox-row"><input type="checkbox" name="scope_cognitive_performance" checked> Cognitive performance</div>
              <div class="sk-checkbox-row"><input type="checkbox" name="scope_activity_history" checked> Activity history</div>
              <div class="sk-checkbox-row"><input type="checkbox" name="scope_reminder_adherence" checked> Reminder adherence</div>
              <div class="sk-checkbox-row"><input type="checkbox" name="scope_wearable_data" checked> Wearable data</div>
              <div class="sk-checkbox-row"><input type="checkbox" name="scope_medical_records" checked> Medical records</div>
              <div class="sk-checkbox-row"><input type="checkbox" name="scope_location"> Location</div>
            </div>
            <button class="sk-btn sk-btn-primary" type="submit" style="margin-top:10px;">Send authorization request</button>
          </form>
        </details>
      </div>
    `;

    document.getElementById("doctorForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = {
        patient_id: selectedPatientId, doctor_name: fd.get("doctor_name"),
        hospital_or_clinic: fd.get("hospital_or_clinic"), doctor_email: fd.get("doctor_email"),
        scope_cognitive_performance: !!fd.get("scope_cognitive_performance"),
        scope_activity_history: !!fd.get("scope_activity_history"),
        scope_reminder_adherence: !!fd.get("scope_reminder_adherence"),
        scope_wearable_data: !!fd.get("scope_wearable_data"),
        scope_medical_records: !!fd.get("scope_medical_records"),
        scope_location: !!fd.get("scope_location"),
      };
      try {
        const res = await SukoonAPI.post("/api/authorization", payload);
        if (res._demo_new_doctor_login) {
          skToast(`Demo doctor account created. Login: ${res._demo_new_doctor_login.email} / ${res._demo_new_doctor_login.password}`, "good");
        } else {
          skToast("Authorization requested", "good");
        }
        renderDoctors();
      } catch (err) { skToast(err.message, "critical"); }
    });

    content().querySelectorAll("[data-approve], [data-reject]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.approve || btn.dataset.reject;
        try { await SukoonAPI.post(`/api/authorization/${id}/decide`, { approve: !!btn.dataset.approve }); renderDoctors(); }
        catch (err) { skToast(err.message, "critical"); }
      });
    });
    content().querySelectorAll("[data-revoke]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try { await SukoonAPI.post(`/api/authorization/${btn.dataset.revoke}/revoke`); renderDoctors(); }
        catch (err) { skToast(err.message, "critical"); }
      });
    });
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
      <div style="margin-top:10px; display:flex; gap:8px;">
        ${a.status === "pending" ? `<button class="sk-btn sk-btn-primary" data-approve="${a.id}">Approve</button><button class="sk-btn sk-btn-ghost" data-reject="${a.id}">Reject</button>` : ""}
        ${a.status === "approved" ? `<button class="sk-btn sk-btn-danger" data-revoke="${a.id}">Revoke access</button>` : ""}
      </div>
    </div>`;
  }

  // ---- Medical records (hospital-file style, read-only here) -------------------
  function renderRecords() {
    const records = dashboard.medical_records || [];
    content().innerHTML = `
      ${patientHeader()}
      <div class="dr-section-title" style="font-size:0.82rem; text-transform:uppercase; letter-spacing:0.04em; color:var(--sukoon-ink-500); margin-bottom:10px;">Hospital file</div>
      ${records.map(fileCardHtml).join("") || '<div class="sk-card"><div class="sk-empty">No visit records yet — these are written by an authorized doctor after a visit.</div></div>'}
    `;
  }

  function fileCardHtml(r) {
    return `<div class="dr-file-card">
      <div class="dr-file-head">
        <div>
          <div class="dr-file-label">Visit record</div>
          <div style="font-weight:700; font-size:1.05rem;">${r.visit_date}</div>
        </div>
        <div style="text-align:right;">
          <div class="dr-file-label">Attending physician</div>
          <div>${skEscape(r.doctor_name || "")}</div>
          <div style="font-size:0.78rem; color:#8a7c56;">${skEscape(r.hospital_or_clinic || "")}</div>
        </div>
      </div>
      <dl>
        ${r.chief_complaint ? `<div class="dr-file-row"><dt>Chief complaint</dt><dd>${skEscape(r.chief_complaint)}</dd></div>` : ""}
        <div class="dr-file-row"><dt>Diagnosis</dt><dd>${skEscape(r.diagnosis)}</dd></div>
        ${r.prescription ? `<div class="dr-file-row"><dt>Prescription</dt><dd style="white-space:pre-line;">${skEscape(r.prescription)}</dd></div>` : ""}
        ${(r.vitals_bp || r.vitals_pulse || r.vitals_weight_kg) ? `<div class="dr-file-row"><dt>Vitals</dt><dd>${[r.vitals_bp, r.vitals_pulse, r.vitals_weight_kg ? r.vitals_weight_kg + " kg" : null].filter(Boolean).join(" · ")}</dd></div>` : ""}
        ${r.follow_up_instructions ? `<div class="dr-file-row"><dt>Follow-up</dt><dd>${skEscape(r.follow_up_instructions)}${r.follow_up_date ? " (by " + r.follow_up_date + ")" : ""}</dd></div>` : ""}
      </dl>
    </div>`;
  }

  // ---- Appointments (read-only) -------------------------------------------------
  function renderAppointments() {
    const appts = dashboard.appointments || [];
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card">
        <h3 style="margin-top:0;">Appointments</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">Appointments are scheduled from the Caregiver dashboard. Join the same video call as the doctor and patient from here — no download or sign-up needed.</p>
        <table class="sk-table">
          <thead><tr><th>Date</th><th>Doctor</th><th>Location</th><th></th></tr></thead>
          <tbody>${appts.map((a) => `<tr><td>${a.date} ${a.time}</td><td>${skEscape(a.doctor_name)}</td><td>${skEscape(a.location || a.hospital_or_clinic || "")}</td><td><a class="sk-btn sk-btn-secondary" href="${a.virtual_meeting_url}" target="_blank" rel="noopener">🎥 Join Virtually</a></td></tr>`).join("") || '<tr><td colspan="4" class="sk-empty">No appointments yet</td></tr>'}</tbody>
        </table>
      </div>
    `;
  }

  // ---- Updates feed (mood/reminder/safety/medical events, per preference) -------
  // ---- AI Care Agent Network -------------------------------------------
  async function renderAgents() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Waking up the care agent network…</div>`;
    let data;
    try {
      data = await SukoonAPI.get(`/api/family/patients/${selectedPatientId}/agentic`);
    } catch (e) {
      content().innerHTML = `${patientHeader()}<div class="sk-empty">${e.message}</div>`;
      return;
    }
    content().innerHTML = patientHeader() + renderAgentNetworkHTML(data);
    wireAgentNetworkExtras("/api/family", selectedPatientId, patients);
  }

  async function renderUpdates() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading updates…</div>`;
    const [items, pref] = await Promise.all([
      SukoonAPI.get("/api/family/notifications"),
      SukoonAPI.get("/api/family/notification-preference"),
    ]);
    const CATEGORY_ICON = { mood: "🙂", reminder: "⏰", safety: "🛟", alert: "🆘", medical_record: "🩺", call: "📞" };
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card" style="margin-bottom:18px;">
        <h3 style="margin-top:0;">Notification preference</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">Choose how much you want to hear. "Every update" includes small things like a missed water reminder; "Important only" sticks to safety events like leaving the safe zone or a new diagnosis.</p>
        <div style="display:flex; gap:10px; margin-top:10px;">
          <button class="sk-btn ${pref.notification_preference === "all" ? "sk-btn-primary" : "sk-btn-ghost"}" data-pref="all">Every little update</button>
          <button class="sk-btn ${pref.notification_preference === "important" ? "sk-btn-primary" : "sk-btn-ghost"}" data-pref="important">Important updates only</button>
        </div>
      </div>
      <div class="sk-card">
        <h3 style="margin-top:0;">Recent updates</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">Everything about the patient's care in one feed — check-ins, reminders, caregiver actions, safety alerts and the doctor's notes.</p>
        ${items.map((n) => `
          <div style="display:flex; gap:12px; padding:12px 0; border-bottom:1px solid var(--sukoon-line);${n.read ? "" : " background:var(--sukoon-teal-50);"}">
            <div style="font-size:1.3rem;">${CATEGORY_ICON[n.category] || "🔔"}</div>
            <div style="flex:1;">
              <strong>${skEscape(n.title)}</strong>
              <div style="font-size:0.85rem; color:var(--sukoon-ink-700); margin-top:2px;">${skEscape(n.body || "")}</div>
              <div style="font-size:0.76rem; color:var(--sukoon-ink-500); margin-top:2px;">${skTimeAgo(n.created_at)}</div>
            </div>
          </div>
        `).join("") || '<div class="sk-empty">No updates yet</div>'}
      </div>
    `;
    content().querySelectorAll("[data-pref]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await SukoonAPI.patch("/api/family/notification-preference", { notification_preference: btn.dataset.pref });
          skToast("Preference saved", "good");
          renderUpdates();
        } catch (err) { skToast(err.message, "critical"); }
      });
    });
  }

  // ---- Family & Contacts (family tree + call-for-comfort management) -----------
  const CONTACT_TYPE_ICON = { family: "👨‍👩‍👧", caregiver: "🧑‍🤝‍🧑", nurse: "👩‍⚕️", other: "👤" };
  let contactsCache = [];
  let editingContactId = null;

  async function renderContacts() {
    content().innerHTML = `${patientHeader()}<div class="sk-loading">Loading…</div>`;
    contactsCache = await SukoonAPI.get(`/api/family/contacts/${selectedPatientId}`);
    const p = dashboard.patient;
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-card" style="margin-bottom:18px;">
        <h3 style="margin-top:0;">📞 Call the patient</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">Set the patient's phone number so you can reach them directly, e.g. if they seem upset or miss a check-in.</p>
        <form id="patientPhoneForm" class="fm-form-row" style="align-items:end;">
          <div class="sk-field" style="margin-bottom:0;"><label>Patient's phone number</label><input name="phone" value="${p.phone ? skEscape(p.phone) : ""}" placeholder="+91 ..."></div>
          <button class="sk-btn sk-btn-secondary" type="submit">Save number</button>
        </form>
        ${p.phone ? `<button class="sk-btn sk-btn-primary" id="callPatientBtn" style="margin-top:12px;">📞 Call ${skEscape(p.full_name)} now</button>` : ""}
      </div>

      <div class="sk-card">
        <h3 style="margin-top:0;">Family tree &amp; call list</h3>
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">These are the people shown on the patient's own "My Family" screen, with photos to help them remember who's who — and who they can call if they're upset.</p>
        <div id="contactCards">${contactsCache.map((c) => contactCardHtml(c)).join("") || '<div class="sk-empty">No family members added yet</div>'}</div>
        <details style="margin-top:16px;" ${editingContactId ? "" : "open"}>
          <summary style="cursor:pointer; font-weight:600; color:var(--sukoon-teal-700);">+ Add family member / contact</summary>
          ${contactFormHtml(null)}
        </details>
      </div>
    `;

    document.getElementById("patientPhoneForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const phone = new FormData(e.target).get("phone");
      try {
        await SukoonAPI.put(`/api/family/patients/${selectedPatientId}/phone`, { phone });
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
        try { await SukoonAPI.del(`/api/family/contacts/${btn.dataset.deleteContact}`); skToast("Removed", "good"); editingContactId = null; renderContacts(); }
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
        <div class="fm-form-row">
          <div class="sk-field"><label>Name</label><input name="name" required value="${c ? skEscape(c.name) : ""}"></div>
          <div class="sk-field"><label>Relationship</label><input name="relationship_label" placeholder="e.g. Son, Visiting Nurse" value="${c ? skEscape(c.relationship_label || "") : ""}"></div>
        </div>
        <div class="fm-form-row">
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
          await SukoonAPI.put(`/api/family/contacts/${existing.id}`, payload);
          skToast("Saved", "good");
          editingContactId = null;
        } else {
          payload.patient_id = selectedPatientId;
          payload.display_order = 99;
          await SukoonAPI.post("/api/family/contacts", payload);
          skToast("Added", "good");
        }
        renderContacts();
      } catch (err) { skToast(err.message, "critical"); }
    });
  }

  // ---- Location & wearable (read-only map) --------------------------------------
  function renderSafety() {
    const d = dashboard;
    const sz = d.safe_zone;
    content().innerHTML = `
      ${patientHeader()}
      <div class="sk-disclaimer" style="margin-bottom:16px;">This is a safety feature, not covert surveillance. Location tracking requires explicit authorization and can be turned off at any time by the caregiver.</div>
      <div class="sk-card" style="margin-bottom:18px;">
        <h3 style="margin-top:0;">Live map <span class="sk-badge sk-badge-demo">Demo Data</span></h3>
        <div id="safetyMap" style="height:340px; border-radius:10px; overflow:hidden; border:1px solid var(--sukoon-line);"></div>
      </div>
      <div class="sk-grid sk-grid-2">
        <div class="sk-card">
          <h3 style="margin-top:0;">Safe zone status</h3>
          ${d.location_latest ? `<div style="margin-top:6px;">${d.location_latest.within_safe_zone ? "✅ Within safe zone" : "⚠️ Outside safe zone"} — ${d.location_latest.distance_from_safe_zone_m}m from ${sz ? skEscape(sz.label) : "home"}<br><span style="color:var(--sukoon-ink-500); font-size:0.8rem;">${skTimeAgo(d.location_latest.timestamp)}</span></div>` : '<div class="sk-empty">No location data yet</div>'}
        </div>
        <div class="sk-card">
          <h3 style="margin-top:0;">SafeTag Tracker™ — live vitals <span class="sk-badge sk-badge-demo">Demo Data</span></h3>
          ${d.wearable_latest ? `
            <div class="stat-row">
              <span class="stat-chip">❤️ ${d.wearable_latest.heart_rate_bpm} bpm</span>
              <span class="stat-chip">👣 ${d.wearable_latest.steps} steps</span>
              <span class="stat-chip">⚡ ${d.wearable_latest.activity_level}</span>
              <span class="stat-chip">🔋 ${d.wearable_latest.battery_pct}%</span>
            </div>
            <div style="color:var(--sukoon-ink-500); font-size:0.8rem;">${skTimeAgo(d.wearable_latest.timestamp)}</div>
          ` : '<div class="sk-empty">No wearable data yet</div>'}
        </div>
      </div>
    `;
    renderSafetyMap(d.location_latest, sz);
  }

  function renderSafetyMap(loc, sz) {
    const mapDiv = document.getElementById("safetyMap");
    if (!mapDiv || typeof L === "undefined") return;
    const centerLat = sz ? sz.center_lat : 26.1445;
    const centerLng = sz ? sz.center_lng : 91.7362;
    if (safetyMap) { safetyMap.remove(); safetyMap = null; }
    safetyMap = L.map(mapDiv, { scrollWheelZoom: false }).setView([centerLat, centerLng], 14);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: '&copy; OpenStreetMap contributors', maxZoom: 19 }).addTo(safetyMap);
    L.marker([centerLat, centerLng]).addTo(safetyMap).bindPopup(`🏠 ${sz ? skEscape(sz.label) : "Home"} (safe zone centre)`);
    if (sz) L.circle([centerLat, centerLng], { radius: sz.radius_m, color: "#1f9d8a", fillColor: "#1f9d8a", fillOpacity: 0.12, weight: 2 }).addTo(safetyMap);
    if (loc) {
      const icon = L.divIcon({ className: "", html: `<div style="font-size:26px; transform:translate(-50%,-90%);">${loc.within_safe_zone ? "🟢" : "🔴"}</div>`, iconSize: [0, 0] });
      L.marker([loc.latitude, loc.longitude], { icon }).addTo(safetyMap).bindPopup(`${loc.within_safe_zone ? "✅ Within safe zone" : "⚠️ Outside safe zone"}`).openPopup();
      safetyMap.fitBounds(L.latLngBounds([[centerLat, centerLng], [loc.latitude, loc.longitude]]).pad(0.4));
    }
    setTimeout(() => safetyMap && safetyMap.invalidateSize(), 150);
  }

  // ---- Alerts (read-only) --------------------------------------------------------
  function renderAlerts() {
    const alerts = dashboard.alerts || [];
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
            ${a.acknowledged ? '<span class="sk-badge sk-badge-good">Acknowledged</span>' : '<span class="sk-badge sk-badge-neutral">Open</span>'}
          </div>
        `).join("") || '<div class="sk-empty">No alerts</div>'}
        <p style="color:var(--sukoon-ink-500); font-size:0.8rem; margin-top:10px;">Alerts are acknowledged from the Caregiver dashboard.</p>
      </div>
    `;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
