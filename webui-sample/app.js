import { APP_KEYS } from "./js/config.js";
import { createUiStore } from "./js/store.js";
import { createApiFacade } from "./js/api/index.js";
import { explainApiError, validateUsername, validateCronSchedule, validateCronArguments, validateStrongPassword } from "./js/modules/validation.js";
import { buildProcessesQuery, normalizeProcessesResponse } from "./js/modules/processes.js";
import { normalizeApprovalActionResponse, normalizeApprovalDetailPayload, normalizeApprovalListPayload, normalizeApprovalStatus } from "./js/modules/approvals.js";
import { normalizeCronListPayload, normalizeApprovalPendingResponse as normalizeCronApprovalPending } from "./js/modules/cron.js";
import { normalizeUsersListPayload, normalizeGroupsListPayload } from "./js/modules/users.js";
import { normalizeLogsPayload, normalizeServiceRestartPayload } from "./js/modules/services.js";

(() => {
  "use strict";

  const SESSION_KEY = APP_KEYS.session;
  const SESSION_TTL = 30 * 60 * 1000;
  const PROC_AUTO_MS = 5000;
  const RESTART_ALLOW = new Set(["nginx", "postgresql", "redis"]);
  const CRON_ALLOW = new Set([
    "/usr/bin/rsync", "/usr/local/bin/healthcheck.sh", "/usr/bin/find",
    "/usr/bin/tar", "/usr/bin/gzip", "/usr/bin/curl", "/usr/bin/wget",
    "/usr/bin/python3", "/usr/bin/node",
  ]);
  const FORBIDDEN_GROUPS = new Set(["root", "sudo", "wheel", "docker", "lxd", "shadow"]);
  const ALLOWED_SHELLS = new Set(["/bin/bash", "/bin/sh", "/usr/bin/zsh", "/usr/sbin/nologin", "/bin/false"]);
  const APPROVAL_META = {
    user_add: { label: "ユーザーアカウント追加", risk: "HIGH", roles: "Approver, Admin", timeout: "24h" },
    user_delete: { label: "ユーザーアカウント削除", risk: "CRITICAL", roles: "Admin", timeout: "12h" },
    user_passwd: { label: "ユーザーパスワード変更", risk: "HIGH", roles: "Approver, Admin", timeout: "24h" },
    group_modify: { label: "グループメンバー変更", risk: "MEDIUM", roles: "Approver, Admin", timeout: "24h" },
    group_delete: { label: "グループ削除", risk: "HIGH", roles: "Admin", timeout: "12h" },
    cron_add: { label: "Cronジョブ追加", risk: "HIGH", roles: "Approver, Admin", timeout: "24h" },
    cron_modify: { label: "Cronジョブ変更", risk: "HIGH", roles: "Approver, Admin", timeout: "24h" },
    service_stop: { label: "サービス停止", risk: "CRITICAL", roles: "Admin", timeout: "12h" },
    firewall_modify: { label: "ファイアウォール変更", risk: "CRITICAL", roles: "Admin", timeout: "12h" },
  };

  const dom = {};
  const state = {
    session: null,
    activeSection: "sec-dashboard",
    procAuto: null,
    clock: null,
    sessionWatch: null,
    scrollTicking: false,
    selectedPid: null,
    selectedService: "nginx",
    services: {},
    approvals: {},
    nextApprovalId: 1007,
    confirmFn: null,
    apiNoticeShown: false,
    api: null,
    store: createUiStore(),
  };

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    window.__LMS_WEBUI_BOOTED__ = true;
    cacheDom();
    seedState();
    initApi();
    bindBaseEvents();
    initAccordions();
    initTabs();
    initClock();
    restoreSession();
    refreshAll(false);
    activateSection(state.activeSection, false);
  }

  function initApi() {
    state.api = createApiFacade({
      getToken: () => state.session?.token || state.session?.access_token || state.session?.accessToken || null,
      onNetworkState: ({ ok, op, error }) => {
        if (ok) return;
        if (state.apiNoticeShown) return;
        state.apiNoticeShown = true;
        toast(`API接続失敗 (${op})。モック表示を継続します。`, "warning", 3600);
        if (error) console.warn("[webui-sample]", op, error);
      },
    });
  }

  function cacheDom() {
    [
      "loginScreen", "shell", "loginForm", "loginEmail", "loginPassword", "loginRole", "loginMessage",
      "logoutBtn", "sidebar", "sidebarBackdrop", "sidebarOpenBtn", "sidebarCloseBtn", "sidebarNav",
      "sidebarUsername", "sidebarEmail", "sidebarRoleBadge", "breadcrumb", "pageTitle", "liveClock",
      "refreshPageBtn", "pageContent", "systemTimeLabel", "modalLayer", "toastStack",
      "cpuUsageValue", "cpuUsageBar", "memUsageValue", "memUsageBar", "pendingCountValue", "procTotalValue",
      "topCpuValue", "procRefreshBtn", "procAutoBtn", "procSort", "procUser", "procMinCpu", "procMinMem",
      "procLimit", "procTable", "procRowsMeta", "procKpiTotal", "procKpiCpu", "procKpiMem", "procKpiStates",
      "procCpuBar", "procMemBar", "procDetailName", "procDetailId", "procDetailStat", "procDetailCpu",
      "procDetailMem", "procDetailStateText", "procDetailCwd", "procDetailCmd",
      "servicePreviewTitle", "servicePreviewName", "serviceLogPreview",
      "logsService", "logsLines", "logsQ", "logsTerminal",
      "usersSearch", "usersStatus", "groupsSearch", "usersTable", "groupsTable",
      "approvalPendingType", "approvalPendingRequester", "approvalPendingTable",
      "approvalMyStatus", "approvalMyTable", "approvalDraftForm", "approvalDraftType", "approvalDraftReason",
      "approvalDraftFields", "approvalPreviewType", "approvalPreviewRisk", "approvalPreviewRoles",
      "approvalPreviewTimeout", "approvalPreviewPayload", "approvalPeriod", "approvalHistoryStatus",
      "approvalHistoryTable", "approvalDetailTitle", "approvalDetailId", "approvalDetailStatus",
      "approvalDetailRisk", "approvalDetailRequesterRole", "approvalDetailRequester", "approvalDetailReason",
      "approvalDetailPayload", "approvalDetailTimeline", "auditOp", "auditStatus", "auditQ", "auditTable", "cronTable"
    ].forEach((id) => { dom[id] = byId(id); });
  }

  function seedState() {
    state.services = {
      nginx: { title: "Nginx Web Server", logs: [
        "Feb 24 09:12:20 nginx: Reloading configuration...",
        "Feb 24 09:12:21 nginx: Configuration reloaded",
        "Feb 24 10:15:13 nginx: GET /api/system/status 200",
        "Feb 24 10:22:33 nginx: GET /api/v1/processes 200",
      ]},
      postgresql: { title: "PostgreSQL", logs: [
        "Feb 24 09:00:01 postgresql: checkpoint complete",
        "Feb 24 09:10:11 postgresql: connection authorized user=adminui",
        "Feb 24 10:14:50 postgresql: autovacuum launcher started",
      ]},
      redis: { title: "Redis", logs: [
        "Feb 24 08:55:20 redis: Background saving started",
        "Feb 24 08:55:21 redis: DB saved on disk",
        "Feb 24 10:04:51 redis: Expired 42 keys",
      ]},
      "linux-management-prod": { title: "Linux Management API", logs: [
        "Feb 24 09:01:00 api: startup complete on :5012",
        "Feb 24 09:28:02 api: processes.list returned=7",
        "Feb 24 09:40:33 api: approval.request created id=apr-1002",
      ]},
      sshd: { title: "SSH Server", logs: [
        "Feb 24 08:32:22 sshd: Accepted publickey for kensan",
        "Feb 24 08:58:45 sshd: Failed password for invalid user test",
      ]},
    };

    state.approvals = {
      "apr-1001": mkApproval("apr-1001", "user_add", "operator", "Operator", "pending", "新規プロジェクトメンバーのアカウント作成",
        { username: "newuser", group: "developers", home: "/home/newuser", shell: "/bin/bash" }, "02/24 17:00:00"),
      "apr-1002": mkApproval("apr-1002", "cron_add", "operator", "Operator", "pending", "夜間バックアップジョブの追加",
        { schedule: "0 2 * * *", command: "/usr/bin/rsync", arguments: "-avz /data /backup/data" }, "02/24 15:00:00"),
      "apr-1003": mkApproval("apr-1003", "service_stop", "approver1", "Approver", "approved", "メンテナンスのため nginx 停止",
        { service: "nginx" }, "02/24 09:30:00", [{ tone: "success", title: "approved / admin (Admin)", time: "02/24 10:00:00" }]),
      "apr-1004": mkApproval("apr-1004", "group_delete", "operator", "Operator", "rejected", "legacyops を削除",
        { group: "legacyops" }, "02/23 10:15:00", [{ tone: "warning", title: "rejected / admin (Admin)", time: "02/23 12:00:00" }]),
      "apr-1005": mkApproval("apr-1005", "cron_modify", "operator2", "Operator", "executed", "ヘルスチェック間隔の調整",
        { cron_id: "cron_002", schedule: "*/10 * * * *" }, "02/22 19:20:00", [
          { tone: "success", title: "approved / approver1 (Approver)", time: "02/22 19:45:00" },
          { tone: "success", title: "executed / system", time: "02/22 20:00:00" },
        ]),
      "apr-1006": mkApproval("apr-1006", "firewall_modify", "operator", "Operator", "expired", "一時的なFWルール変更",
        { rule: "allow tcp/8443 from 10.0.10.0/24" }, "02/20 20:00:00", [{ tone: "warning", title: "expired / system", time: "02/21 08:00:00" }]),
    };
  }

  function mkApproval(id, type, requester, role, status, reason, payload, createdAt, extraTimeline) {
    return {
      id, type, requester, requesterRole: role, status,
      risk: (APPROVAL_META[type] || APPROVAL_META.user_add).risk,
      reason, payload,
      timeline: [{ tone: "info", title: `created / ${requester} (${role})`, time: createdAt }].concat(extraTimeline || []),
    };
  }

  function bindBaseEvents() {
    dom.loginForm?.addEventListener("submit", loginSubmit);
    dom.logoutBtn?.addEventListener("click", () => logout("ログアウトしました。"));
    dom.sidebarOpenBtn?.addEventListener("click", () => setSidebar(true));
    dom.sidebarCloseBtn?.addEventListener("click", () => setSidebar(false));
    dom.sidebarBackdrop?.addEventListener("click", () => setSidebar(false));
    dom.refreshPageBtn?.addEventListener("click", () => refreshAll(true));
    document.addEventListener("click", onClick);
    document.addEventListener("input", onInput);
    document.addEventListener("change", onChange);
    document.addEventListener("submit", onSubmit);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && dom.modalLayer?.classList.contains("active")) closeModal();
    });
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  function restoreSession() {
    try {
      const s = state.store.getSession();
      if (!s) return loggedOut();
      if (!s || !s.expiresAt || Date.now() >= s.expiresAt) return loggedOut("セッションの有効期限が切れました。");
      state.session = s;
      loggedIn();
    } catch {
      loggedOut("保存セッションの読み込みに失敗しました。");
    }
  }

  async function loginSubmit(e) {
    e.preventDefault();
    const email = (dom.loginEmail?.value || "").trim();
    const pw = dom.loginPassword?.value || "";
    const role = dom.loginRole?.value || "Admin";
    if (!email.includes("@")) return setMsg(dom.loginMessage, "メールアドレスを確認してください。", "error");
    if (pw.length < 8) return setMsg(dom.loginMessage, "パスワードは8文字以上で入力してください。", "error");
    setMsg(dom.loginMessage, "ログイン中...", "info");

    let sessionFromApi = null;
    try {
      const live = await state.api.tryLive(
        () => state.api.api.auth.login({ email, password: pw }),
        { op: "auth.login" }
      );
      if (live.live && live.data) {
        const token = live.data.access_token || live.data.token || live.data.jwt;
        sessionFromApi = {
          email: live.data.email || email,
          username: live.data.username || email.split("@")[0],
          role: roleLabel(live.data.role || role),
          token,
          access_token: token,
          user_id: live.data.user_id || live.data.id || null,
          expiresAt: Date.now() + SESSION_TTL,
        };
        // Best effort refresh from /auth/me for permissions/profile
        if (token) {
          state.session = sessionFromApi;
          const me = await state.api.tryLive(() => state.api.api.auth.me(), { op: "auth.me" });
          if (me.live && me.data) {
            sessionFromApi = {
              ...sessionFromApi,
              email: me.data.email || sessionFromApi.email,
              username: me.data.username || sessionFromApi.username,
              role: roleLabel(me.data.role || sessionFromApi.role),
              permissions: me.data.permissions || sessionFromApi.permissions,
              user_id: me.data.user_id || sessionFromApi.user_id,
            };
          }
        }
      }
    } catch (err) {
      const info = explainApiError(err);
      setMsg(dom.loginMessage, info.message, "error");
      if (state.api.settings.mode === "live") return;
    }

    state.session = sessionFromApi || {
      email,
      username: email.split("@")[0],
      role,
      token: `mock.${Date.now()}.${Math.random().toString(36).slice(2, 8)}`,
      expiresAt: Date.now() + SESSION_TTL,
      mock: true,
    };
    state.store.setSession(state.session);
    loggedIn();
    setMsg(dom.loginMessage, "", "");
    toast(`ログイン: ${state.session.username} (${state.session.role})${sessionFromApi ? "" : " (mock)"}`, "success");
  }

  function loggedIn() {
    dom.loginScreen?.classList.add("hidden");
    dom.shell?.classList.remove("hidden");
    if (dom.sidebarUsername) dom.sidebarUsername.textContent = state.session?.username || "-";
    if (dom.sidebarEmail) dom.sidebarEmail.textContent = state.session?.email || "-";
    if (dom.sidebarRoleBadge) dom.sidebarRoleBadge.textContent = state.session?.role || "-";
    setMsg(dom.loginMessage, "", "");
    updateClocks();
    void hydrateLiveData();
  }

  function loggedOut(msg) {
    state.store.clearSession();
    state.session = null;
    dom.shell?.classList.add("hidden");
    dom.loginScreen?.classList.remove("hidden");
    setSidebar(false);
    if (state.procAuto) { clearInterval(state.procAuto); state.procAuto = null; }
    if (dom.procAutoBtn) { dom.procAutoBtn.dataset.procAuto = "off"; dom.procAutoBtn.textContent = "▶ Auto-refresh (5s)"; }
    if (msg) setMsg(dom.loginMessage, msg, "warning");
  }

  function logout(msg) {
    if (state.session && state.api) {
      void state.api.tryLive(() => state.api.api.auth.logout(), { op: "auth.logout" }).catch(() => {});
    }
    loggedOut();
    if (msg) toast(msg, "info");
  }

  async function hydrateLiveData() {
    await Promise.allSettled([
      refreshProcesses(false),
      renderLogs(),
      loadCronFromApi(),
      loadUsersFromApi(),
      refreshApprovalsFromApi(),
    ]);
  }

  function initClock() {
    updateClocks();
    state.clock = setInterval(updateClocks, 1000);
    state.sessionWatch = setInterval(() => {
      if (state.session && Date.now() >= state.session.expiresAt) logout("セッションの有効期限（30分）が切れました。");
    }, 15000);
  }

  function updateClocks() {
    const d = new Date();
    if (dom.liveClock) dom.liveClock.textContent = d.toLocaleTimeString("ja-JP", { hour12: false });
    if (dom.systemTimeLabel) dom.systemTimeLabel.textContent = d.toLocaleString("ja-JP", {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
    });
  }

  function initAccordions() {
    qsa("[data-accordion-toggle]").forEach((btn) => syncAccordion(btn.closest(".accordion"), btn));
  }

  function syncAccordion(acc, btn) {
    const ex = !!acc?.classList.contains("expanded");
    btn?.setAttribute("aria-expanded", String(ex));
    const chev = btn?.querySelector(".accordion-chevron");
    if (chev) chev.textContent = ex ? "▾" : "▸";
  }

  function initTabs() {
    qsa(".tab.active[data-tab-group]").forEach((b) => activateTab(b.dataset.tabGroup, b.dataset.tabId, false));
  }

  function activateTab(group, id, focus = true) {
    const tabs = qsa(`.tab[data-tab-group="${escSel(group)}"]`);
    const ids = tabs.map((t) => t.dataset.tabId);
    tabs.forEach((t) => {
      const on = t.dataset.tabId === id;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", String(on));
      if (on && focus) t.focus({ preventScroll: true });
    });
    qsa("[data-tab-panel]").forEach((p) => {
      if (ids.includes(p.dataset.tabPanel)) p.classList.toggle("active", p.dataset.tabPanel === id);
    });
  }

  function activateSection(id, doScroll) {
    const sec = byId(id);
    if (!sec) return;
    state.activeSection = id;
    if (dom.pageTitle) dom.pageTitle.textContent = sec.dataset.pageLabel || "ページ";
    if (dom.breadcrumb) dom.breadcrumb.textContent = sec.dataset.breadcrumb || "Home";
    qsa(".menu-item, .submenu-item").forEach((b) => b.classList.toggle("active", b.dataset.scrollTarget === id));
    if (doScroll) sec.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function setSidebar(open) {
    dom.sidebar?.classList.toggle("open", !!open);
    dom.sidebarBackdrop?.classList.toggle("hidden", !open);
  }

  function onScroll() {
    if (state.scrollTicking) return;
    state.scrollTicking = true;
    requestAnimationFrame(() => {
      state.scrollTicking = false;
      let best = null, score = Infinity;
      qsa(".module-section[id]").forEach((sec) => {
        const s = Math.abs(sec.getBoundingClientRect().top - 140);
        if (s < score) { score = s; best = sec; }
      });
      if (best && best.id !== state.activeSection) activateSection(best.id, false);
    });
  }

  function refreshAll(withToast) {
    updateClocks();
    if (typeof refreshProcesses === "function") void refreshProcesses(false);
    if (typeof renderServicePreview === "function") renderServicePreview(state.selectedService);
    if (typeof renderLogs === "function") void renderLogs();
    if (typeof loadCronFromApi === "function") void loadCronFromApi();
    if (typeof loadUsersFromApi === "function") void loadUsersFromApi();
    if (typeof filterAudit === "function") filterAudit();
    if (typeof filterUsersGroups === "function") filterUsersGroups();
    if (typeof syncApprovalUI === "function") syncApprovalUI();
    if (typeof refreshApprovalsFromApi === "function") void refreshApprovalsFromApi();
    if (withToast) toast(`画面を再描画しました（${state.api?.settings?.mode || "mock"}）`, "info");
  }

  function onClick(e) {}
  function onInput(e) {}
  function onChange(e) {}
  function onSubmit(e) {}

  function byId(id) { return document.getElementById(id); }
  function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }
  function txt(el, v) { if (el) el.textContent = v; }
  function fmtInt(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toLocaleString("en-US") : "0";
  }
  function setMsg(el, msg, tone) {
    if (!el) return;
    el.textContent = msg || "";
    el.classList.remove("msg-success", "msg-error", "msg-warning", "msg-info");
    if (tone) el.classList.add(`msg-${tone}`);
  }
  function clamp(n, min, max) { return Math.min(max, Math.max(min, n)); }
  function rand(min, max) { return Math.random() * (max - min) + min; }
  function parseHms(s) {
    const p = String(s || "").split(":").map(Number);
    if (p.some(Number.isNaN)) return 0;
    return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p.length === 2 ? p[0] * 60 + p[1] : (p[0] || 0);
  }
  function nowShort() {
    return new Date().toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  }
  function nowLong() {
    return new Date().toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  }
  function isoToUi(v) {
    if (!v) return "-";
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  }
  function escSel(v) { return window.CSS?.escape ? CSS.escape(v || "") : String(v || "").replace(/["\\]/g, "\\$&"); }
  function escHtml(v) {
    return String(v).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  }
  function roleLabel(v) {
    const m = { admin: "Admin", approver: "Approver", operator: "Operator", viewer: "Viewer" };
    return m[String(v || "").toLowerCase()] || (v || "Operator");
  }
  function getProcRows() { return qsa("tr[data-proc-row]", dom.procTable); }

  async function refreshProcesses(jitter = true) {
    if (!dom.procTable) return;
    if (state.session && state.api) {
      const query = buildProcessesQuery({
        sort_by: dom.procSort?.value || "cpu",
        filter_user: dom.procUser?.value || "",
        min_cpu: +dom.procMinCpu?.value || 0,
        min_mem: +dom.procMinMem?.value || 0,
        limit: clamp(parseInt(dom.procLimit?.value || "100", 10), 1, 1000),
      });
      try {
        const live = await state.api.tryLive(
          () => state.api.api.processes.list(query),
          { op: "processes.list" }
        );
        if (live.live && live.data) {
          try {
            const normalized = normalizeProcessesResponse(live.data);
            renderProcessesTableFromApi(normalized);
            return;
          } catch (err) {
            console.warn("[webui-sample] processes adapter fallback", err);
          }
        }
      } catch (err) {
        if (state.api.settings.mode === "live") toast(explainApiError(err).message, "error");
      }
    }

    const rows = getProcRows();
    if (jitter) {
      rows.forEach((r) => {
        const c = clamp((+r.dataset.cpu || 0) + rand(-1.2, 1.5), 0, 95);
        const m = clamp((+r.dataset.mem || 0) + rand(-0.6, 0.8), 0, 95);
        r.dataset.cpu = c.toFixed(1);
        r.dataset.mem = m.toFixed(1);
        const cCell = r.querySelector("[data-proc-cpu]");
        const mCell = r.querySelector("[data-proc-mem]");
        if (cCell) cCell.textContent = c.toFixed(1);
        if (mCell) mCell.textContent = m.toFixed(1);
      });
    }

    const sort = dom.procSort?.value || "cpu";
    const user = dom.procUser?.value || "";
    const minCpu = +dom.procMinCpu?.value || 0;
    const minMem = +dom.procMinMem?.value || 0;
    const limit = clamp(parseInt(dom.procLimit?.value || "100", 10), 1, 1000);
    if (dom.procLimit) dom.procLimit.value = String(limit);

    const body = dom.procTable.tBodies[0];
    const list = rows.filter((r) => {
      if (user && r.dataset.user !== user) return false;
      if ((+r.dataset.cpu || 0) < minCpu) return false;
      if ((+r.dataset.mem || 0) < minMem) return false;
      return true;
    });

    list.sort((a, b) => {
      if (sort === "mem") return (+b.dataset.mem || 0) - (+a.dataset.mem || 0);
      if (sort === "pid") return (+a.dataset.pid || 0) - (+b.dataset.pid || 0);
      if (sort === "time") return parseHms(b.cells[8]?.textContent) - parseHms(a.cells[8]?.textContent);
      return (+b.dataset.cpu || 0) - (+a.dataset.cpu || 0);
    });

    const shown = list.slice(0, limit);
    shown.forEach((r) => body.appendChild(r));
    rows.forEach((r) => r.classList.add("hidden"));
    shown.forEach((r) => r.classList.remove("hidden"));

    let cpu = 0, mem = 0;
    const st = { R: 0, S: 0, Z: 0, T: 0 };
    shown.forEach((r) => {
      cpu += +r.dataset.cpu || 0;
      mem += +r.dataset.mem || 0;
      const s = (r.cells[6]?.textContent || "").trim();
      const k = s.startsWith("R") ? "R" : s.startsWith("Z") ? "Z" : s.startsWith("T") ? "T" : "S";
      st[k] += 1;
    });
    const top = shown[0];
    txt(dom.procRowsMeta, `${shown.length} 件表示`);
    txt(dom.procKpiTotal, String(shown.length));
    txt(dom.procKpiCpu, `${cpu.toFixed(1)}%`);
    txt(dom.procKpiMem, `${mem.toFixed(1)}%`);
    txt(dom.procKpiStates, `R:${st.R} / S:${st.S}`);
    if (dom.procCpuBar) dom.procCpuBar.style.width = `${clamp(cpu, 0, 100).toFixed(1)}%`;
    if (dom.procMemBar) dom.procMemBar.style.width = `${clamp(mem, 0, 100).toFixed(1)}%`;
    txt(dom.procTotalValue, String(shown.length));
    txt(dom.topCpuValue, `${(+top?.dataset.cpu || 0).toFixed(1)}%`);

    const selected = shown.find((r) => r.dataset.pid === state.selectedPid) || shown[0];
    if (selected) selectProcess(selected);

    const dashCpu = clamp(cpu + rand(-2, 2), 1, 98);
    const dashMem = clamp(mem + rand(-3, 3) + 18, 10, 98);
    txt(dom.cpuUsageValue, `${dashCpu.toFixed(1)}%`);
    txt(dom.memUsageValue, `${dashMem.toFixed(1)}%`);
    if (dom.cpuUsageBar) dom.cpuUsageBar.style.width = `${dashCpu.toFixed(1)}%`;
    if (dom.memUsageBar) dom.memUsageBar.style.width = `${dashMem.toFixed(1)}%`;
  }

  function renderProcessesTableFromApi(data) {
    const body = dom.procTable?.tBodies?.[0];
    if (!body) return;
    const rows = Array.isArray(data?.processes) ? data.processes : [];
    body.innerHTML = "";
    const frag = document.createDocumentFragment();
    rows.forEach((p) => {
      const tr = document.createElement("tr");
      tr.dataset.procRow = "";
      tr.dataset.user = p.user;
      tr.dataset.cpu = Number(p.cpu_percent || 0).toFixed(1);
      tr.dataset.mem = Number(p.mem_percent || 0).toFixed(1);
      tr.dataset.pid = String(p.pid);
      tr.innerHTML =
        `<td class="mono">${escHtml(p.pid)}</td>` +
        `<td>${escHtml(p.user)}</td>` +
        `<td data-proc-cpu>${Number(p.cpu_percent || 0).toFixed(1)}</td>` +
        `<td data-proc-mem>${Number(p.mem_percent || 0).toFixed(1)}</td>` +
        `<td>${fmtInt(p.vsz)}</td>` +
        `<td>${fmtInt(p.rss)}</td>` +
        `<td><span class="chip chip-outline mono">${escHtml(p.stat || "S")}</span></td>` +
        `<td class="mono">${escHtml(p.start || "")}</td>` +
        `<td class="mono">${escHtml(p.time || "00:00:00")}</td>` +
        `<td class="mono truncate-cell">${escHtml(p.command || "")}</td>`;
      frag.appendChild(tr);
    });
    body.appendChild(frag);

    const cpu = rows.reduce((s, p) => s + Number(p.cpu_percent || 0), 0);
    const mem = rows.reduce((s, p) => s + Number(p.mem_percent || 0), 0);
    const states = { R: 0, S: 0, Z: 0, T: 0 };
    rows.forEach((p) => {
      const st = String(p.stat || "");
      const k = st.startsWith("R") ? "R" : st.startsWith("Z") ? "Z" : st.startsWith("T") ? "T" : "S";
      states[k] += 1;
    });
    txt(dom.procRowsMeta, `${rows.length} 件表示`);
    txt(dom.procKpiTotal, String(rows.length));
    txt(dom.procKpiCpu, `${cpu.toFixed(1)}%`);
    txt(dom.procKpiMem, `${mem.toFixed(1)}%`);
    txt(dom.procKpiStates, `R:${states.R} / S:${states.S}`);
    if (dom.procCpuBar) dom.procCpuBar.style.width = `${clamp(cpu, 0, 100).toFixed(1)}%`;
    if (dom.procMemBar) dom.procMemBar.style.width = `${clamp(mem, 0, 100).toFixed(1)}%`;
    txt(dom.procTotalValue, String(rows.length));
    txt(dom.topCpuValue, `${Number(rows[0]?.cpu_percent || 0).toFixed(1)}%`);
    const rowEls = getProcRows();
    if (rowEls[0]) selectProcess(rowEls.find((r) => r.dataset.pid === state.selectedPid) || rowEls[0]);
    const dashCpu = clamp(cpu + rand(-1.5, 1.5), 1, 98);
    const dashMem = clamp(mem + rand(-2.0, 2.0) + 18, 10, 98);
    txt(dom.cpuUsageValue, `${dashCpu.toFixed(1)}%`);
    txt(dom.memUsageValue, `${dashMem.toFixed(1)}%`);
    if (dom.cpuUsageBar) dom.cpuUsageBar.style.width = `${dashCpu.toFixed(1)}%`;
    if (dom.memUsageBar) dom.memUsageBar.style.width = `${dashMem.toFixed(1)}%`;
  }

  function selectProcess(row) {
    state.selectedPid = row.dataset.pid || null;
    getProcRows().forEach((r) => {
      r.style.outline = "";
      r.removeAttribute("aria-selected");
    });
    row.style.outline = "2px solid #b7d7f7";
    row.style.outlineOffset = "-2px";
    row.setAttribute("aria-selected", "true");
    const cmd = (row.cells[9]?.textContent || "").trim();
    const user = row.dataset.user || "";
    const stat = (row.cells[6]?.textContent || "").trim();
    txt(dom.procDetailName, procName(cmd, user));
    txt(dom.procDetailId, `${row.dataset.pid || "-"} / ${user}`);
    txt(dom.procDetailStat, stat);
    txt(dom.procDetailCpu, (+row.dataset.cpu || 0).toFixed(1));
    txt(dom.procDetailMem, (+row.dataset.mem || 0).toFixed(1));
    txt(dom.procDetailStateText, stat.startsWith("R") ? "Running" : stat.startsWith("Z") ? "Zombie" : stat.startsWith("T") ? "Stopped/Traced" : "Sleeping");
    txt(dom.procDetailCwd, procCwd(cmd, user));
    txt(dom.procDetailCmd, cmd);
  }

  function procName(cmd, user) {
    if (cmd.includes("postgres")) return "postgres";
    if (cmd.includes("redis")) return "redis";
    if (cmd.includes("nginx")) return "nginx";
    return (cmd.split(" ")[0].split("/").pop() || user || "-");
  }

  function procCwd(cmd, user) {
    if (cmd.includes("postgres")) return "/var/lib/postgresql";
    if (cmd.includes("uvicorn")) return "/opt/linux-management";
    if (cmd.includes("scheduler.py")) return "/opt/linux-management/jobs";
    if (cmd.includes("nginx")) return "/var/www";
    if (user === "root") return "/root";
    return `/home/${user || "user"}`;
  }

  function renderServicePreview(name = state.selectedService) {
    if (!state.services[name]) name = "nginx";
    state.selectedService = name;
    const svc = state.services[name];
    txt(dom.servicePreviewTitle, svc.title);
    txt(dom.servicePreviewName, name);
    renderTerminal(dom.serviceLogPreview, svc.logs.slice(-6));
    qsa("[data-service-select]").forEach((b) => {
      const on = b.dataset.serviceSelect === name;
      b.style.outline = on ? "2px solid #d8e8fb" : "";
      b.style.outlineOffset = on ? "2px" : "";
    });
  }

  async function restartService(name) {
    const chip = document.querySelector(`[data-service-status="${escSel(name)}"]`);
    if (!RESTART_ALLOW.has(name)) {
      statusChip(chip, "denied");
      addSvcLog(name, `${name}: restart denied (allowlist)`);
      toast(`再起動拒否: ${name} は allowlist 外です。`, "error");
      setTimeout(() => statusChip(chip, "active"), 1200);
      void renderLogs();
      renderServicePreview(name);
      return;
    }

    // Try live API first, fallback to mock behavior
    if (state.session && state.api) {
      statusChip(chip, "restarting");
      try {
        const live = await state.api.tryLive(
          () => state.api.api.services.restart(name),
          { op: "services.restart" }
        );
        if (live.live && live.data) {
          const normalized = normalizeServiceRestartPayload(live.data);
          statusChip(chip, normalized.current_status || "active");
          addSvcLog(name, `${name}: ${normalized.message || "restart completed"}`);
          toast(normalized.message || `${name} を再起動しました。`, "success");
          void renderLogs();
          renderServicePreview(name);
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") {
          statusChip(chip, "active");
          toast(explainApiError(err).message, "error");
          return;
        }
      }
    }

    statusChip(chip, "restarting");
    addSvcLog(name, `${name}: restart requested`);
    toast(`${name} を再起動しました（モック）。`, "success");
    setTimeout(() => {
      statusChip(chip, "active");
      addSvcLog(name, `${name}: restart completed`);
      const cpuCell = document.querySelector(`[data-service-cpu="${escSel(name)}"]`);
      if (cpuCell) {
        const v = clamp((+String(cpuCell.textContent).replace("%", "") || 0) + rand(0.2, 1.8), 0, 99);
        cpuCell.textContent = `${v.toFixed(1)}%`;
      }
      void renderLogs();
      renderServicePreview(name);
    }, 900);
  }

  function addSvcLog(name, line) {
    const t = new Date().toLocaleTimeString("ja-JP", { hour12: false });
    const entry = `Feb 24 ${t} ${line}`;
    if (state.services[name]) {
      state.services[name].logs.push(entry);
      if (state.services[name].logs.length > 200) state.services[name].logs.shift();
    }
    if (name !== "linux-management-prod" && state.services["linux-management-prod"]) {
      state.services["linux-management-prod"].logs.push(`Feb 24 ${t} api: ${line}`);
    }
  }

  async function renderLogs() {
    const svc = dom.logsService?.value || state.selectedService || "nginx";
    const max = clamp(parseInt(dom.logsLines?.value || "100", 10), 1, 1000);
    const q = (dom.logsQ?.value || "").trim().toLowerCase();
    if (state.session && state.api) {
      try {
        const live = await state.api.tryLive(
          () => state.api.api.logs.get(svc, { lines: max, q: q || undefined }),
          { op: "logs.get" }
        );
        if (live.live && live.data) {
          const normalized = normalizeLogsPayload(live.data);
          const lines = (normalized.logs || []).filter((l) => !q || l.toLowerCase().includes(q)).slice(-max);
          renderTerminal(dom.logsTerminal, lines.length ? lines : ["(no log lines matched filters)"]);
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") toast(explainApiError(err).message, "error");
      }
    }
    const src = [...(state.services[svc]?.logs || [])];
    const lines = src.filter((l) => !q || l.toLowerCase().includes(q)).slice(-max);
    renderTerminal(dom.logsTerminal, lines.length ? lines : ["(no log lines matched filters)"]);
  }

  function filterAudit() {
    const op = dom.auditOp?.value || "all";
    const st = dom.auditStatus?.value || "all";
    const q = (dom.auditQ?.value || "").trim().toLowerCase();
    qsa("tr[data-audit-row]", dom.auditTable).forEach((r) => {
      const ok = (op === "all" || r.dataset.op === op)
        && (st === "all" || r.dataset.status === st)
        && (!q || (r.textContent || "").toLowerCase().includes(q));
      r.classList.toggle("hidden", !ok);
    });
  }

  function filterUsersGroups() {
    const uq = (dom.usersSearch?.value || "").trim().toLowerCase();
    const us = dom.usersStatus?.value || "all";
    const gq = (dom.groupsSearch?.value || "").trim().toLowerCase();
    qsa("tr[data-user-row]", dom.usersTable).forEach((r) => {
      const ok = (!uq || (r.textContent || "").toLowerCase().includes(uq))
        && (us === "all" || r.dataset.userStatus === us);
      r.classList.toggle("hidden", !ok);
    });
    qsa("tr[data-group-row]", dom.groupsTable).forEach((r) => {
      const t = (r.textContent || "").toLowerCase();
      const ok = !gq || t.includes(gq) || (r.dataset.groupName || "").toLowerCase().includes(gq);
      r.classList.toggle("hidden", !ok);
    });
  }

  async function loadCronFromApi() {
    if (!state.session || !state.api || !dom.cronTable) return;
    try {
      const live = await state.api.tryLive(() => state.api.api.cron.list(), { op: "cron.list" });
      if (!live.live || !live.data) return;
      try {
        const normalized = normalizeCronListPayload(live.data);
        renderCronTableFromApi(normalized);
      } catch (err) {
        console.warn("[webui-sample] cron adapter fallback", err);
      }
    } catch (err) {
      if (state.api.settings.mode === "live") toast(explainApiError(err).message, "error");
    }
  }

  function renderCronTableFromApi(data) {
    const body = dom.cronTable?.tBodies?.[0];
    if (!body) return;
    const jobs = data.jobs || [];
    body.innerHTML = "";
    const frag = document.createDocumentFragment();
    jobs.forEach((job) => {
      const tr = document.createElement("tr");
      tr.dataset.cronId = job.id;
      tr.innerHTML =
        `<td class="mono">${escHtml(job.id)}</td>` +
        `<td>${escHtml(job.owner || "")}</td>` +
        `<td><div class="mono">${escHtml(job.schedule)}</div><div class="muted small">${escHtml(job.schedule_human || "")}</div></td>` +
        `<td><div class="mono">${escHtml(job.command)}</div><div class="muted small truncate-cell">${escHtml(job.arguments || "-")}</div></td>` +
        `<td><span class="chip ${job.enabled ? "chip-success" : "chip-muted"}" data-cron-status>${job.enabled ? "Active" : "Disabled"}</span></td>` +
        `<td><div class="inline-actions"><button class="btn btn-mini btn-soft" data-cron-toggle="${escHtml(job.id)}">[T]</button><button class="btn btn-mini btn-danger-soft" data-open-modal="cron-delete" data-cron-id="${escHtml(job.id)}">[D]</button></div></td>`;
      frag.appendChild(tr);
    });
    body.appendChild(frag);
  }

  async function loadUsersFromApi() {
    if (!state.session || !state.api) return;
    const [usersRes, groupsRes] = await Promise.allSettled([
      state.api.tryLive(() => state.api.api.users.list(), { op: "users.list" }),
      state.api.tryLive(() => state.api.api.users.listGroups(), { op: "groups.list" }),
    ]);
    if (usersRes.status === "fulfilled" && usersRes.value.live && usersRes.value.data) {
      try { renderUsersTableFromApi(normalizeUsersListPayload(usersRes.value.data)); } catch (err) { console.warn(err); }
    }
    if (groupsRes.status === "fulfilled" && groupsRes.value.live && groupsRes.value.data) {
      try { renderGroupsTableFromApi(normalizeGroupsListPayload(groupsRes.value.data)); } catch (err) { console.warn(err); }
    }
    if (state.api.settings.mode === "live") {
      if (usersRes.status === "rejected") toast(explainApiError(usersRes.reason).message, "error");
      if (groupsRes.status === "rejected") toast(explainApiError(groupsRes.reason).message, "error");
    }
    filterUsersGroups();
  }

  function renderUsersTableFromApi(data) {
    const body = dom.usersTable?.tBodies?.[0];
    if (!body) return;
    const users = data.users || [];
    body.innerHTML = "";
    const frag = document.createDocumentFragment();
    users.forEach((u) => {
      const tr = document.createElement("tr");
      tr.dataset.userRow = "";
      tr.dataset.userName = u.username;
      tr.dataset.userStatus = u.locked ? "locked" : "active";
      tr.dataset.userGroups = (u.groups || []).join(" ");
      tr.innerHTML =
        `<td><strong>${escHtml(u.username)}</strong></td>` +
        `<td class="mono">${escHtml(u.uid)}</td>` +
        `<td>${(u.groups || []).map((g) => `<span class="chip chip-outline">${escHtml(g)}</span>`).join(" ") || '<span class="muted">-</span>'}</td>` +
        `<td class="mono">${escHtml(u.home || "")}</td>` +
        `<td class="mono">${escHtml(u.shell || "")}</td>` +
        `<td><span class="chip ${u.locked ? "chip-muted" : "chip-success"}">${u.locked ? "Locked" : "Active"}</span></td>` +
        `<td>${escHtml(u.last_login || "-")}</td>` +
        `<td><div class="inline-actions"><button class="btn btn-mini btn-soft" data-quick-approval="user_passwd" data-target-name="${escHtml(u.username)}">PW変更申請</button><button class="btn btn-mini btn-danger-soft" data-quick-approval="user_delete" data-target-name="${escHtml(u.username)}">削除申請</button></div></td>`;
      frag.appendChild(tr);
    });
    body.appendChild(frag);
  }

  function renderGroupsTableFromApi(data) {
    const body = dom.groupsTable?.tBodies?.[0];
    if (!body) return;
    const groups = data.groups || [];
    body.innerHTML = "";
    const frag = document.createDocumentFragment();
    groups.forEach((g) => {
      const tr = document.createElement("tr");
      tr.dataset.groupRow = "";
      tr.dataset.groupName = g.group;
      const riskClass = g.risk === "CRITICAL" ? "chip-critical" : g.risk === "HIGH" ? "chip-high" : g.risk === "MEDIUM" ? "chip-medium" : "chip-low";
      const action = g.members?.length
        ? `<button class="btn btn-mini btn-soft" data-quick-approval="group_modify" data-target-name="${escHtml(g.group)}">メンバー変更申請</button>`
        : `<button class="btn btn-mini btn-danger-soft" data-quick-approval="group_delete" data-target-name="${escHtml(g.group)}">削除申請</button>`;
      tr.innerHTML =
        `<td><strong>${escHtml(g.group)}</strong></td>` +
        `<td class="mono">${escHtml(g.gid)}</td>` +
        `<td>${(g.members || []).length ? g.members.map((m) => `<span class="chip chip-outline">${escHtml(m)}</span>`).join(" ") : '<span class="muted">No members</span>'}</td>` +
        `<td><span class="chip chip-risk ${riskClass}">${escHtml(g.risk || "LOW")}</span></td>` +
        `<td>${action}</td>`;
      frag.appendChild(tr);
    });
    body.appendChild(frag);
  }

  function renderTerminal(el, lines) {
    if (!el) return;
    el.innerHTML = "";
    const f = document.createDocumentFragment();
    (lines || []).forEach((l) => {
      const d = document.createElement("div");
      d.textContent = l;
      f.appendChild(d);
    });
    el.appendChild(f);
  }

  function statusChip(el, status) {
    if (!el) return;
    const s = String(status || "").toLowerCase();
    el.textContent = s;
    el.classList.remove("chip-success", "chip-warning", "chip-danger", "chip-muted", "chip-outline");
    if (["active", "approved", "executed", "success"].includes(s)) el.classList.add("chip-success");
    else if (["pending", "attempt", "restarting"].includes(s)) el.classList.add("chip-warning");
    else if (["rejected", "denied", "failure", "execution_failed"].includes(s)) el.classList.add("chip-danger");
    else if (["expired", "cancelled", "disabled"].includes(s)) el.classList.add("chip-muted");
    else el.classList.add("chip-outline");
  }

  function riskChip(el, risk) {
    if (!el) return;
    const r = String(risk || "MEDIUM").toUpperCase();
    el.textContent = r;
    el.className = "chip chip-risk";
    el.classList.add(r === "CRITICAL" ? "chip-critical" : r === "HIGH" ? "chip-high" : r === "MEDIUM" ? "chip-medium" : "chip-low");
  }

  function toast(msg, tone = "info", ms = 2600) {
    if (!dom.toastStack) return;
    const n = document.createElement("div");
    n.className = `toast toast-${tone}`;
    n.textContent = msg;
    dom.toastStack.appendChild(n);
    requestAnimationFrame(() => n.classList.add("show"));
    setTimeout(() => { n.classList.remove("show"); setTimeout(() => n.remove(), 220); }, ms);
  }
  function onClick(e) {
    const t = e.target;
    const accBtn = t.closest("[data-accordion-toggle]");
    if (accBtn) {
      e.preventDefault();
      const acc = accBtn.closest(".accordion");
      acc?.classList.toggle("expanded");
      syncAccordion(acc, accBtn);
      return;
    }

    const tab = t.closest(".tab[data-tab-group][data-tab-id]");
    if (tab) {
      e.preventDefault();
      activateTab(tab.dataset.tabGroup, tab.dataset.tabId);
      return;
    }

    const draftReset = t.closest("[data-approval-draft-reset]");
    if (draftReset) {
      e.preventDefault();
      openDraftReset();
      toast("承認リクエストのテンプレートを再読込しました。", "info");
      return;
    }

    const nav = t.closest("[data-scroll-target]");
    if (nav) {
      e.preventDefault();
      activateSection(nav.dataset.scrollTarget, true);
      if (window.innerWidth <= 1024) setSidebar(false);
      return;
    }

    const open = t.closest("[data-open-modal]");
    if (open && !open.disabled) {
      e.preventDefault();
      openModalByName(open.dataset.openModal, open);
      return;
    }

    if (dom.modalLayer?.classList.contains("active")) {
      const close = t.closest("[data-close-modal]");
      if (close) { e.preventDefault(); closeModal(); return; }
      const ok = t.closest("#confirmOkBtn");
      if (ok) {
        e.preventDefault();
        const fn = state.confirmFn;
        closeModal();
        state.confirmFn = null;
        if (typeof fn === "function") fn();
        return;
      }
    }

    const svcSel = t.closest("[data-service-select]");
    if (svcSel) {
      e.preventDefault();
      renderServicePreview(svcSel.dataset.serviceSelect);
      if (dom.logsService) dom.logsService.value = svcSel.dataset.serviceSelect;
      void renderLogs();
      return;
    }

    const svcRestart = t.closest("[data-service-restart]");
    if (svcRestart) { e.preventDefault(); void restartService(svcRestart.dataset.serviceRestart); return; }

    const procBtn = t.closest("#procRefreshBtn");
    if (procBtn) { e.preventDefault(); void refreshProcesses(true); toast("プロセス一覧を再取得しました。", "info"); return; }

    const autoBtn = t.closest("#procAutoBtn");
    if (autoBtn) {
      e.preventDefault();
      const on = autoBtn.dataset.procAuto !== "on";
      if (state.procAuto) { clearInterval(state.procAuto); state.procAuto = null; }
      if (on) {
        state.procAuto = setInterval(() => state.session && void refreshProcesses(true), PROC_AUTO_MS);
        autoBtn.dataset.procAuto = "on";
        autoBtn.textContent = "■ Auto-refresh (5s)";
        toast("プロセス自動更新を開始しました。", "info");
      } else {
        autoBtn.dataset.procAuto = "off";
        autoBtn.textContent = "▶ Auto-refresh (5s)";
        toast("プロセス自動更新を停止しました。", "warning");
      }
      return;
    }

    const pRow = t.closest("tr[data-proc-row]");
    if (pRow && dom.procTable?.contains(pRow)) { selectProcess(pRow); return; }

    const apSel = t.closest("[data-approval-select]");
    if (apSel) {
      e.preventDefault();
      selectApproval(apSel.dataset.approvalSelect);
      if (!apSel.closest("#sec-approvals")) activateSection("sec-approvals", true);
      return;
    }

    const cronToggle = t.closest("[data-cron-toggle]");
    if (cronToggle) {
      e.preventDefault();
      const id = cronToggle.dataset.cronToggle;
      openConfirm(`Cronジョブ ${id} の有効/無効切替申請を作成しますか？`, () => {
        void submitCronToggleRequest(id, cronToggle.closest("tr"));
      });
      return;
    }

    const quick = t.closest("[data-quick-approval]");
    if (quick) {
      e.preventDefault();
      const typ = quick.dataset.quickApproval || "user_add";
      const target = quick.dataset.targetName || "";
      if ([...dom.approvalDraftType.options].some((o) => o.value === typ)) {
        dom.approvalDraftType.value = typ;
        applyDraftDefaults();
        if (target) qsa("[data-approval-field]", dom.approvalDraftFields).forEach((i) => {
          if (typ.startsWith("user_") && i.dataset.approvalField === "username") i.value = target;
          if (typ.startsWith("group_") && i.dataset.approvalField === "group") i.value = target;
        });
        if (dom.approvalDraftReason) dom.approvalDraftReason.value = `${(APPROVAL_META[typ] || { label: typ }).label} のため ${target} を対象に申請します。`;
        renderDraftPreview();
        activateTab("approvals", "ap-create", false);
        activateSection("sec-approvals", true);
      } else {
        const rec = createApproval({ type: typ, reason: `${(APPROVAL_META[typ] || { label: typ }).label} 申請: ${target}`, payload: typ.startsWith("group_") ? { group: target } : { username: target } });
        addApprovalRows(rec);
        syncApprovalUI();
        activateSection("sec-approvals", true);
        toast(`クイック申請を作成しました: ${rec.id}`, "success");
      }
      return;
    }

    const exp = t.closest("[data-export]");
    if (exp) { e.preventDefault(); toast(`エクスポート（${exp.dataset.export.toUpperCase()}）を開始（モック）`, "info"); return; }
    const save = t.closest("[data-action='settings-save']");
    if (save) { e.preventDefault(); toast("監査ログ設定を保存しました（モック）。", "success"); return; }
  }

  function onInput(e) {
    const id = e.target.id;
    if (["procMinCpu", "procMinMem", "procLimit"].includes(id)) return refreshProcesses(false);
    if (["usersSearch", "groupsSearch"].includes(id)) return filterUsersGroups();
    if (["logsQ"].includes(id)) return renderLogs();
    if (["auditQ"].includes(id)) return filterAudit();
    if (e.target.closest("#approvalDraftFields") || id === "approvalDraftReason") return renderDraftPreview();
  }

  function onChange(e) {
    const id = e.target.id;
    if (["procSort", "procUser", "procMinCpu", "procMinMem", "procLimit"].includes(id)) return refreshProcesses(false);
    if (["logsService", "logsLines"].includes(id)) return renderLogs();
    if (["usersStatus"].includes(id)) return filterUsersGroups();
    if (["auditOp", "auditStatus"].includes(id)) return filterAudit();
    if (["approvalPendingType", "approvalPendingRequester", "approvalMyStatus", "approvalHistoryStatus", "approvalPeriod"].includes(id)) {
      syncApprovalUI(id === "approvalPeriod");
      void refreshApprovalsFromApi();
      return;
    }
    if (id === "approvalDraftType") { applyDraftDefaults(); renderDraftPreview(); return; }
    if (id === "cronPresetSelect") {
      const f = e.target.closest("form");
      const inp = f?.querySelector('input[name="schedule"]');
      if (inp) inp.value = e.target.value;
    }
  }

  function onSubmit(e) {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.id === "loginForm") return;
    const kind = form.dataset.form;
    if (!kind) return;
    e.preventDefault();
    if (kind === "approval-draft") return void submitDraft(form);
    if (kind === "cron-add") return void submitCronAdd(form);
    if (kind === "user-add") return void submitUserAdd(form);
    if (kind === "service-stop") return void submitServiceStop(form);
    if (kind === "approval-action") return void submitApprovalAction(form);
  }

  async function refreshApprovalsFromApi() {
    if (!state.session || !state.api) return;
    const pendingParams = {};
    if ((dom.approvalPendingType?.value || "all") !== "all") pendingParams.request_type = dom.approvalPendingType.value;
    if ((dom.approvalPendingRequester?.value || "all") !== "all") pendingParams.requester_id = dom.approvalPendingRequester.value;

    const myParams = {};
    if ((dom.approvalMyStatus?.value || "all") !== "all") myParams.status = dom.approvalMyStatus.value;

    const historyParams = { period: dom.approvalPeriod?.value || "30d" };
    if ((dom.approvalHistoryStatus?.value || "all") !== "all") historyParams.status = dom.approvalHistoryStatus.value;

    const [pendingRes, myRes, histRes] = await Promise.allSettled([
      state.api.tryLive(() => state.api.api.approvals.pending(pendingParams), { op: "approval.pending" }),
      state.api.tryLive(() => state.api.api.approvals.myRequests(myParams), { op: "approval.my" }),
      state.api.tryLive(() => state.api.api.approvals.history(historyParams), { op: "approval.history" }),
    ]);

    if (pendingRes.status === "fulfilled" && pendingRes.value.live && pendingRes.value.data) {
      applyPendingApprovalsFromApi(normalizeApprovalListPayload(pendingRes.value.data, "pending"));
    }
    if (myRes.status === "fulfilled" && myRes.value.live && myRes.value.data) {
      applyMyApprovalsFromApi(normalizeApprovalListPayload(myRes.value.data, "my"));
    }
    if (histRes.status === "fulfilled" && histRes.value.live && histRes.value.data) {
      applyApprovalHistoryFromApi(histRes.value.data);
    }

    if (state.api.settings.mode === "live") {
      if (pendingRes.status === "rejected") toast(explainApiError(pendingRes.reason).message, "error");
      if (myRes.status === "rejected") toast(explainApiError(myRes.reason).message, "error");
      if (histRes.status === "rejected") toast(explainApiError(histRes.reason).message, "error");
    }

    syncApprovalUI(false);
  }

  function applyPendingApprovalsFromApi(data) {
    const body = dom.approvalPendingTable?.tBodies?.[0];
    if (!body) return;
    body.innerHTML = "";
    (data.requests || []).forEach((r) => {
      upsertApprovalFromListItem(r, "pending");
      addPendingRow({
        id: r.id,
        type: r.request_type,
        requester: r.requester_name || r.requester_id || "unknown",
        status: "pending",
        risk: r.risk_level,
        reason: r.reason,
      }, {
        ttlText: Number.isFinite(r.remaining_hours) && r.remaining_hours > 0 ? `${r.remaining_hours.toFixed(1)}h 残` : "期限不明",
      });
    });
  }

  function applyMyApprovalsFromApi(data) {
    const body = dom.approvalMyTable?.tBodies?.[0];
    if (!body) return;
    body.innerHTML = "";
    (data.requests || []).forEach((r) => {
      upsertApprovalFromListItem(r, "my");
      addMyRow({
        id: r.id,
        type: r.request_type,
        requester: state.session?.username || "operator",
        status: r.status,
        risk: r.risk_level,
        reason: r.reason,
      }, { createdText: isoToUi(r.created_at) });
    });
  }

  function applyApprovalHistoryFromApi(payload) {
    const root = payload?.data ?? payload ?? {};
    const body = dom.approvalHistoryTable?.tBodies?.[0];
    if (!body) return;
    if (!Array.isArray(root.history)) return;
    const latestByReq = new Map();
    for (const item of root.history) {
      const reqId = String(item.approval_request_id || item.request_id || "");
      if (!reqId) continue;
      const prev = latestByReq.get(reqId);
      const ts = Date.parse(item.timestamp || 0) || 0;
      const prevTs = Date.parse(prev?.timestamp || 0) || 0;
      if (!prev || ts >= prevTs) latestByReq.set(reqId, item);
      if (!state.approvals[reqId]) {
        state.approvals[reqId] = {
          id: reqId,
          type: item.request_type || "unknown",
          requester: item.actor_name || "unknown",
          requesterRole: item.actor_role || "Operator",
          status: normalizeApprovalStatus(item.new_status || "pending"),
          risk: (APPROVAL_META[item.request_type] || { risk: "MEDIUM" }).risk,
          reason: "",
          payload: {},
          timeline: [],
        };
      }
    }
    body.innerHTML = "";
    [...latestByReq.values()]
      .sort((a, b) => (Date.parse(b.timestamp || 0) || 0) - (Date.parse(a.timestamp || 0) || 0))
      .forEach((item) => {
        const reqId = String(item.approval_request_id || item.request_id || "");
        const rec = state.approvals[reqId];
        if (rec) {
          rec.type = item.request_type || rec.type;
          rec.status = normalizeApprovalStatus(item.new_status || rec.status);
        }
        addHistoryRow({
          id: reqId,
          type: item.request_type || rec?.type || "unknown",
          requester: item.actor_name || rec?.requester || "-",
          status: normalizeApprovalStatus(item.new_status || rec?.status || "pending"),
        }, item.actor_name || "-", { timeText: isoToUi(item.timestamp) });
      });
  }

  function upsertApprovalFromListItem(item, source) {
    if (!item?.id) return;
    const current = state.approvals[item.id] || {
      id: item.id,
      type: item.request_type,
      requester: item.requester_name || "unknown",
      requesterRole: "Operator",
      status: "pending",
      risk: item.risk_level || "MEDIUM",
      reason: "",
      payload: {},
      timeline: [],
    };
    current.type = item.request_type || current.type;
    current.risk = item.risk_level || current.risk;
    current.reason = item.reason || current.reason;
    current.requester = item.requester_name || current.requester;
    if (item.status) current.status = normalizeApprovalStatus(item.status);
    if (!current.timeline?.length && item.created_at) current.timeline = [{ tone: "info", title: `created / ${current.requester}`, time: isoToUi(item.created_at) }];
    state.approvals[item.id] = current;
    if (source === "my" && item.approved_by_name) {
      current.approved_by = item.approved_by_name;
    }
  }

  async function loadApprovalDetailFromApi(id) {
    if (!state.session || !state.api || !id) return;
    const live = await state.api.tryLive(() => state.api.api.approvals.detail(id), { op: "approval.detail" });
    if (!live.live || !live.data) return;
    const d = normalizeApprovalDetailPayload(live.data);
    if (!d || !d.id) return;
    const rec = state.approvals[d.id] || { id: d.id, type: d.request_type, requester: d.requester_name || "unknown", requesterRole: "Operator", status: d.status, risk: d.risk_level, reason: d.reason, payload: {}, timeline: [] };
    rec.type = d.request_type;
    rec.risk = d.risk_level;
    rec.requester = d.requester_name || rec.requester;
    rec.reason = d.reason || rec.reason;
    rec.status = normalizeApprovalStatus(d.status);
    rec.payload = d.request_payload || rec.payload;
    rec.timeline = (d.history || []).map((h) => ({
      tone: h.action === "approved" || h.action === "executed" ? "success" : h.action === "rejected" || h.action === "cancelled" ? "warning" : "info",
      title: `${h.action} / ${h.actor_name || h.actor_id || "system"} (${h.actor_role || "-"})${h.details?.comment ? ` - ${h.details.comment}` : ""}${h.details?.reason ? ` - ${h.details.reason}` : ""}`,
      time: isoToUi(h.timestamp),
    }));
    state.approvals[d.id] = rec;
    renderApprovalDetail(rec);
  }

  function syncApprovalUI(periodToast) {
    syncApprovalRows();
    const tp = dom.approvalPendingType?.value || "all";
    const rq = dom.approvalPendingRequester?.value || "all";
    qsa("tr[data-approval-row]", dom.approvalPendingTable).forEach((r) => {
      const rec = state.approvals[rowApId(r)];
      const ok = rec && rec.status === "pending"
        && (tp === "all" || rec.type === tp)
        && (rq === "all" || rec.requester === rq);
      r.classList.toggle("hidden", !ok);
    });
    const ms = dom.approvalMyStatus?.value || "all";
    qsa("tr[data-my-approval-row]", dom.approvalMyTable).forEach((r) => {
      const rec = state.approvals[rowApId(r)];
      const ok = rec && (ms === "all" || rec.status === ms);
      r.classList.toggle("hidden", !ok);
    });
    const hs = dom.approvalHistoryStatus?.value || "all";
    qsa("tr[data-history-row]", dom.approvalHistoryTable).forEach((r) => {
      const rec = state.approvals[rowApId(r)];
      const st = rec?.status || r.dataset.historyStatus;
      r.classList.toggle("hidden", !(hs === "all" || st === hs));
    });
    txt(dom.pendingCountValue, String(Object.values(state.approvals).filter((a) => a.status === "pending").length));
    renderDraftPreview();
    const curId = (dom.approvalDetailId?.textContent || "").trim();
    if (curId && state.approvals[curId]) renderApprovalDetail(state.approvals[curId]);
    if (periodToast) toast(`承認履歴期間を ${dom.approvalPeriod.value} に変更`, "info");
  }

  function syncApprovalRows() {
    qsa("tr[data-approval-row], tr[data-my-approval-row], tr[data-history-row]").forEach((r) => {
      const id = rowApId(r);
      const rec = state.approvals[id];
      if (!rec) return;
      if (r.dataset.approvalRow !== undefined) r.dataset.approvalStatus = rec.status;
      if (r.dataset.myApprovalRow !== undefined) r.dataset.approvalStatus = rec.status;
      if (r.dataset.historyRow !== undefined) r.dataset.historyStatus = rec.status;
      const chip = r.querySelector(".approval-status-chip")
        || (r.dataset.myApprovalRow !== undefined ? r.querySelector("td:nth-child(3) .chip") : null)
        || (r.dataset.historyRow !== undefined ? r.querySelector("td:nth-child(5) .chip") : null);
      if (chip) statusChip(chip, rec.status);
      const lastTd = r.querySelector("td:last-child");
      if (lastTd && (r.dataset.approvalRow !== undefined || r.dataset.myApprovalRow !== undefined)) {
        if (rec.status === "pending" && r.dataset.myApprovalRow !== undefined) {
          lastTd.innerHTML = `<button class="btn btn-mini btn-danger-soft" data-open-modal="approval-action" data-approval-op="cancel" data-approval-id="${escHtml(id)}">キャンセル</button>`;
        } else if (rec.status !== "pending" && r.dataset.approvalRow !== undefined) {
          lastTd.innerHTML = `<button class="btn btn-mini btn-soft" data-approval-select="${escHtml(id)}">詳細</button>`;
        } else if (rec.status !== "pending" && r.dataset.myApprovalRow !== undefined) {
          lastTd.innerHTML = `<button class="btn btn-mini btn-soft" data-approval-select="${escHtml(id)}">詳細</button>`;
        }
      }
    });
  }

  function rowApId(row) {
    return row.dataset.approvalId || row.querySelector("[data-approval-select]")?.dataset.approvalSelect || row.cells?.[0]?.textContent?.trim() || "";
  }

  function selectApproval(id) {
    const rec = state.approvals[id];
    if (!rec) return;
    renderApprovalDetail(rec);
    void loadApprovalDetailFromApi(id);
    qsa("[data-approval-select]").forEach((b) => {
      const on = b.dataset.approvalSelect === id;
      b.style.outline = on ? "2px solid #d8e8fb" : "";
      b.style.outlineOffset = on ? "2px" : "";
    });
  }

  function renderApprovalDetail(rec) {
    txt(dom.approvalDetailTitle, (APPROVAL_META[rec.type] || { label: rec.type }).label);
    txt(dom.approvalDetailId, rec.id);
    statusChip(dom.approvalDetailStatus, rec.status);
    riskChip(dom.approvalDetailRisk, rec.risk);
    txt(dom.approvalDetailRequesterRole, rec.requesterRole);
    txt(dom.approvalDetailRequester, `${rec.requester} (user_${Math.abs(hash(rec.requester)).toString().slice(0, 3)})`);
    txt(dom.approvalDetailReason, rec.reason);
    txt(dom.approvalDetailPayload, JSON.stringify(rec.payload || {}, null, 2));
    renderTimeline(dom.approvalDetailTimeline, rec.timeline || []);
  }

  function renderTimeline(el, items) {
    if (!el) return;
    el.innerHTML = "";
    const f = document.createDocumentFragment();
    items.forEach((it) => {
      const row = document.createElement("div");
      row.className = "timeline-item";
      row.innerHTML = `<div class="timeline-dot ${it.tone || "info"}"></div><div><div class="timeline-title">${escHtml(it.title || "")}</div><div class="timeline-text">${escHtml(it.time || "")}</div></div>`;
      f.appendChild(row);
    });
    el.appendChild(f);
  }

  function applyDraftDefaults() {
    const type = dom.approvalDraftType?.value || "user_add";
    const defs = {
      user_add: { username: "newuser", group: "developers", home: "/home/newuser", shell: "/bin/bash" },
      user_delete: { username: "tempstaff" },
      cron_add: { schedule: "0 2 * * *", command: "/usr/bin/rsync" },
      cron_modify: { schedule: "*/10 * * * *", command: "/usr/local/bin/healthcheck.sh" },
      service_stop: { service: "nginx" },
      group_modify: { group: "developers" },
      group_delete: { group: "legacyops" },
      user_passwd: { username: "kensan" },
      firewall_modify: { rule: "allow tcp/443" },
    }[type] || {};
    qsa("[data-approval-field]", dom.approvalDraftFields).forEach((i) => { i.value = defs[i.dataset.approvalField] || ""; });
    if (dom.approvalDraftReason) dom.approvalDraftReason.value = `${(APPROVAL_META[type] || { label: type }).label} のため承認を依頼します。`;
  }

  function draftPayload() {
    const p = {};
    qsa("[data-approval-field]", dom.approvalDraftFields).forEach((i) => {
      const v = (i.value || "").trim();
      if (v) p[i.dataset.approvalField] = v;
    });
    return p;
  }

  function renderDraftPreview() {
    if (!dom.approvalDraftType) return;
    const type = dom.approvalDraftType.value;
    const meta = APPROVAL_META[type] || { risk: "MEDIUM", roles: "Approver", timeout: "24h" };
    txt(dom.approvalPreviewType, type);
    riskChip(dom.approvalPreviewRisk, meta.risk);
    txt(dom.approvalPreviewRoles, meta.roles);
    txt(dom.approvalPreviewTimeout, meta.timeout);
    txt(dom.approvalPreviewPayload, JSON.stringify(draftPayload(), null, 2));
  }

  async function submitDraft() {
    const type = dom.approvalDraftType?.value || "user_add";
    const reason = (dom.approvalDraftReason?.value || "").trim();
    if (reason.length < 5) return toast("申請理由は5文字以上で入力してください。", "error");
    const payload = draftPayload();
    if (state.session && state.api) {
      try {
        const live = await state.api.tryLive(
          () => state.api.api.approvals.create({ request_type: type, payload, reason }),
          { op: "approval.request" }
        );
        if (live.live && live.data) {
          const resp = live.data?.data ?? live.data;
          const rec = createApproval({ type, reason, payload, forceId: resp.request_id || undefined });
          if (resp.risk_level) rec.risk = resp.risk_level;
          addApprovalRows(rec);
          syncApprovalUI();
          activateTab("approvals", "ap-my", false);
          selectApproval(rec.id);
          void refreshApprovalsFromApi();
          toast(resp.message || `承認リクエストを作成しました: ${rec.id}`, "success");
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") { toast(explainApiError(err).message, "error"); return; }
      }
    }
    const rec = createApproval({ type, reason, payload });
    addApprovalRows(rec);
    syncApprovalUI();
    activateTab("approvals", "ap-my", false);
    selectApproval(rec.id);
    toast(`承認リクエストを作成しました: ${rec.id}`, "success");
  }

  function createApproval({ type, reason, payload, forceId }) {
    const id = forceId || `apr-${state.nextApprovalId++}`;
    if (forceId) {
      const m = String(forceId).match(/(\d+)$/);
      if (m) state.nextApprovalId = Math.max(state.nextApprovalId, Number(m[1]) + 1);
    }
    const req = state.session?.username || "operator";
    const role = roleLabel(state.session?.role || "Operator");
    const meta = APPROVAL_META[type] || { risk: "MEDIUM" };
    const rec = { id, type, requester: req, requesterRole: role, status: "pending", risk: meta.risk, reason, payload: payload || {}, timeline: [
      { tone: "info", title: `created / ${req} (${role})`, time: nowLong() }
    ]};
    state.approvals[id] = rec;
    return rec;
  }

  function addApprovalRows(rec) {
    addPendingRow(rec);
    addMyRow(rec);
  }

  function addPendingRow(rec, opts = {}) {
    const body = dom.approvalPendingTable?.tBodies?.[0];
    if (!body || body.querySelector(`[data-approval-id="${escSel(rec.id)}"]`)) return;
    const tr = document.createElement("tr");
    tr.dataset.approvalRow = "";
    tr.dataset.approvalId = rec.id;
    tr.dataset.approvalType = rec.type;
    tr.dataset.approvalRequester = rec.requester;
    tr.dataset.approvalStatus = rec.status;
    tr.innerHTML = `<td class="mono">${escHtml(rec.id)}</td><td>${escHtml((APPROVAL_META[rec.type] || { label: rec.type }).label)}</td><td>${escHtml(rec.requester)}</td><td>${riskChipHtml(rec.risk)}</td><td>${escHtml(rec.reason)}</td><td>${escHtml(opts.ttlText || "24.0h 残")}</td><td><span class="chip chip-warning approval-status-chip">pending</span></td><td><div class="inline-actions"><button class="btn btn-mini btn-soft" data-approval-select="${escHtml(rec.id)}">詳細</button><button class="btn btn-mini btn-success-soft" data-open-modal="approval-action" data-approval-op="approve" data-approval-id="${escHtml(rec.id)}">承認</button><button class="btn btn-mini btn-danger-soft" data-open-modal="approval-action" data-approval-op="reject" data-approval-id="${escHtml(rec.id)}">拒否</button></div></td>`;
    body.prepend(tr);
  }

  function addMyRow(rec, opts = {}) {
    const body = dom.approvalMyTable?.tBodies?.[0];
    if (!body || [...body.rows].some((r) => rowApId(r) === rec.id)) return;
    const tr = document.createElement("tr");
    tr.dataset.myApprovalRow = "";
    tr.dataset.approvalId = rec.id;
    tr.dataset.approvalStatus = rec.status;
    tr.innerHTML = `<td class="mono">${escHtml(rec.id)}</td><td>${escHtml(rec.type)}</td><td>${statusChipHtml(rec.status || "pending")}</td><td>${escHtml(rec.reason)}</td><td>${escHtml(opts.createdText || nowShort())}</td><td>${(rec.status || "pending") === "pending" ? `<button class="btn btn-mini btn-danger-soft" data-open-modal="approval-action" data-approval-op="cancel" data-approval-id="${escHtml(rec.id)}">キャンセル</button>` : `<button class="btn btn-mini btn-soft" data-approval-select="${escHtml(rec.id)}">詳細</button>`}</td>`;
    body.prepend(tr);
  }

  function addHistoryRow(rec, approver, opts = {}) {
    const body = dom.approvalHistoryTable?.tBodies?.[0];
    if (!body || [...body.rows].some((r) => rowApId(r) === rec.id)) return;
    const tr = document.createElement("tr");
    tr.dataset.historyRow = "";
    tr.dataset.approvalId = rec.id;
    tr.dataset.historyStatus = rec.status;
    tr.innerHTML = `<td>${escHtml(opts.timeText || nowShort())}</td><td>${escHtml(rec.type)}</td><td>${escHtml(rec.requester)}</td><td>${escHtml(approver || "-")}</td><td>${statusChipHtml(rec.status)}</td><td><button class="btn btn-mini btn-soft" data-approval-select="${escHtml(rec.id)}">詳細</button></td>`;
    body.prepend(tr);
  }

  function riskChipHtml(r) {
    const s = String(r || "MEDIUM").toUpperCase();
    const c = s === "CRITICAL" ? "chip-critical" : s === "HIGH" ? "chip-high" : s === "MEDIUM" ? "chip-medium" : "chip-low";
    return `<span class="chip chip-risk ${c}">${escHtml(s)}</span>`;
  }
  function statusChipHtml(s) {
    const v = String(s || "pending").toLowerCase();
    const c = ["approved", "executed", "success"].includes(v) ? "chip-success" : ["pending", "attempt"].includes(v) ? "chip-warning" : ["rejected", "denied", "failure", "execution_failed"].includes(v) ? "chip-danger" : ["expired", "cancelled", "disabled"].includes(v) ? "chip-muted" : "chip-outline";
    return `<span class="chip ${c}">${escHtml(v)}</span>`;
  }

  function openModalByName(name, trigger) {
    if (name === "cron-delete") {
      return openConfirm(`Cronジョブ ${trigger.dataset.cronId || ""} の削除申請を作成しますか？`, () => {
        void submitCronDeleteRequest(trigger.dataset.cronId || "");
      });
    }
    const map = { "cron-add": "cronAddTemplate", "user-add": "userAddTemplate", "approval-action": "approvalActionTemplate", "service-stop": "serviceStopTemplate" };
    const tpl = byId(map[name]);
    if (!(tpl instanceof HTMLTemplateElement)) return toast(`テンプレート未検出: ${name}`, "error");
    dom.modalLayer.innerHTML = "";
    dom.modalLayer.appendChild(tpl.content.cloneNode(true));
    dom.modalLayer.classList.add("active");
    if (name === "service-stop") {
      const inp = dom.modalLayer.querySelector('input[name="service"]');
      if (inp) inp.value = trigger.dataset.serviceName || inp.value || "nginx";
    }
    if (name === "approval-action") setupApprovalActionModal(trigger.dataset.approvalOp, trigger.dataset.approvalId);
  }

  async function submitCronToggleRequest(id, rowEl) {
    if (state.session && state.api) {
      const currentEnabled = !String(rowEl?.querySelector("[data-cron-status]")?.textContent || "").toLowerCase().includes("disabled");
      try {
        const live = await state.api.tryLive(
          () => state.api.api.cron.toggle(id, { enabled: !currentEnabled, reason: `Cronジョブ ${id} の有効/無効切替` }),
          { op: "cron.toggle" }
        );
        if (live.live && live.data) {
          const res = normalizeCronApprovalPending(live.data);
          const rec = createApproval({ type: "cron_modify", reason: `Cronジョブ ${id} の切替`, payload: { cron_id: id, action: "toggle" }, forceId: res.request_id || undefined });
          addApprovalRows(rec);
          const chip = rowEl?.querySelector("[data-cron-status]");
          if (chip) { chip.className = "chip chip-warning"; chip.textContent = "Pending"; }
          syncApprovalUI();
          toast(res.message || `切替申請を作成しました: ${rec.id}`, "success");
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") { toast(explainApiError(err).message, "error"); return; }
      }
    }
    const rec = createApproval({ type: "cron_modify", reason: `Cronジョブ ${id} の切替`, payload: { cron_id: id, action: "toggle" } });
    addApprovalRows(rec);
    const chip = rowEl?.querySelector("[data-cron-status]");
    if (chip) { chip.className = "chip chip-warning"; chip.textContent = "Pending"; }
    syncApprovalUI();
    toast(`切替申請を作成しました: ${rec.id}`, "success");
  }

  async function submitCronDeleteRequest(id) {
    if (state.session && state.api) {
      try {
        const live = await state.api.tryLive(
          () => state.api.api.cron.delete(id, `Cronジョブ ${id} の削除申請`),
          { op: "cron.delete" }
        );
        if (live.live && live.data) {
          const res = normalizeCronApprovalPending(live.data);
          const rec = createApproval({ type: "cron_modify", reason: `Cronジョブ ${id} の削除申請`, payload: { cron_id: id, action: "delete" }, forceId: res.request_id || undefined });
          addApprovalRows(rec); syncApprovalUI(); toast(res.message || `削除申請を作成しました: ${rec.id}`, "success");
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") { toast(explainApiError(err).message, "error"); return; }
      }
    }
    const rec = createApproval({ type: "cron_modify", reason: `Cronジョブ ${id} の削除申請`, payload: { cron_id: id, action: "delete" } });
    addApprovalRows(rec); syncApprovalUI(); toast(`削除申請を作成しました: ${rec.id}`, "success");
  }

  function setupApprovalActionModal(op, id) {
    const rec = state.approvals[id];
    txt(dom.modalLayer.querySelector("[data-approval-modal-id]"), id || "-");
    txt(dom.modalLayer.querySelector("[data-approval-modal-op]"), op || "-");
    txt(dom.modalLayer.querySelector("[data-approval-modal-label]"), op === "reject" ? "拒否理由 *" : op === "cancel" ? "キャンセル理由" : "承認コメント");
    const ta = dom.modalLayer.querySelector("[data-approval-modal-textarea]");
    if (ta) {
      ta.required = op === "reject";
      ta.placeholder = op === "reject" ? "拒否理由を入力してください。" : "コメント（任意）";
      ta.value = op === "approve" && rec ? `確認済み: ${(APPROVAL_META[rec.type] || { label: rec.type }).label}` : "";
    }
    const idIn = dom.modalLayer.querySelector('input[name="approvalId"]');
    const opIn = dom.modalLayer.querySelector('input[name="op"]');
    if (idIn) idIn.value = id || "";
    if (opIn) opIn.value = op || "";
    const sb = dom.modalLayer.querySelector("[data-approval-modal-submit]");
    if (sb) sb.textContent = op === "reject" ? "拒否する" : op === "cancel" ? "キャンセルする" : "承認する";
  }

  function openConfirm(msg, fn) {
    state.confirmFn = fn;
    const tpl = byId("confirmTemplate");
    if (!(tpl instanceof HTMLTemplateElement)) return;
    dom.modalLayer.innerHTML = "";
    dom.modalLayer.appendChild(tpl.content.cloneNode(true));
    dom.modalLayer.classList.add("active");
    txt(dom.modalLayer.querySelector("#confirmMessage"), msg);
  }

  function closeModal() {
    dom.modalLayer?.classList.remove("active");
    if (dom.modalLayer) dom.modalLayer.innerHTML = "";
    state.confirmFn = null;
  }

  function modalMsg(form, msg, tone) {
    setMsg(form.querySelector("[data-modal-message]"), msg, tone);
  }

  async function submitCronAdd(form) {
    const fd = new FormData(form);
    const schedule = (fd.get("schedule") || "").toString().trim();
    const cmd = (fd.get("command") || "").toString().trim();
    const args = (fd.get("arguments") || "").toString().trim();
    const reason = (fd.get("reason") || "").toString().trim();
    if (!validateCronSchedule(schedule)) return modalMsg(form, "Cron式が不正、または毎分実行は禁止です。", "error");
    if (!CRON_ALLOW.has(cmd)) return modalMsg(form, "allowlist外コマンドは使用できません。", "error");
    if (!validateCronArguments(args)) return modalMsg(form, "引数に禁止文字が含まれています。", "error");
    if (reason.length < 10) return modalMsg(form, "理由は10文字以上で入力してください。", "error");
    const payload = { schedule, command: cmd, arguments: args, comment: (fd.get("comment") || "").toString().trim(), reason };
    if (state.session && state.api) {
      try {
        const live = await state.api.tryLive(() => state.api.api.cron.create(payload), { op: "cron.create" });
        if (live.live && live.data) {
          const res = normalizeCronApprovalPending(live.data);
          const rec = createApproval({ type: "cron_add", reason, payload, forceId: res.request_id || undefined });
          addApprovalRows(rec); closeModal(); syncApprovalUI(); selectApproval(rec.id); void refreshApprovalsFromApi(); toast(res.message || `Cron追加申請を作成しました: ${rec.id}`, "success");
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") return modalMsg(form, explainApiError(err).message, "error");
      }
    }
    const rec = createApproval({ type: "cron_add", reason, payload });
    addApprovalRows(rec); closeModal(); syncApprovalUI(); selectApproval(rec.id); toast(`Cron追加申請を作成しました: ${rec.id}`, "success");
  }

  async function submitUserAdd(form) {
    const fd = new FormData(form);
    const u = (fd.get("username") || "").toString().trim();
    const sh = (fd.get("shell") || "").toString().trim();
    const pw = (fd.get("password") || "").toString();
    const cf = (fd.get("confirm") || "").toString();
    const groups = (fd.get("groups") || "").toString().split(",").map((s) => s.trim()).filter(Boolean);
    const home = (fd.get("home") || "").toString().trim();
    const reason = (fd.get("reason") || "").toString().trim();
    if (!validateUsername(u)) return modalMsg(form, "username形式が不正です。", "error");
    if (!ALLOWED_SHELLS.has(sh)) return modalMsg(form, "許可されていない shell です。", "error");
    if (pw !== cf) return modalMsg(form, "パスワード確認が一致しません。", "error");
    if (!validateStrongPassword(pw, u)) return modalMsg(form, "パスワードポリシーを満たしていません。", "error");
    if (groups.some((g) => !validateUsername(g))) return modalMsg(form, "group 名形式が不正です。", "error");
    if (groups.some((g) => FORBIDDEN_GROUPS.has(g))) return modalMsg(form, "禁止グループが含まれます。", "error");
    if (reason.length < 10) return modalMsg(form, "理由は10文字以上で入力してください。", "error");
    if (state.session && state.api) {
      try {
        const live = await state.api.tryLive(
          () => state.api.api.users.create({ username: u, password: pw, groups, home_dir: home, shell: sh, reason }),
          { op: "users.create" }
        );
        if (live.live && live.data) {
          const d = live.data?.data ?? live.data;
          const approvalId = d.request_id || d.approval_id || null;
          const rec = createApproval({ type: "user_add", reason, payload: { username: u, shell: sh, groups, home }, forceId: approvalId || undefined });
          addApprovalRows(rec); closeModal(); syncApprovalUI(); selectApproval(rec.id); void refreshApprovalsFromApi(); toast(d.message || `ユーザー追加申請を作成しました: ${rec.id}`, "success");
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") {
          return modalMsg(form, explainApiError(err).message, "error");
        }
      }
    }
    const rec = createApproval({ type: "user_add", reason, payload: { username: u, shell: sh, groups, home } });
    addApprovalRows(rec); closeModal(); syncApprovalUI(); selectApproval(rec.id); toast(`ユーザー追加申請を作成しました: ${rec.id}`, "success");
  }

  async function submitServiceStop(form) {
    const fd = new FormData(form);
    const service = (fd.get("service") || "").toString().trim();
    const reason = (fd.get("reason") || "").toString().trim();
    if (!service) return modalMsg(form, "service 名を確認してください。", "error");
    if (reason.length < 10) return modalMsg(form, "理由は10文字以上で入力してください。", "error");
    if (state.session && state.api) {
      try {
        const live = await state.api.tryLive(
          () => state.api.api.approvals.create({ request_type: "service_stop", payload: { service }, reason }),
          { op: "approval.request.service_stop" }
        );
        if (live.live && live.data) {
          const d = live.data?.data ?? live.data;
          const rec = createApproval({ type: "service_stop", reason, payload: { service }, forceId: d.request_id || undefined });
          addApprovalRows(rec); closeModal(); syncApprovalUI(); selectApproval(rec.id); void refreshApprovalsFromApi(); toast(d.message || `サービス停止申請を作成しました: ${rec.id}`, "success");
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") return modalMsg(form, explainApiError(err).message, "error");
      }
    }
    const rec = createApproval({ type: "service_stop", reason, payload: { service } });
    addApprovalRows(rec); closeModal(); syncApprovalUI(); selectApproval(rec.id); toast(`サービス停止申請を作成しました: ${rec.id}`, "success");
  }

  async function submitApprovalAction(form) {
    const fd = new FormData(form);
    const id = (fd.get("approvalId") || "").toString();
    const op = (fd.get("op") || "").toString();
    const msg = (fd.get("message") || "").toString().trim();
    const rec = state.approvals[id];
    if (!rec) return modalMsg(form, "承認IDが見つかりません。", "error");
    if (!["approve", "reject", "cancel"].includes(op)) return modalMsg(form, "不正な操作です。", "error");
    if (op === "reject" && msg.length < 3) return modalMsg(form, "拒否理由を入力してください。", "error");
    const actor = state.session?.username || "operator";
    if ((op === "approve" || op === "reject") && actor === rec.requester) return modalMsg(form, "自己承認は禁止です。", "error");
    if (state.session && state.api) {
      try {
        const fn = op === "approve" ? state.api.api.approvals.approve
          : op === "reject" ? state.api.api.approvals.reject
          : state.api.api.approvals.cancel;
        const payload = op === "approve" ? { comment: msg || undefined } : { reason: msg || undefined };
        const live = await state.api.tryLive(() => fn(id, payload), { op: `approval.${op}` });
        if (live.live && live.data) {
          const mapped = normalizeApprovalActionResponse(live.data, op === "approve" ? "approved" : op === "reject" ? "rejected" : "cancelled");
          rec.status = mapped.next_status;
          rec.timeline.push({ tone: op === "approve" ? "success" : "warning", title: `${op} / ${actor} (${roleLabel(state.session?.role)})${msg ? ` - ${msg}` : ""}`, time: nowLong() });
          if (["approved", "rejected", "executed", "expired", "cancelled"].includes(rec.status)) addHistoryRow(rec, actor);
          syncApprovalUI();
          renderApprovalDetail(rec);
          closeModal();
          void refreshApprovalsFromApi();
          toast(mapped.message || `承認操作を実行しました: ${id} → ${rec.status}`, op === "approve" ? "success" : "warning");
          return;
        }
      } catch (err) {
        if (state.api.settings.mode === "live") return modalMsg(form, explainApiError(err).message, "error");
      }
    }
    rec.status = op === "approve" ? "approved" : op === "reject" ? "rejected" : "cancelled";
    rec.timeline.push({ tone: op === "approve" ? "success" : "warning", title: `${op} / ${actor} (${roleLabel(state.session?.role)})${msg ? ` - ${msg}` : ""}`, time: nowLong() });
    if (["approved", "rejected", "executed", "expired", "cancelled"].includes(rec.status)) addHistoryRow(rec, actor);
    syncApprovalUI();
    renderApprovalDetail(rec);
    closeModal();
    toast(`承認操作を実行しました: ${id} → ${rec.status}`, op === "approve" ? "success" : "warning");
  }

  function strongPw(pw, username) { return validateStrongPassword(pw, username); }

  function openDraftReset() { applyDraftDefaults(); renderDraftPreview(); }

  function hash(s) {
    let h = 0;
    for (let i = 0; i < s.length; i += 1) h = ((h << 5) - h) + s.charCodeAt(i) | 0;
    return h;
  }

})();
