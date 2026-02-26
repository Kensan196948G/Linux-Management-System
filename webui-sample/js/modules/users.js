export function normalizeUsersListPayload(payload) {
  const root = payload?.data ?? payload ?? {};
  const users = Array.isArray(root.users) ? root.users : [];
  return {
    status: root.status || "success",
    total_count: Number(root.total_count ?? users.length),
    users: users.map((u) => ({
      username: String(u.username || ""),
      uid: Number(u.uid ?? 0),
      gid: Number(u.gid ?? 0),
      gecos: String(u.gecos || ""),
      home: String(u.home || u.home_dir || ""),
      shell: String(u.shell || ""),
      groups: Array.isArray(u.groups) ? u.groups.map(String) : [],
      locked: Boolean(u.locked),
      last_login: u.last_login || null,
    })).filter((u) => u.username),
    timestamp: root.timestamp || null,
  };
}

export function normalizeGroupsListPayload(payload) {
  const root = payload?.data ?? payload ?? {};
  const groups = Array.isArray(root.groups) ? root.groups : [];
  return {
    status: root.status || "success",
    total_count: Number(root.total_count ?? groups.length),
    groups: groups.map((g) => ({
      group: String(g.group || g.name || ""),
      gid: Number(g.gid ?? 0),
      members: Array.isArray(g.members) ? g.members.map(String) : [],
      risk: String(g.risk || "LOW").toUpperCase(),
    })).filter((g) => g.group),
    timestamp: root.timestamp || null,
  };
}

