/* Sukoon — minimal EN/Assamese dictionary for shared UI chrome.
   Architected so more languages (per NER requirements) can be added by
   extending this table only — no other code needs to change. */

const SukoonI18N = (() => {
  const DICT = {
    good_morning: { en: "Good Morning", as: "শুভ ৰাতিপুৱা" },
    today_routine: { en: "Today's Routine", as: "আজিৰ কাৰ্যসূচী" },
    cognitive_activity: { en: "Today's Cognitive Activity", as: "আজিৰ জ্ঞানমূলক কাৰ্যকলাপ" },
    next_medicine: { en: "Next Medicine", as: "পৰৱৰ্তী ঔষধ" },
    hydration: { en: "Hydration", as: "জলপান" },
    doctor_appointment: { en: "Doctor Appointment", as: "চিকিৎসকৰ সাক্ষাৎ" },
    mood: { en: "Mood", as: "মন-ভাব" },
    help: { en: "Help", as: "সহায়" },
    play_now: { en: "Play now", as: "এতিয়া খেলক" },
    view: { en: "View", as: "চাওক" },
    mark_taken: { en: "Mark as taken", as: "লোৱা হ'ল বুলি চিহ্নিত কৰক" },
    completed: { en: "Completed", as: "সম্পূৰ্ণ" },
    pending: { en: "Pending", as: "বাকী আছে" },
    how_are_you_feeling: { en: "How are you feeling today?", as: "আজি আপুনি কেনে অনুভৱ কৰিছে?" },
    logout: { en: "Log out", as: "লগ আউট" },
    offline_msg: { en: "Offline — data will sync when connection is restored.", as: "অফলাইন — সংযোগ পুনৰুদ্ধাৰ হ'লে তথ্য ছিংক হ'ব।" },
    synced_msg: { en: "Synced", as: "ছিংক সম্পূৰ্ণ" },
    good: { en: "Good", as: "ভাল" },
    okay: { en: "Okay", as: "ঠিকেই আছে" },
    unsure: { en: "Not sure", as: "নিশ্চিত নহয়" },
    sad: { en: "Sad", as: "দুখী" },
    my_family: { en: "My Family", as: "মোৰ পৰিয়াল" },
  };

  let currentLang = localStorage.getItem("sukoon_lang") || "en";

  function t(key) {
    const entry = DICT[key];
    if (!entry) return key;
    return entry[currentLang] || entry.en;
  }

  function setLang(lang) {
    currentLang = lang;
    localStorage.setItem("sukoon_lang", lang);
    document.dispatchEvent(new CustomEvent("sukoon:lang-changed", { detail: { lang } }));
  }

  function getLang() { return currentLang; }

  return { t, setLang, getLang };
})();
