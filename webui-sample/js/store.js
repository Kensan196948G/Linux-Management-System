import { APP_KEYS } from "./config.js";

export function createUiStore() {
  const ui = {
    filters: {
      processes: { sort_by: "cpu", filter_user: "", min_cpu: 0, min_mem: 0, limit: 100 },
      approvals: { pending: {}, my: {}, history: { period: "30d" } },
      cron: {},
      users: {},
      logs: {},
    },
    selected: {
      processId: null,
      approvalId: null,
      service: "nginx",
    },
    modal: {
      name: null,
      payload: null,
    },
  };

  return {
    getSession() {
      try { return JSON.parse(localStorage.getItem(APP_KEYS.session) || "null"); } catch { return null; }
    },
    setSession(session) {
      localStorage.setItem(APP_KEYS.session, JSON.stringify(session));
    },
    clearSession() {
      localStorage.removeItem(APP_KEYS.session);
    },
    ui,
  };
}

