/* Sukoon — small shared UI helpers. */

function skToast(message, kind) {
  let wrap = document.querySelector(".sk-toast-wrap");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.className = "sk-toast-wrap";
    document.body.appendChild(wrap);
  }
  const el = document.createElement("div");
  el.className = "sk-toast" + (kind ? " " + kind : "");
  el.textContent = message;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function skEscape(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function skTimeAgo(isoString) {
  if (!isoString) return "";
  const then = new Date(isoString + (isoString.endsWith("Z") ? "" : "Z"));
  const diffMs = Date.now() - then.getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days > 1 ? "s" : ""} ago`;
}

function skRequireAuth(requiredRole) {
  const user = SukoonAPI.getUser();
  if (!user || !SukoonAPI.getToken()) {
    location.href = "/";
    return null;
  }
  if (requiredRole && user.role !== requiredRole) {
    location.href = "/";
    return null;
  }
  return user;
}

function skLogout() {
  SukoonAPI.post("/api/auth/logout").catch(() => {});
  SukoonAPI.clearSession();
  location.href = "/";
}
