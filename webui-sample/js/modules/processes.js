export function buildProcessesQuery(filters) {
  return {
    sort_by: filters.sort_by || "cpu",
    filter_user: filters.filter_user || undefined,
    min_cpu: Number(filters.min_cpu || 0) || 0,
    min_mem: Number(filters.min_mem || 0) || 0,
    limit: Number(filters.limit || 100) || 100,
  };
}

export function normalizeProcessesResponse(payload) {
  const root = payload?.data ?? payload ?? {};
  const list = root.processes || root.items || root.data || [];
  const rows = Array.isArray(list) ? list.map(normalizeProcessRow).filter(Boolean) : [];
  return {
    status: root.status || "success",
    sort_by: root.sort_by || "cpu",
    total_processes: Number(root.total_processes ?? root.total ?? rows.length),
    returned_processes: Number(root.returned_processes ?? rows.length),
    filters: root.filters || {
      user: root.filter_user || null,
      min_cpu: root.min_cpu ?? 0,
      min_mem: root.min_mem ?? 0,
    },
    processes: rows,
    timestamp: root.timestamp || new Date().toISOString(),
  };
}

export function normalizeProcessRow(row) {
  if (!row || typeof row !== "object") return null;
  const pid = Number(row.pid ?? row.process_id ?? 0);
  if (!Number.isFinite(pid) || pid <= 0) return null;
  return {
    pid,
    user: String(row.user ?? row.username ?? "unknown"),
    cpu_percent: toNumber(row.cpu_percent ?? row.cpu ?? row.cpuUsage ?? 0),
    mem_percent: toNumber(row.mem_percent ?? row.mem ?? row.memory ?? 0),
    vsz: toNumber(row.vsz ?? row.virtual_size ?? 0, true),
    rss: toNumber(row.rss ?? row.resident_size ?? 0, true),
    tty: String(row.tty ?? "?"),
    stat: String(row.stat ?? row.state ?? "S"),
    start: String(row.start ?? row.started ?? row.start_time ?? ""),
    time: String(row.time ?? row.cpu_time ?? "00:00:00"),
    command: String(row.command ?? row.cmd ?? row.name ?? ""),
  };
}

function toNumber(v, integer = false) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return integer ? Math.trunc(n) : n;
}

