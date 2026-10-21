/* Sukoon — thin fetch wrapper: attaches JWT, handles JSON, surfaces errors. */

const SukoonAPI = (() => {
  const TOKEN_KEY = "sukoon_token";
  const USER_KEY = "sukoon_user";
  const PROFILE_KEY = "sukoon_profile_id";

  function getToken() { return localStorage.getItem(TOKEN_KEY); }
  function getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch (e) { return null; }
  }
  function getProfileId() { return localStorage.getItem(PROFILE_KEY); }

  function setSession(token, user, profileId) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    if (profileId) localStorage.setItem(PROFILE_KEY, profileId);
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(PROFILE_KEY);
  }

  async function request(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    let res;
    try {
      res = await fetch(path, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (networkErr) {
      const err = new Error("You appear to be offline.");
      err.offline = true;
      throw err;
    }

    if (res.status === 401) {
      clearSession();
      if (!location.pathname.endsWith("/") && !location.pathname.endsWith("index.html")) {
        location.href = "/";
      }
      throw new Error("Session expired. Please log in again.");
    }

    let data = null;
    const text = await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = text; }
    }

    if (!res.ok) {
      const detail = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
      const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  return {
    get: (path) => request("GET", path),
    post: (path, body) => request("POST", path, body === undefined ? {} : body),
    put: (path, body) => request("PUT", path, body === undefined ? {} : body),
    patch: (path, body) => request("PATCH", path, body === undefined ? {} : body),
    del: (path) => request("DELETE", path),
    getToken, getUser, getProfileId, setSession, clearSession,
  };
})();
