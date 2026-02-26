#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const FILE = path.join(ROOT, "docs", "openapi.json");
const raw = fs.readFileSync(FILE, "utf8").replace(/^\uFEFF/, "");
const doc = JSON.parse(raw);

const ref = (name) => ({ $ref: `#/components/schemas/${name}` });
const resp = (schema, description = "OK", contentType = "application/json") => ({
  description,
  content: { [contentType]: { schema } },
});
const body = (schema, required = true) => ({ required, content: { "application/json": { schema } } });
const sec = [{ HTTPBearer: [] }];
const q = (name, schema, description) => ({ name, in: "query", required: false, schema, ...(description ? { description } : {}) });
const p = (name, schema) => ({ name, in: "path", required: true, schema });

function obj(properties, required = []) {
  return { type: "object", properties, required, additionalProperties: true };
}

function putSchema(name, schema) {
  doc.components ??= {};
  doc.components.schemas ??= {};
  doc.components.schemas[name] = schema;
}

function op({ tags, summary, description, permissions, permissionsAnyOf, parameters, requestBody, responses }) {
  const o = { tags, summary, description, responses, security: sec };
  if (parameters?.length) o.parameters = parameters;
  if (requestBody) o.requestBody = requestBody;
  if (permissions?.length) o["x-required-permissions"] = permissions;
  if (permissionsAnyOf?.length) o["x-required-permissions-anyOf"] = permissionsAnyOf;
  return o;
}

function addPath(url, method, config) {
  doc.paths ??= {};
  doc.paths[url] ??= {};
  doc.paths[url][method] = op(config);
}

function protectedResponses(main) {
  return {
    ...main,
    "401": resp(ref("ApiErrorResponse"), "Unauthorized"),
    "403": resp(ref("ApiErrorResponse"), "Forbidden"),
    "422": resp(ref("HTTPValidationError"), "Validation Error"),
  };
}

doc.info ??= {};
doc.info.version = "0.3.0-doc-sync";
doc.info.description = `${doc.info.description || "Linux Management System API"}\n\nv0.3 docs-sync: processes/cron/users-groups/approval endpoints synchronized.`;
doc["x-docs-sync"] = {
  synced_at: new Date().toISOString(),
  source_documents: [
    "docs/api/approval-api-spec.md",
    "docs/architecture/approval-workflow-design.md",
    "docs/architecture/cron-jobs-design.md",
    "docs/architecture/processes-module-design.md",
    "docs/architecture/users-groups-design.md",
  ],
  note: "x-required-permissions* are documentation extensions.",
};

putSchema("ApiErrorResponse", obj({
  status: { type: "string", enum: ["error"] },
  message: { type: "string" },
  detail: { oneOf: [{ type: "string" }, { type: "array", items: { type: "object", additionalProperties: true } }] },
  status_code: { type: "integer" },
  error_code: { type: "string" },
}, []));

putSchema("ApprovalStatus", { type: "string", enum: ["pending", "approved", "rejected", "expired", "executed", "execution_failed", "cancelled"] });
putSchema("ApprovalPendingResponse", obj({
  status: { type: "string", enum: ["approval_pending", "pending", "success"] },
  request_id: { type: "string" },
  message: { type: "string" },
}, ["status"]));

putSchema("ProcessRow", obj({
  pid: { type: "integer" }, user: { type: "string" }, cpu_percent: { type: "number" }, mem_percent: { type: "number" },
  vsz: { type: "integer" }, rss: { type: "integer" }, tty: { type: "string" }, stat: { type: "string" },
  start: { type: "string" }, time: { type: "string" }, command: { type: "string" },
}, ["pid", "user", "command"]));
putSchema("ProcessesListResponse", obj({
  status: { type: "string", enum: ["success", "error"] },
  total_processes: { type: "integer" }, returned_processes: { type: "integer" },
  sort_by: { type: "string", enum: ["cpu", "mem", "pid", "time"] },
  filters: { type: "object", additionalProperties: true },
  processes: { type: "array", items: ref("ProcessRow") },
  timestamp: { type: "string", format: "date-time" }, message: { type: "string" },
}, ["status"]));

