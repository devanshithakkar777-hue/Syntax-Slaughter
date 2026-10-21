/* Sukoon — offline-first queue.
   While offline, patient actions (game sessions, mood check-ins, reminder
   responses) are written to localStorage instead of the network. When the
   browser comes back online, the whole queue is POSTed once to
   /api/sync/batch. Each item carries a client-generated idempotency key so
   a retried batch can never create duplicate records server-side. */

const SukoonOffline = (() => {
  const QUEUE_KEY = "sukoon_sync_queue";
  let banner = null;
  let syncing = false;

  function uuid() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function getQueue() {
    try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]"); } catch (e) { return []; }
  }
  function setQueue(q) { localStorage.setItem(QUEUE_KEY, JSON.stringify(q)); }

  function enqueue(entityType, payload) {
    const item = {
      client_generated_id: uuid(),
      entity_type: entityType,
      payload,
      created_offline_at: new Date().toISOString(),
    };
    const q = getQueue();
    q.push(item);
    setQueue(q);
    renderBanner();
    if (navigator.onLine) trySync();
    return item;
  }

  async function trySync() {
    const q = getQueue();
    if (!q.length || syncing || !navigator.onLine) return;
    syncing = true;
    try {
      const res = await SukoonAPI.post("/api/sync/batch", { items: q });
      const syncedIds = new Set(
        res.results.filter((r) => r.status === "synced" || r.status === "already_synced").map((r) => r.client_generated_id)
      );
      const remaining = q.filter((item) => !syncedIds.has(item.client_generated_id));
      setQueue(remaining);
      if (syncedIds.size > 0) {
        showSyncedBriefly();
        document.dispatchEvent(new CustomEvent("sukoon:synced"));
      }
    } catch (e) {
      // stays queued; will retry on next online event or enqueue
    } finally {
      syncing = false;
      renderBanner();
    }
  }

  function renderBanner() {
    if (!banner) return;
    const q = getQueue();
    if (!navigator.onLine) {
      banner.textContent = SukoonI18N.t("offline_msg") + (q.length ? `  (${q.length} pending)` : "");
      banner.className = "sk-offline-banner show";
    } else if (q.length > 0) {
      banner.textContent = `Syncing ${q.length} item(s)…`;
      banner.className = "sk-offline-banner show";
    } else {
      banner.className = "sk-offline-banner";
    }
  }

  function showSyncedBriefly() {
    if (!banner) return;
    banner.textContent = "✓ " + SukoonI18N.t("synced_msg");
    banner.className = "sk-offline-banner show synced";
    setTimeout(() => { banner.className = "sk-offline-banner"; }, 2200);
  }

  function init(bannerEl) {
    banner = bannerEl;
    window.addEventListener("online", () => { renderBanner(); trySync(); });
    window.addEventListener("offline", renderBanner);
    renderBanner();
    if (navigator.onLine) trySync();
  }

  function queueLength() { return getQueue().length; }
  function isOnline() { return navigator.onLine; }

  return { init, enqueue, trySync, queueLength, isOnline };
})();
