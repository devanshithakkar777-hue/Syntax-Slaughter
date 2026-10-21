/* Sukoon — Doctor dashboard controller.
   Clinical, less gamified than the caregiver view. Every section respects
   the authorization scope returned by the API — a section the doctor was
   not granted simply doesn't render, rather than showing empty/fake data. */

(() => {
  let user = null;
  let patients = [];
  let selectedId = null;
  let dashboard = null;
  let activeTab = "overview";
  let chartInstance = null;

  const DOMAIN_BY_ACTIVITY = {
    memory_matching: "Memory", pattern_recognition: "Attention",
    object_recognition: "Recognition", routine_recall: "Engagement",
  };

  const content = () => document.getElementById("drContent");

  async function init() {
    user = skRequireAuth("doctor");
    if (!user) return;
    document.getElementById("drUserName").textContent = user.full_name;
    document.getElementById("logoutBtn").addEventListener("click", skLogout);
    document.querySelectorAll(".dr-tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
    if (typeof SukoonVoice !== "undefined") SukoonVoice.attachReadAloud(content());

    try {
      patients = await SukoonAPI.get("/api/doctor/patients");
    } catch (e) {
      content().innerHTML = `<div class="sk-empty">${e.message}</div>`;
      return;
    }
    renderPatientList();
    if (patients.length) selectPatient(patients[0].id);
    else content().innerHTML = `<div class="sk-card"><strong>No authorized patients yet.</strong><p style="color:var(--sukoon-ink-500); font-size:0.9rem; margin-top:8px;">A caregiver must explicitly request and the patient/caregiver must approve before any patient data appears here.</p></div>`;
  }

  function renderPatientList() {
    const list = document.getElementById("patientList");
    list.innerHTML = "";
    patients.forEach((p) => {
      const el = document.createElement("div");
      el.className = "dr-patient-item" + (p.id === selectedId ? " active" : "");
      el.innerHTML = `<strong>${skEscape(p.full_name)}</strong><div style="font-size:0.78rem; color:var(--sukoon-ink-500);">${p.age ? p.age + " yrs" : ""}</div>`;
      el.addEventListener("click", () => selectPatient(p.id));
      list.appendChild(el);
    });
  }

  async function selectPatient(id) {
    selectedId = id;
    renderPatientList();
    document.getElementById("drTabs").style.display = "flex";
    content().innerHTML = `<div class="sk-loading">Loading clinical dashboard…</div>`;
    try {
      dashboard = await SukoonAPI.get(`/api/doctor/patients/${id}/dashboard`);
    } catch (e) {
      content().innerHTML = `<div class="sk-empty">${e.message}</div>`;
      return;
    }
    switchTab("overview");
  }

  function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll(".dr-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
    if (tab === "overview") renderOverview();
    else if (tab === "agents") renderAgents();
    else if (tab === "appointments") renderAppointments();
    else renderMedicalRecords();
  }

  function drPatientHeader() {
    const p = dashboard.patient;
    return `
      <div class="sk-card" style="margin-bottom:18px;">
        <div style="font-size:1.3rem; font-weight:800;">${skEscape(p.full_name)}</div>
        <div style="color:var(--sukoon-ink-500); font-size:0.88rem;">${p.age ? p.age + " years · " : ""}${skEscape(p.gender || "")} · ${skEscape(p.home_region || "")}</div>
      </div>
    `;
  }

  // ---- AI Care Agent Network -------------------------------------------
  async function renderAgents() {
    content().innerHTML = `${drPatientHeader()}<div class="sk-loading">Waking up the care agent network…</div>`;
    let data;
    try {
      data = await SukoonAPI.get(`/api/doctor/patients/${selectedId}/agentic`);
    } catch (e) {
      content().innerHTML = `${drPatientHeader()}<div class="sk-empty">${e.message}</div>`;
      return;
    }
    content().innerHTML = drPatientHeader() + renderAgentNetworkHTML(data);
    wireAgentNetworkExtras("/api/doctor", selectedId, patients);
  }

  function renderOverview() {
    const d = dashboard;
    const p = d.patient;
    content().innerHTML = `
      <div class="sk-card">
        <div style="font-size:1.3rem; font-weight:800;">${skEscape(p.full_name)}</div>
        <div style="color:var(--sukoon-ink-500); font-size:0.88rem;">${p.age ? p.age + " years · " : ""}${skEscape(p.gender || "")} · ${skEscape(p.home_region || "")}</div>
        <div style="margin-top:8px; font-size:0.85rem; color:var(--sukoon-ink-700);">${skEscape(p.condition_notes || "")}</div>
      </div>

      <div class="sk-disclaimer" style="margin-top:16px;">
        ${skEscape(d.disclaimer)} Sukoon does not diagnose or treat dementia — this is supportive information only.
      </div>

      <div class="dr-section-title">Access granted to you</div>
      <div class="sk-card" style="font-size:0.85rem;">
        ${scopeRow("Cognitive performance / activity history", d.authorization.scope_cognitive_performance || d.authorization.scope_activity_history)}
        ${scopeRow("Reminder adherence", d.authorization.scope_reminder_adherence)}
        ${scopeRow("Wearable data", d.authorization.scope_wearable_data)}
        ${scopeRow("Location", d.authorization.scope_location)}
        ${scopeRow("Medical records", d.authorization.scope_medical_records)}
      </div>

      ${d.performance_30d !== null ? `
        <div class="dr-section-title">Cognitive activity trend (30 days)</div>
        <div class="sk-card"><div class="chart-wrap"><canvas id="perfChart"></canvas></div></div>
      ` : ""}

      ${d.reminder_adherence !== null ? `
        <div class="dr-section-title">Reminder adherence (recent)</div>
        <div class="sk-card">
          <table class="sk-table">
            <thead><tr><th>Date</th><th>Reminder</th><th>Status</th></tr></thead>
            <tbody>${d.reminder_adherence.slice(0, 12).map((r) => `<tr><td>${r.date}</td><td>${skEscape(r.title_en)}</td><td>${r.status}</td></tr>`).join("") || '<tr><td colspan="3" class="sk-empty">No data</td></tr>'}</tbody>
          </table>
        </div>
      ` : ""}

      ${d.wearable_recent !== null ? `
        <div class="dr-section-title">SafeTag Tracker™ — wearable data (recent) <span class="sk-badge sk-badge-demo">Demo Data</span></div>
        <div class="sk-card">
          ${d.wearable_recent.length ? `<div class="stat-row" style="display:flex; gap:10px; flex-wrap:wrap;">
            <span class="stat-chip">❤️ Latest: ${d.wearable_recent[0].heart_rate_bpm} bpm</span>
            <span class="stat-chip">👣 ${d.wearable_recent[0].steps} steps</span>
          </div>` : '<div class="sk-empty">No wearable data yet</div>'}
        </div>
      ` : ""}

      ${d.location_latest !== null ? `
        <div class="dr-section-title">Location</div>
        <div class="sk-card">
          <div style="margin-bottom:8px;">${d.location_latest ? (d.location_latest.within_safe_zone ? "✅ Within configured safe zone" : "⚠️ Outside configured safe zone") : "No location data"} <span class="sk-badge sk-badge-demo">Demo Data</span></div>
          ${d.location_latest ? `<div id="drMap" style="height:240px; border-radius:10px; overflow:hidden; border:1px solid var(--sukoon-line);"></div>` : ""}
        </div>
      ` : ""}

      <div class="dr-section-title">Recent safety alerts</div>
      <div class="sk-card">
        ${d.recent_alerts.map((a) => `<div style="padding:8px 0; border-bottom:1px solid var(--sukoon-line); font-size:0.85rem;">${skEscape(a.message_en)} <span style="color:var(--sukoon-ink-500);">— ${skTimeAgo(a.created_at)}</span></div>`).join("") || '<div class="sk-empty">No alerts</div>'}
      </div>

      <div class="sk-disclaimer" style="margin:20px 0 4px; font-weight:600;">
        Clinical decisions should not be based solely on Sukoon.
      </div>
    `;

    if (d.performance_30d !== null) renderChart(d.performance_30d);
    if (d.location_latest) renderDrMap(d.location_latest, d.safe_zone);
  }

  let drMap = null;
  function renderDrMap(loc, sz) {
    const mapDiv = document.getElementById("drMap");
    if (!mapDiv || typeof L === "undefined") return;
    if (drMap) { drMap.remove(); drMap = null; }
    drMap = L.map(mapDiv, { scrollWheelZoom: false }).setView([loc.latitude, loc.longitude], 14);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; OpenStreetMap contributors', maxZoom: 19,
    }).addTo(drMap);
    if (sz) {
      L.circle([sz.center_lat, sz.center_lng], { radius: sz.radius_m, color: "#1f9d8a", fillColor: "#1f9d8a", fillOpacity: 0.12, weight: 2 }).addTo(drMap);
    }
    const icon = L.divIcon({ className: "", html: `<div style="font-size:24px; transform:translate(-50%,-90%);">${loc.within_safe_zone ? "🟢" : "🔴"}</div>`, iconSize: [0, 0] });
    L.marker([loc.latitude, loc.longitude], { icon }).addTo(drMap).bindPopup(`${loc.within_safe_zone ? "Within safe zone" : "Outside safe zone"}`).openPopup();
    setTimeout(() => drMap && drMap.invalidateSize(), 150);
  }

  function scopeRow(label, granted) {
    return `<div style="padding:6px 0;">${granted ? "✓" : "✕"} ${label}</div>`;
  }

  // ---- Appointments (with virtual visit join) ---------------------------------
  async function renderAppointments() {
    content().innerHTML = `<div class="sk-loading">Loading appointments…</div>`;
    let appts;
    try {
      appts = await SukoonAPI.get(`/api/doctor/patients/${selectedId}/appointments`);
    } catch (e) {
      content().innerHTML = `<div class="sk-empty">${e.message}</div>`;
      return;
    }
    content().innerHTML = `
      <div class="dr-section-title">Appointments — ${skEscape(dashboard.patient.full_name)}</div>
      <div class="sk-card">
        <p style="color:var(--sukoon-ink-500); font-size:0.85rem; margin-top:-6px;">Start the same free video room the patient and family will join — no download or sign-up needed.</p>
        <table class="sk-table">
          <thead><tr><th>Date</th><th>Location</th><th></th></tr></thead>
          <tbody>${appts.map((a) => `<tr><td>${a.date} ${a.time}</td><td>${skEscape(a.location || a.hospital_or_clinic || "")}</td><td><a class="sk-btn sk-btn-secondary" href="${a.virtual_meeting_url}" target="_blank" rel="noopener">🎥 Start / Join</a></td></tr>`).join("") || '<tr><td colspan="3" class="sk-empty">No appointments yet</td></tr>'}</tbody>
        </table>
      </div>
    `;
  }

  // ---- Medical records (hospital-file style) ---------------------------------
  async function renderMedicalRecords() {
    if (dashboard.authorization && dashboard.authorization.scope_medical_records === false) {
      content().innerHTML = `<div class="sk-card"><strong>Medical records access not granted.</strong><p style="color:var(--sukoon-ink-500); font-size:0.88rem; margin-top:8px;">The patient's family has not authorized you to view or write medical records for this patient.</p></div>`;
      return;
    }
    content().innerHTML = `<div class="sk-loading">Loading medical records…</div>`;
    let records, appts;
    try {
      [records, appts] = await Promise.all([
        SukoonAPI.get(`/api/doctor/patients/${selectedId}/medical-records`),
        SukoonAPI.get(`/api/doctor/patients/${selectedId}/appointments`),
      ]);
    } catch (e) {
      content().innerHTML = `<div class="sk-empty">${e.message}</div>`;
      return;
    }
    const openAppts = appts.filter((a) => !a.has_medical_record);

    content().innerHTML = `
      <div class="dr-section-title">Hospital file — ${skEscape(dashboard.patient.full_name)}</div>
      ${records.map(fileCardHtml).join("") || '<div class="sk-card"><div class="sk-empty">No visit records yet</div></div>'}

      <div class="sk-card" style="margin-top:8px;">
        <h3 style="margin-top:0; font-size:0.95rem;">+ Add visit / diagnosis record</h3>
        ${openAppts.length ? `
          <form id="recordForm">
            <div class="sk-field"><label>Appointment</label>
              <select name="appointment_id" required>
                ${openAppts.map((a) => `<option value="${a.id}">${a.date} ${a.time} — ${skEscape(a.hospital_or_clinic || a.location || "")}</option>`).join("")}
              </select>
            </div>
            <div class="cg-form-row">
              <div class="sk-field"><label>Visit date</label><input type="date" name="visit_date" required></div>
              <div class="sk-field"><label>Follow-up date (optional)</label><input type="date" name="follow_up_date"></div>
            </div>
            <div class="sk-field"><label>Chief complaint</label><input name="chief_complaint" placeholder="e.g. Forgetfulness, disorientation in evenings"></div>
            <div class="sk-field"><label>Diagnosis</label><textarea name="diagnosis" rows="2" required placeholder="e.g. Mild cognitive impairment, consistent with early-stage dementia — clinical correlation advised"></textarea></div>
            <div class="sk-field"><label>Prescription</label><textarea name="prescription" rows="2" placeholder="Drug — dose — duration, one per line"></textarea></div>
            <div class="cg-form-row">
              <div class="sk-field"><label>BP</label><input name="vitals_bp" placeholder="130/85 mmHg"></div>
              <div class="sk-field"><label>Pulse</label><input name="vitals_pulse" placeholder="76 bpm"></div>
              <div class="sk-field"><label>Weight (kg)</label><input name="vitals_weight_kg" type="number" step="0.1"></div>
            </div>
            <div class="sk-field"><label>Follow-up instructions</label><input name="follow_up_instructions" placeholder="e.g. Review in 4 weeks; monitor mood check-ins"></div>
            <button class="sk-btn sk-btn-primary" type="submit" style="margin-top:8px;">Save record</button>
          </form>
        ` : '<div class="sk-empty">Every appointment already has a record. Ask the family to add a new appointment to write another visit note.</div>'}
      </div>
    `;

    const form = document.getElementById("recordForm");
    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = Object.fromEntries(fd.entries());
        payload.patient_id = selectedId;
        if (payload.vitals_weight_kg) payload.vitals_weight_kg = parseFloat(payload.vitals_weight_kg);
        else delete payload.vitals_weight_kg;
        try {
          await SukoonAPI.post("/api/doctor/medical-records", payload);
          skToast("Medical record saved", "good");
          renderMedicalRecords();
        } catch (err) { skToast(err.message, "critical"); }
      });
    }
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

  function renderChart(perf) {
    const canvas = document.getElementById("perfChart");
    if (!canvas || typeof Chart === "undefined") return;
    const byDate = {};
    perf.forEach((r) => {
      const date = (r.timestamp || "").slice(0, 10);
      const domain = DOMAIN_BY_ACTIVITY[r.activity_code] || "Other";
      byDate[date] = byDate[date] || {};
      byDate[date][domain] = byDate[date][domain] || [];
      byDate[date][domain].push(r.accuracy);
    });
    const dates = Object.keys(byDate).sort();
    const domains = ["Memory", "Attention", "Recognition", "Engagement"];
    const colors = { Memory: "#1f9d8a", Attention: "#c98a1f", Recognition: "#2f6fb0", Engagement: "#8e5fc9" };
    const datasets = domains.map((d) => ({
      label: d, borderColor: colors[d], backgroundColor: colors[d], spanGaps: true, tension: 0.25,
      data: dates.map((date) => {
        const vals = (byDate[date] || {})[d];
        return vals ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) : null;
      }),
    }));
    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(canvas, {
      type: "line",
      data: { labels: dates.map((d) => d.slice(5)), datasets },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100 } }, plugins: { legend: { position: "bottom" } } },
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