putSchema("CronJobListResponse", obj({
  status: { type: "string", enum: ["success"] }, user: { type: "string" },
  jobs: { type: "array", items: { type: "object", additionalProperties: true } },
  total_count: { type: "integer" }, max_allowed: { type: "integer" },
}, ["status", "jobs"]));
putSchema("CronJobCreateRequest", {
  type: "object", additionalProperties: false,
  properties: {
    schedule: { type: "string", maxLength: 50, pattern: "^[\\\\d\\\\*\\\\/\\\\-\\\\,\\\\s]+$" },
    command: { type: "string", maxLength: 256, pattern: "^/[a-zA-Z0-9/_\\\\-.]+$" },
    arguments: { type: "string", maxLength: 512 }, comment: { type: "string", maxLength: 256 },
    reason: { type: "string", minLength: 10, maxLength: 500 },
  },
  required: ["schedule", "command", "reason"],
});
putSchema("CronJobToggleRequest", {
  type: "object", additionalProperties: false,
  properties: { enabled: { type: "boolean" }, reason: { type: "string", minLength: 10, maxLength: 500 } },
  required: ["enabled", "reason"],
});

putSchema("UserListResponse", obj({
  status: { type: "string", enum: ["success"] },
  users: { type: "array", items: { type: "object", additionalProperties: true } },
  total_count: { type: "integer" }, timestamp: { type: "string", format: "date-time" },
}, ["status"]));
putSchema("UserCreateRequest", {
  type: "object", additionalProperties: false,
  properties: {
    username: { type: "string", pattern: "^[a-z_][a-z0-9_-]{0,31}$", maxLength: 32 },
    password: { type: "string", minLength: 8, maxLength: 128, writeOnly: true },
    groups: { type: "array", maxItems: 10, items: { type: "string" } },
    home_dir: { type: "string" }, shell: { type: "string" },
    reason: { type: "string", minLength: 10, maxLength: 500 },
  },
  required: ["username", "password", "reason"],
});
putSchema("UserDeleteRequest", {
  type: "object", additionalProperties: false,
  properties: { reason: { type: "string", minLength: 10, maxLength: 500 }, remove_home: { type: "boolean" } },
  required: ["reason"],
});
putSchema("UserPasswordChangeRequest", {
  type: "object", additionalProperties: false,
  properties: { password: { type: "string", minLength: 8, maxLength: 128, writeOnly: true }, reason: { type: "string", minLength: 10, maxLength: 500 } },
  required: ["password", "reason"],
});
putSchema("GroupListResponse", obj({
  status: { type: "string", enum: ["success"] },
  groups: { type: "array", items: { type: "object", additionalProperties: true } },
  total_count: { type: "integer" }, timestamp: { type: "string", format: "date-time" },
}, ["status"]));
putSchema("GroupCreateRequest", { type: "object", additionalProperties: false, properties: { group_name: { type: "string" }, reason: { type: "string", minLength: 10, maxLength: 500 } }, required: ["group_name", "reason"] });
putSchema("GroupDeleteRequest", { type: "object", additionalProperties: false, properties: { reason: { type: "string", minLength: 10, maxLength: 500 } }, required: ["reason"] });
putSchema("GroupMembersUpdateRequest", { type: "object", additionalProperties: false, properties: { members: { type: "array", items: { type: "string" } }, reason: { type: "string", minLength: 10, maxLength: 500 } }, required: ["members", "reason"] });

