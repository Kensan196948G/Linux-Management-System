export function normalizeApprovalStatus(value) {
  const v = String(value || "").toLowerCase();
  const known = ["pending", "approved", "rejected", "expired", "executed", "execution_failed", "cancelled"];
  return known.includes(v) ? v : "pending";
}

export function normalizeApprovalRisk(value) {
  const v = String(value || "").toUpperCase();
  return ["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(v) ? v : "MEDIUM";
}

export function normalizeApprovalListPayload(payload, mode = "pending") {
  const root = payload?.data ?? payload ?? {};
  const source = root.requests || root.items || root.data || [];
  const requests = Array.isArray(source) ? source.map((r) => normalizeApprovalListItem(r, mode)).filter(Boolean) : [];
  return {
    status: root.status || "success",
    total: Number(root.total ?? requests.length),
    page: Number(root.page ?? 1),
    per_page: Number(root.per_page ?? (requests.length || 20)),
    requests,
  };
}

export function normalizeApprovalListItem(item, mode = "pending") {
  if (!item || typeof item !== "object") return null;
  const id = String(item.id || item.request_id || "");
  if (!id) return null;
  return {
    id,
    request_type: String(item.request_type || item.operation_type || "unknown"),
    request_type_description: String(item.request_type_description || item.description || item.request_type || ""),
    risk_level: normalizeApprovalRisk(item.risk_level || item.risk || "MEDIUM"),
    requester_id: String(item.requester_id || ""),
    requester_name: String(item.requester_name || item.requester || ""),
    reason: String(item.reason || ""),
    status: normalizeApprovalStatus(item.status || (mode === "pending" ? "pending" : "")),
    created_at: item.created_at || null,
    expires_at: item.expires_at || null,
    remaining_hours: Number(item.remaining_hours ?? 0),
    payload_summary: String(item.payload_summary || ""),
    approved_by_name: item.approved_by_name ?? null,
    approved_at: item.approved_at ?? null,
    rejection_reason: item.rejection_reason ?? null,
  };
}

export function normalizeApprovalDetailPayload(payload) {
  const root = payload?.data ?? payload ?? {};
  const req = root.request || root.data || root;
  if (!req || typeof req !== "object") return null;
  return {
    id: String(req.id || req.request_id || ""),
    request_type: String(req.request_type || "unknown"),
    request_type_description: String(req.request_type_description || req.request_type || ""),
    risk_level: normalizeApprovalRisk(req.risk_level || req.risk || "MEDIUM"),
    requester_id: String(req.requester_id || ""),
    requester_name: String(req.requester_name || req.requester || ""),
    request_payload: req.request_payload || req.payload || {},
    reason: String(req.reason || ""),
    status: normalizeApprovalStatus(req.status),
    created_at: req.created_at || null,
    expires_at: req.expires_at || null,
    approved_by: req.approved_by || null,
    approved_by_name: req.approved_by_name || null,
    approved_at: req.approved_at || null,
    rejection_reason: req.rejection_reason || null,
    execution_result: req.execution_result || null,
    executed_at: req.executed_at || null,
    history: Array.isArray(req.history) ? req.history : [],
  };
}

export function normalizeApprovalActionResponse(payload, fallbackStatus) {
  const root = payload?.data ?? payload ?? {};
  return {
    status: root.status || "success",
    message: root.message || "",
    request_id: root.request_id || root.id || "",
    next_status: normalizeApprovalStatus(root.status_value || fallbackStatus || "pending"),
    raw: root,
  };
}
