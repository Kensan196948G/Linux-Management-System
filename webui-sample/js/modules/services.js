export function normalizeLogsPayload(payload) {
  const root = payload?.data ?? payload ?? {};
  const lines = root.logs || root.lines || root.entries || [];
  return {
    status: root.status || "success",
    service_name: root.service_name || root.service || null,
    line_count: Number(root.line_count ?? lines.length),
    logs: Array.isArray(lines) ? lines.map(String) : [],
    timestamp: root.timestamp || null,
  };
}

export function normalizeServiceRestartPayload(payload) {
  const root = payload?.data ?? payload ?? {};
  return {
    status: root.status || "success",
    service_name: root.service_name || null,
    previous_status: root.previous_status || null,
    current_status: root.current_status || root.status_value || null,
    message: root.message || "",
    timestamp: root.timestamp || null,
  };
}