putSchema("ApprovalListResponse", obj({ status: { type: "string", enum: ["success"] }, requests: { type: "array", items: { type: "object", additionalProperties: true } }, total: { type: "integer" }, page: { type: "integer" }, per_page: { type: "integer" } }, ["status"]));
putSchema("ApprovalDetailResponse", obj({ status: { type: "string", enum: ["success"] }, request: { type: "object", additionalProperties: true } }, ["status", "request"]));
putSchema("ApprovalActionRequest", { type: "object", additionalProperties: true, properties: { comment: { type: "string" }, reason: { type: "string" }, note: { type: "string" } } });
putSchema("ApprovalRejectRequest", { type: "object", additionalProperties: true, properties: { rejection_reason: { type: "string", minLength: 1 }, comment: { type: "string" } }, required: ["rejection_reason"] });
putSchema("ApprovalActionResponse", obj({ status: { type: "string", enum: ["success", "error"] }, message: { type: "string" }, request_id: { type: "string" }, status_value: ref("ApprovalStatus") }, ["status"]));
putSchema("ApprovalHistoryResponse", obj({ status: { type: "string", enum: ["success"] }, history: { type: "array", items: { type: "object", additionalProperties: true } }, total: { type: "integer" }, page: { type: "integer" }, per_page: { type: "integer" } }, ["status"]));
putSchema("ApprovalPoliciesResponse", obj({ status: { type: "string", enum: ["success"] }, policies: { type: "array", items: { type: "object", additionalProperties: true } } }, ["status"]));
putSchema("ApprovalStatsResponse", obj({ status: { type: "string", enum: ["success"] }, stats: { type: "object", additionalProperties: true } }, ["status"]));
putSchema("ApprovalRequestCreateRequest", { type: "object", additionalProperties: false, properties: { request_type: { type: "string" }, payload: { type: "object", additionalProperties: true }, reason: { type: "string", minLength: 1, maxLength: 500 } }, required: ["request_type", "payload", "reason"] });

addPath("/api/v1/processes", "get", {
  tags: ["processes"], summary: "List processes", description: "v0.3 process list",
  permissions: ["read:processes"],
  parameters: [
    q("sort_by", { type: "string", enum: ["cpu", "mem", "pid", "time"], default: "cpu" }, "推奨パラメータ"),
    q("sort", { type: "string", enum: ["cpu", "mem", "pid", "time"] }, "後方互換エイリアス"),
    q("filter_user", { type: "string", pattern: "^[a-z_][a-z0-9_-]{0,31}$" }),
    q("min_cpu", { type: "number", minimum: 0, maximum: 100, default: 0 }),
    q("min_mem", { type: "number", minimum: 0, maximum: 100, default: 0 }),
    q("limit", { type: "integer", minimum: 1, maximum: 1000, default: 100 }),
  ],
  responses: protectedResponses({ "200": resp(ref("ProcessesListResponse"), "Process list") }),
});

addPath("/api/cron", "get", {
  tags: ["cron"], summary: "List cron jobs", description: "Cronジョブ一覧取得",
  permissions: ["read:cron"], parameters: [q("user", { type: "string", pattern: "^[a-z_][a-z0-9_-]{0,31}$" }, "Adminのみ")],
  responses: protectedResponses({ "200": resp(ref("CronJobListResponse"), "Cron jobs") }),
});
addPath("/api/cron", "post", {
  tags: ["cron"], summary: "Create cron approval request", description: "Cron追加申請",
  permissions: ["write:cron"], requestBody: body(ref("CronJobCreateRequest")),
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});
addPath("/api/cron/{job_id}", "delete", {
  tags: ["cron"], summary: "Create cron delete approval request", description: "Cron削除申請",
  permissions: ["write:cron"],
  parameters: [p("job_id", { type: "string", pattern: "^cron_[0-9]{3,6}$" }), q("reason", { type: "string", minLength: 10, maxLength: 500 })],
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});
addPath("/api/cron/{job_id}", "patch", {
  tags: ["cron"], summary: "Create cron toggle approval request", description: "Cron有効/無効切替申請",
  permissions: ["write:cron"], parameters: [p("job_id", { type: "string", pattern: "^cron_[0-9]{3,6}$" })],
  requestBody: body(ref("CronJobToggleRequest")),
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});

