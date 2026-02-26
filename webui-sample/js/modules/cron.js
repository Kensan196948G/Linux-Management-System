export function normalizeCronListPayload(payload) {
  const root = payload?.data ?? payload ?? {};
  const jobs = Array.isArray(root.jobs) ? root.jobs : [];
  return {
    status: root.status || "success",
    user: root.user || null,
    total_count: Number(root.total_count ?? jobs.length),
    max_allowed: Number(root.max_allowed ?? 10),
    jobs: jobs.map((job) => ({
      id: String(job.id || ""),
      owner: String(job.user || job.owner || root.user || ""),
      schedule: String(job.schedule || ""),
      schedule_human: String(job.schedule_human || ""),
      command: String(job.command || ""),
      arguments: String(job.arguments || ""),
      enabled: Boolean(job.enabled),
      created_at: job.created_at || null,
      created_by: job.created_by || null,
    })).filter((j) => j.id),
  };
}

export function normalizeApprovalPendingResponse(payload) {
  const root = payload?.data ?? payload ?? {};
  return {
    status: String(root.status || ""),
    request_id: String(root.request_id || root.approval_id || ""),
    message: String(root.message || ""),
  };
}

