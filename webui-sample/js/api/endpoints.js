function qp(params = {}) {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    usp.set(k, String(v));
  });
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export function createApi(client) {
  return {
    auth: {
      login(payload) { return client.request("/auth/login", { method: "POST", body: payload }); },
      me() { return client.request("/auth/me"); },
      logout() { return client.request("/auth/logout", { method: "POST" }); },
    },
    system: {
      status() { return client.request("/system/status"); },
    },
    services: {
      list() { return client.request("/services"); }, // may not exist yet; caller should fallback
      restart(service_name) { return client.request("/services/restart", { method: "POST", body: { service_name } }); },
    },
    logs: {
      get(service_name, params = {}) { return client.request(`/logs/${encodeURIComponent(service_name)}${qp(params)}`); },
    },
    processes: {
      list(params = {}) { return client.request(`/v1/processes${qp(params)}`); },
    },
    cron: {
      list(params = {}) { return client.request(`/cron${qp(params)}`); },
      create(payload) { return client.request("/cron", { method: "POST", body: payload }); },
      delete(jobId, reason) { return client.request(`/cron/${encodeURIComponent(jobId)}${qp({ reason })}`, { method: "DELETE" }); },
      toggle(jobId, payload) { return client.request(`/cron/${encodeURIComponent(jobId)}`, { method: "PATCH", body: payload }); },
    },
    users: {
      list() { return client.request("/users"); },
      detail(uid) { return client.request(`/users/${encodeURIComponent(uid)}`); },
      create(payload) { return client.request("/users", { method: "POST", body: payload }); },
      delete(uid, payload = {}) { return client.request(`/users/${encodeURIComponent(uid)}`, { method: "DELETE", body: payload }); },
      changePassword(uid, payload) { return client.request(`/users/${encodeURIComponent(uid)}/password`, { method: "PUT", body: payload }); },
      listGroups() { return client.request("/groups"); },
      createGroup(payload) { return client.request("/groups", { method: "POST", body: payload }); },
      deleteGroup(gid, payload = {}) { return client.request(`/groups/${encodeURIComponent(gid)}`, { method: "DELETE", body: payload }); },
      updateGroupMembers(gid, payload) { return client.request(`/groups/${encodeURIComponent(gid)}/members`, { method: "PUT", body: payload }); },
    },
    approvals: {
      create(payload) { return client.request("/approval/request", { method: "POST", body: payload }); },
      pending(params = {}) { return client.request(`/approval/pending${qp(params)}`); },
      myRequests(params = {}) { return client.request(`/approval/my-requests${qp(params)}`); },
      detail(id) { return client.request(`/approval/${encodeURIComponent(id)}`); },
      approve(id, payload = {}) { return client.request(`/approval/${encodeURIComponent(id)}/approve`, { method: "POST", body: payload }); },
      reject(id, payload) { return client.request(`/approval/${encodeURIComponent(id)}/reject`, { method: "POST", body: payload }); },
      cancel(id, payload = {}) { return client.request(`/approval/${encodeURIComponent(id)}/cancel`, { method: "POST", body: payload }); },
      execute(id, payload = {}) { return client.request(`/approval/${encodeURIComponent(id)}/execute`, { method: "POST", body: payload }); },
      history(params = {}) { return client.request(`/approval/history${qp(params)}`); },
      policies() { return client.request("/approval/policies"); },
      stats(params = {}) { return client.request(`/approval/stats${qp(params)}`); },
    },
  };
}