addPath("/api/users", "get", {
  tags: ["users"], summary: "List users", description: "ユーザー一覧取得",
  permissions: ["read:users"], responses: protectedResponses({ "200": resp(ref("UserListResponse"), "User list") }),
});
addPath("/api/users", "post", {
  tags: ["users"], summary: "Create user approval request", description: "ユーザー追加申請",
  permissions: ["write:users"], requestBody: body(ref("UserCreateRequest")),
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});
addPath("/api/users/{uid}", "get", {
  tags: ["users"], summary: "Get user detail", description: "ユーザー詳細",
  permissions: ["read:users"], parameters: [p("uid", { oneOf: [{ type: "string" }, { type: "integer" }] })],
  responses: protectedResponses({ "200": resp({ type: "object", additionalProperties: true }, "User detail"), "404": resp(ref("ApiErrorResponse"), "Not found") }),
});
addPath("/api/users/{uid}", "delete", {
  tags: ["users"], summary: "Create user delete approval request", description: "ユーザー削除申請",
  permissions: ["write:users"], parameters: [p("uid", { oneOf: [{ type: "string" }, { type: "integer" }] })],
  requestBody: body(ref("UserDeleteRequest"), false),
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});
addPath("/api/users/{uid}/password", "put", {
  tags: ["users"], summary: "Create password change approval request", description: "パスワード変更申請",
  permissions: ["write:users"], parameters: [p("uid", { oneOf: [{ type: "string" }, { type: "integer" }] })], requestBody: body(ref("UserPasswordChangeRequest")),
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});
addPath("/api/groups", "get", {
  tags: ["users"], summary: "List groups", description: "グループ一覧取得",
  permissions: ["read:users"], responses: protectedResponses({ "200": resp(ref("GroupListResponse"), "Group list") }),
});
addPath("/api/groups", "post", {
  tags: ["users"], summary: "Create group approval request", description: "グループ追加申請",
  permissions: ["write:users"], requestBody: body(ref("GroupCreateRequest")),
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});
addPath("/api/groups/{gid}", "delete", {
  tags: ["users"], summary: "Create group delete approval request", description: "グループ削除申請",
  permissions: ["write:users"], parameters: [p("gid", { oneOf: [{ type: "string" }, { type: "integer" }] })], requestBody: body(ref("GroupDeleteRequest"), false),
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});
addPath("/api/groups/{gid}/members", "put", {
  tags: ["users"], summary: "Create group membership update approval request", description: "メンバー変更申請",
  permissions: ["write:users"], parameters: [p("gid", { oneOf: [{ type: "string" }, { type: "integer" }] })], requestBody: body(ref("GroupMembersUpdateRequest")),
  responses: protectedResponses({ "202": resp(ref("ApprovalPendingResponse"), "Approval pending"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});

const apId = p("request_id", { type: "string" });
const apListQ = [
  q("page", { type: "integer", minimum: 1, default: 1 }),
  q("per_page", { type: "integer", minimum: 1, maximum: 100, default: 20 }),
  q("status", { type: "string", enum: ["pending", "approved", "rejected", "expired", "executed", "execution_failed", "cancelled"] }),
  q("request_type", { type: "string" }),
  q("q", { type: "string" }),
];

addPath("/api/approval/request", "post", {
  tags: ["approval"], summary: "Create approval request", description: "危険操作の承認申請を作成",
  permissions: ["request:approval"], requestBody: body(ref("ApprovalRequestCreateRequest")),
  responses: protectedResponses({ "201": resp(ref("ApprovalActionResponse"), "Created"), "202": resp(ref("ApprovalActionResponse"), "Accepted"), "409": resp(ref("ApiErrorResponse"), "Conflict") }),
});
addPath("/api/approval/pending", "get", {
  tags: ["approval"], summary: "List pending approvals", description: "承認待ち一覧",
  permissions: ["view:approval_pending"], parameters: apListQ,
  responses: protectedResponses({ "200": resp(ref("ApprovalListResponse"), "Pending approvals") }),
});
addPath("/api/approval/my-requests", "get", {
  tags: ["approval"], summary: "List my requests", description: "自分の申請一覧",
  permissions: ["request:approval"], parameters: apListQ,
  responses: protectedResponses({ "200": resp(ref("ApprovalListResponse"), "My requests") }),
});
addPath("/api/approval/{request_id}", "get", {
  tags: ["approval"], summary: "Get approval detail", description: "申請者本人または承認権限保持者が閲覧",
  permissionsAnyOf: ["request:approval", "view:approval_pending"], parameters: [apId],
  responses: protectedResponses({ "200": resp(ref("ApprovalDetailResponse"), "Approval detail"), "404": resp(ref("ApiErrorResponse"), "Not found") }),
});
addPath("/api/approval/{request_id}/approve", "post", {
  tags: ["approval"], summary: "Approve request", description: "自己承認禁止。pendingのみ",
  permissions: ["execute:approval"], parameters: [apId], requestBody: body(ref("ApprovalActionRequest"), false),
  responses: protectedResponses({ "200": resp(ref("ApprovalActionResponse"), "Approved"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Invalid state / self approval") }),
});
addPath("/api/approval/{request_id}/reject", "post", {
  tags: ["approval"], summary: "Reject request", description: "pendingのみ",
  permissions: ["execute:approval"], parameters: [apId], requestBody: body(ref("ApprovalRejectRequest")),
  responses: protectedResponses({ "200": resp(ref("ApprovalActionResponse"), "Rejected"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Invalid state") }),
});
addPath("/api/approval/{request_id}/cancel", "post", {
  tags: ["approval"], summary: "Cancel request", description: "申請者本人のみ。pendingのみ",
  permissions: ["request:approval"], parameters: [apId], requestBody: body(ref("ApprovalActionRequest"), false),
  responses: protectedResponses({ "200": resp(ref("ApprovalActionResponse"), "Cancelled"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Invalid state") }),
});
addPath("/api/approval/{request_id}/execute", "post", {
  tags: ["approval"], summary: "Execute approved action", description: "approvedのみ手動実行",
  permissions: ["execute:approved_action"], parameters: [apId], requestBody: body(ref("ApprovalActionRequest"), false),
  responses: protectedResponses({ "200": resp(ref("ApprovalActionResponse"), "Executed"), "404": resp(ref("ApiErrorResponse"), "Not found"), "409": resp(ref("ApiErrorResponse"), "Invalid state") }),
});
addPath("/api/approval/history", "get", {
  tags: ["approval"], summary: "Approval history", description: "承認監査履歴",
  permissions: ["view:approval_history"], parameters: [...apListQ, q("date_from", { type: "string", format: "date" }), q("date_to", { type: "string", format: "date" })],
  responses: protectedResponses({ "200": resp(ref("ApprovalHistoryResponse"), "History") }),
});
addPath("/api/approval/history/export", "get", {
  tags: ["approval"], summary: "Export approval history CSV", description: "CSVエクスポート",
  permissions: ["export:approval_history"], parameters: [q("date_from", { type: "string", format: "date" }), q("date_to", { type: "string", format: "date" }), q("request_type", { type: "string" }), q("action", { type: "string" })],
  responses: { "200": resp({ type: "string" }, "CSV export", "text/csv"), "401": resp(ref("ApiErrorResponse"), "Unauthorized"), "403": resp(ref("ApiErrorResponse"), "Forbidden"), "422": resp(ref("HTTPValidationError"), "Validation Error") },
});
addPath("/api/approval/policies", "get", {
  tags: ["approval"], summary: "Approval policies", description: "承認ポリシー一覧",
  permissions: ["view:approval_policies"], responses: protectedResponses({ "200": resp(ref("ApprovalPoliciesResponse"), "Policies") }),
});
addPath("/api/approval/stats", "get", {
  tags: ["approval"], summary: "Approval stats", description: "承認統計",
  permissions: ["view:approval_stats"], parameters: [q("date_from", { type: "string", format: "date" }), q("date_to", { type: "string", format: "date" })],
  responses: protectedResponses({ "200": resp(ref("ApprovalStatsResponse"), "Stats") }),
});

fs.writeFileSync(FILE, `${JSON.stringify(doc, null, 2)}\n`, "utf8");
console.log(`Updated docs/openapi.json (paths=${Object.keys(doc.paths || {}).length}, schemas=${Object.keys(doc.components?.schemas || {}).length})`);
