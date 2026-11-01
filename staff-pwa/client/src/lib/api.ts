/**
 * Clinical Warmth integration layer: all protected data stays on the approved
 * FastAPI API path and is scoped by the signed-in user's Bearer token.
 */
import { staffApiFeatures } from "./features";
import {
  isCredentialGenerationCurrent,
  isSameCredentialSnapshot,
  type CredentialSnapshot,
} from "./sessionGuards";

export const API_BASE = (import.meta.env.VITE_API_BASE || "").trim().replace(/\/+$/, "");

/** A browser-exposed build setting, deliberately limited to one HTTPS origin. */
export function isConfiguredApiOrigin(value = API_BASE) {
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      url.pathname === "/" &&
      !url.search &&
      !url.hash &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}

function apiUrl(path: string) {
  if (!API_BASE) {
    throw new Error("尚未設定已批准的後端網址；請設定 VITE_API_BASE 後再登入。");
  }
  if (!isConfiguredApiOrigin()) {
    throw new Error("VITE_API_BASE 必須是已批准的 HTTPS 後端 origin（不可包含路徑、查詢或帳密）。");
  }
  return `${API_BASE}${path}`;
}

function unavailableFeatureError(message: string) {
  return new Error(message);
}

const ACCESS_KEY = "emma_token";
const REFRESH_KEY = "emma_refresh_token";
const EXPIRES_KEY = "emma_expires_at";
const USER_KEY = "emma_user";

let authToken: string | null = localStorage.getItem(ACCESS_KEY);
let credentialGeneration = 0;

interface LoginAttempt {
  generation: number;
}

// A login response is deliberately not a usable browser session until its
// Bearer token has hydrated a tenant-scoped identity via /auth/me.
let pendingLogin: LoginAttempt | null = null;

interface RefreshInFlight {
  snapshot: CredentialSnapshot;
  promise: Promise<SessionOut>;
}

let refreshInFlight: RefreshInFlight | null = null;

export interface SessionUser {
  id: string;
  email?: string | null;
  role?: string | null;
  position?: string | null;
  unit?: string | null;
  floor?: string | null;
  monthly_hours_target?: number;
  monthly_hours_worked?: number;
  certifications?: string[];
  staff_id?: string | null;
  facility_id?: string | null;
  facility_name?: string | null;
  name?: string;
}

export interface SessionOut {
  access_token: string;
  refresh_token?: string | null;
  token_type?: string;
  expires_at?: number | null;
  user_id: string;
  email?: string | null;
  role?: string | null;
  facility_id?: string | null;
  facility_name?: string | null;
  user?: SessionUser | null;
}

export type StaffUser = SessionUser;

/** The stable tenant-scoped identity returned by GET /auth/me. */
export interface AuthProfile {
  id: string;
  auth_user_id?: string | null;
  facility_id?: string | null;
  org_id?: string | null;
  email?: string | null;
  role: string;
  staff_id?: string | null;
  facility?: {
    code?: string | null;
    name?: string | null;
  } | null;
  organisation?: {
    id?: string | null;
    code?: string | null;
    name?: string | null;
  } | null;
}

export interface StaffProfile {
  id: string;
  name: string;
  name_en?: string | null;
  rank: string;
  employment_type?: string | null;
  unit_name?: string | null;
  gender?: string | null;
  is_mentor?: boolean;
  is_audited_for_medication?: boolean;
  certificates: Array<{
    cert_type: string;
    expiry_date?: string | null;
    days_left?: number | null;
  }>;
  hours?: {
    period_start?: string;
    period_end?: string;
    scheduled_hours?: number;
    contracted_hours?: number;
    pct?: number;
  };
  attendance_month?: Record<string, unknown>;
}

export interface StaffTask {
  id: string;
  task_label: string;
  scheduled_time?: string | null;
  priority?: number | null;
  status: "pending" | "done" | "skipped";
  completed_at?: string | null;
  shift_type?: string | null;
}

export interface RosterDay {
  date: string;
  shift_type?: string | null;
  is_working: boolean;
  start_time?: string | null;
  end_time?: string | null;
  unit_name?: string | null;
  tasks: string[];
}

export interface RosterResponse {
  staff_id: string;
  name: string;
  name_en?: string | null;
  rank: string;
  unit_name?: string | null;
  start: string;
  end: string;
  days: RosterDay[];
}

export interface LeaveRequestPayload {
  leave_type: string;
  date_start: string;
  date_end: string;
  reason?: string | null;
  remark?: string | null;
  requested_shift_type?: string | null;
  document_url?: string | null;
}

export interface DutyRequestWindow {
  enabled: boolean;
  opens_at: string | null;
  closes_at: string | null;
  target_start: string | null;
  target_end: string | null;
  status: "open" | "closed" | "scheduled" | "expired";
}

export interface ShiftDefinitionOption {
  shift_type: string;
  label?: string | null;
  is_working?: boolean;
}

export interface LeaveRequest {
  id: string;
  leave_type?: string;
  request_type?: string;
  date_start: string;
  date_end: string;
  status: string;
  reason?: string | null;
  remark?: string | null;
  requested_shift_type?: string | null;
  document_url?: string | null;
  created_at?: string | null;
  submitted_at?: string | null;
  decided_at?: string | null;
  reviewed_at?: string | null;
  decision_reason?: string | null;
  reviewer_name?: string | null;
}

export interface StaffNotification {
  id: string;
  event_type: string;
  title: string;
  body: string;
  status: string;
  related_type?: string | null;
  related_id?: string | null;
  created_at: string;
  read_at?: string | null;
}

export interface MessageContact {
  id: string;
  display_name: string;
  role: string;
  staff_id?: string | null;
}

export interface DirectMessage {
  id: string;
  sender_profile_id: string;
  recipient_profile_id: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

export type ReplacementOfferStatus =
  | "pending"
  | "accepted"
  | "declined"
  | "approved"
  | "withdrawn"
  | "superseded";

export interface ReplacementOffer {
  id: string;
  incident_id: string;
  shift_id: string;
  offered_staff_id: string;
  score?: number | null;
  rank_required?: string | null;
  note?: string | null;
  status: ReplacementOfferStatus;
  responded_at?: string | null;
  created_at: string;
}

export interface Certificate {
  id: string;
  name: string;
  cert_number: string;
  issue_date: string;
  expiry_date: string;
  status: "valid" | "expiring_soon" | "expired";
  file_url?: string;
}

export interface CertificatePayload {
  name: string;
  cert_number: string;
  issue_date: string;
  expiry_date: string;
  file_url?: string;
}

function normaliseUser(session: SessionOut): StaffUser {
  return (
    session.user || {
      id: session.user_id,
      email: session.email,
      role: session.role,
      facility_id: session.facility_id,
      facility_name: session.facility_name,
    }
  );
}

function mergeAuthenticatedProfile(profile: AuthProfile, session: SessionOut): StaffUser {
  const sessionUser = normaliseUser(session);
  return {
    ...sessionUser,
    // Retain the login response's user id because the public contract does not
    // state whether SessionUser.id is an auth-user id or a profile id. The
    // profile response augments it with the server-validated tenant attributes.
    email: profile.email ?? sessionUser.email,
    role: profile.role,
    staff_id: profile.staff_id ?? sessionUser.staff_id,
    facility_id: profile.facility_id ?? sessionUser.facility_id,
    facility_name: profile.facility?.name ?? sessionUser.facility_name,
  };
}

function replaceNullableSessionValue(key: string, value: string | number | null | undefined) {
  // SessionOut permits these fields to be omitted. Remove first so a new
  // account can never inherit a previous account's refresh capability/expiry.
  localStorage.removeItem(key);
  if (value !== null && value !== undefined) localStorage.setItem(key, String(value));
}

function persistSession(session: SessionOut) {
  authToken = session.access_token;
  localStorage.setItem(ACCESS_KEY, session.access_token);
  replaceNullableSessionValue(REFRESH_KEY, session.refresh_token);
  replaceNullableSessionValue(EXPIRES_KEY, session.expires_at);
  localStorage.setItem(USER_KEY, JSON.stringify(normaliseUser(session)));
}

function advanceCredentialGeneration() {
  messageAttempts.clear();
  credentialGeneration += 1;
  return credentialGeneration;
}

function removePersistedSession() {
  authToken = null;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(EXPIRES_KEY);
  localStorage.removeItem(USER_KEY);
}

function beginLoginAttempt(): LoginAttempt {
  // Revoke every prior account capability before issuing the next network
  // request. In-flight refreshes still complete, but their generation/snapshot
  // check prevents them from restoring these removed credentials.
  const attempt = { generation: advanceCredentialGeneration() };
  removePersistedSession();
  pendingLogin = attempt;
  return attempt;
}

function isLoginAttemptCurrent(attempt: LoginAttempt) {
  return pendingLogin === attempt && credentialGeneration === attempt.generation;
}

function assertLoginAttemptCurrent(attempt: LoginAttempt) {
  if (!isLoginAttemptCurrent(attempt)) throw credentialChangedError();
}

function failLoginAttempt(attempt: LoginAttempt) {
  // A superseded attempt must never clear a newer successful login.
  if (!isLoginAttemptCurrent(attempt)) return;
  pendingLogin = null;
  advanceCredentialGeneration();
  removePersistedSession();
}

function authPendingError() {
  return new Error("登入程序進行中，請等待身分驗證完成");
}

function assertNoLoginPending() {
  if (pendingLogin) throw authPendingError();
}

function captureCredentials(): CredentialSnapshot {
  return {
    generation: credentialGeneration,
    accessToken: authToken,
    refreshToken: localStorage.getItem(REFRESH_KEY),
  };
}

function isSnapshotCurrent(snapshot: CredentialSnapshot) {
  return (
    isCredentialGenerationCurrent(snapshot, credentialGeneration) &&
    authToken === snapshot.accessToken &&
    localStorage.getItem(REFRESH_KEY) === snapshot.refreshToken
  );
}

function credentialChangedError() {
  return new Error("登入狀態已變更，請重新操作");
}

function assertRequestCurrent(requestIdentity: CredentialSnapshot) {
  // A successful refresh changes the tokens within this generation. The
  // generation, rather than token string equality, therefore binds a request
  // to its signed-in session while allowing its own refresh to complete.
  if (!isCredentialGenerationCurrent(requestIdentity, credentialGeneration)) {
    throw credentialChangedError();
  }
}

export function setToken(token: string) {
  advanceCredentialGeneration();
  pendingLogin = null;
  authToken = token;
  localStorage.setItem(ACCESS_KEY, token);
}

export function getToken() {
  return authToken;
}

export function getStoredUser(): StaffUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StaffUser;
  } catch {
    return null;
  }
}

export function clearToken() {
  advanceCredentialGeneration();
  pendingLogin = null;
  removePersistedSession();
}

function readableError(payload: unknown, fallback: string) {
  if (typeof payload === "string") return payload;
  if (!payload || typeof payload !== "object") return fallback;
  const data = payload as Record<string, unknown>;
  if (typeof data.message === "string") return data.message;
  if (typeof data.detail === "string") return data.detail;
  if (data.detail && typeof data.detail === "object") {
    const detail = data.detail as Record<string, unknown>;
    if (typeof detail.message === "string") return detail.message;
    if (typeof detail.code === "string") return detail.code;
  }
  return fallback;
}

async function refreshSession(): Promise<SessionOut> {
  const snapshot = captureCredentials();
  if (!snapshot.refreshToken) throw new Error("登入已過期，請重新登入");

  if (refreshInFlight && isSameCredentialSnapshot(refreshInFlight.snapshot, snapshot)) {
    return refreshInFlight.promise;
  }

  // Begin asynchronously so the slot is installed before a synchronous fetch
  // failure can settle it. A slot only deduplicates callers with the exact
  // generation/access/refresh-token snapshot that started it.
  const slot = {} as RefreshInFlight;
  const promise = Promise.resolve()
    .then(async () => {
      const res = await fetch(apiUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: snapshot.refreshToken }),
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        throw new Error(readableError(payload, "登入已過期，請重新登入"));
      }
      return res.json() as Promise<SessionOut>;
    })
    .then((session) => {
      // A logout, setToken, or successful newer login must win over an older
      // refresh response. Do not restore or overwrite that newer session.
      if (!isSnapshotCurrent(snapshot)) throw credentialChangedError();
      persistSession(session);
      return session;
    })
    .catch((error) => {
      // Only the still-current credential set may expire the UI. A late
      // failure from an earlier session must never clear a newer login.
      if (isSnapshotCurrent(snapshot)) {
        clearToken();
        window.dispatchEvent(new Event("emma-auth-expired"));
      }
      throw error;
    })
    .finally(() => {
      // An old completion cannot erase a newer generation's refresh slot.
      if (refreshInFlight === slot) refreshInFlight = null;
    });

  slot.snapshot = snapshot;
  slot.promise = promise;
  refreshInFlight = slot;
  return promise;
}

async function ensureFreshToken() {
  const expiresAt = Number(localStorage.getItem(EXPIRES_KEY) || 0);
  if (authToken && expiresAt && expiresAt * 1000 <= Date.now() + 120_000) {
    await refreshSession();
  }
}

async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  // Do not turn an ordinary request into an unauthenticated request, or attach
  // a just-issued but not yet identity-validated token, during a sign-in.
  assertNoLoginPending();
  const requestIdentity = captureCredentials();
  return requestForIdentity<T>(path, options, retry, requestIdentity);
}

async function requestForIdentity<T>(
  path: string,
  options: RequestInit,
  retry: boolean,
  requestIdentity: CredentialSnapshot,
): Promise<T> {
  // Bind this call before refreshing: a new login/logout invalidates all work
  // captured under the old generation, including mutation bodies.
  assertNoLoginPending();
  assertRequestCurrent(requestIdentity);
  await ensureFreshToken();
  assertNoLoginPending();
  assertRequestCurrent(requestIdentity);

  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) headers.set("Content-Type", "application/json");
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);

  let res: Response;
  try {
    res = await fetch(apiUrl(path), { ...options, headers });
  } catch {
    throw new Error("未能連接院舍系統；請確認PWA網址已加入後端CORS白名單");
  }
  // Do not inspect, retry, or deliver a response that arrived after another
  // user established a new credential generation.
  assertRequestCurrent(requestIdentity);
  if (res.status === 401 && retry && localStorage.getItem(REFRESH_KEY)) {
    await refreshSession();
    // Keep the original identity on retry; recapturing here would replay an
    // old request body under a newly signed-in user's Authorization header.
    assertRequestCurrent(requestIdentity);
    return requestForIdentity<T>(path, options, false, requestIdentity);
  }
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    assertRequestCurrent(requestIdentity);
    throw new Error(readableError(payload, `API錯誤 (${res.status})`));
  }
  if (res.status === 204) return undefined as T;
  const payload = (await res.json()) as T;
  assertRequestCurrent(requestIdentity);
  return payload;
}

function requireLoginSession(payload: unknown): SessionOut {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("登入回應無效");
  }
  const session = payload as SessionOut;
  if (
    typeof session.access_token !== "string" ||
    !session.access_token.trim() ||
    typeof session.user_id !== "string" ||
    !session.user_id.trim()
  ) {
    throw new Error("登入回應無效");
  }
  return session;
}

function requireAuthProfile(payload: unknown): AuthProfile {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("未能驗證登入身分");
  }
  const profile = payload as AuthProfile;
  if (
    typeof profile.id !== "string" ||
    !profile.id.trim() ||
    typeof profile.role !== "string" ||
    !profile.role.trim()
  ) {
    throw new Error("未能驗證登入身分");
  }
  return profile;
}

async function getLoginIdentity(attempt: LoginAttempt, accessToken: string): Promise<AuthProfile> {
  // A successful /auth/login has just supplied this access token. Avoid the
  // general request helper's optional expiry preflight here: an omitted or
  // clock-skewed expires_at must not cause a prior account's stale refresh
  // credential to be consulted before this identity is hydrated. The exact
  // candidate token is held only in this call, never in shared session state.
  assertLoginAttemptCurrent(attempt);
  const headers = new Headers({ Accept: "application/json" });
  headers.set("Authorization", `Bearer ${accessToken}`);

  let res: Response;
  try {
    res = await fetch(apiUrl("/auth/me"), { headers });
  } catch {
    throw new Error("未能驗證登入身分；請確認PWA網址已加入後端CORS白名單");
  }
  assertLoginAttemptCurrent(attempt);
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    assertLoginAttemptCurrent(attempt);
    throw new Error(readableError(payload, "未能驗證登入身分"));
  }
  const payload = await res.json();
  assertLoginAttemptCurrent(attempt);
  return requireAuthProfile(payload);
}

export async function login(email: string, password: string) {
  // Invalidate existing work and remove any previous identity before this new
  // sign-in makes a network call. A later login owns a distinct attempt object
  // as well as a distinct generation, so an older failure cannot clear it.
  const attempt = beginLoginAttempt();
  try {
    const res = await fetch(apiUrl("/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    assertLoginAttemptCurrent(attempt);
    if (!res.ok) {
      const payload = await res.json().catch(() => null);
      throw new Error(readableError(payload, "登入失敗"));
    }
    const session = requireLoginSession(await res.json());
    assertLoginAttemptCurrent(attempt);
    // /auth/login establishes credentials; /auth/me is the documented,
    // Bearer-protected source of tenant-scoped role, staff, and facility data.
    // Do not infer those fields in the browser or query a manager endpoint.
    const profile = await getLoginIdentity(attempt, session.access_token);
    const user = mergeAuthenticatedProfile(profile, session);
    assertLoginAttemptCurrent(attempt);
    persistSession({ ...session, user });
    pendingLogin = null;
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    return { ...session, user };
  } catch (error) {
    // No failed or malformed login response may reactivate the previous
    // browser session. Only this still-current attempt is allowed to clear;
    // an older attempt losing a race must leave the newer login intact.
    failLoginAttempt(attempt);
    throw error;
  }
}

export async function getMyProfile() {
  return request<StaffProfile>("/me/profile");
}

export async function getMyTasks(date?: string) {
  const q = date ? `?date=${encodeURIComponent(date)}` : "";
  return request<StaffTask[]>(`/me/tasks${q}`);
}

export async function updateMyTask(taskId: string, status: "pending" | "done" | "skipped") {
  return request<StaffTask>(`/me/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function completeTask(taskId: string) {
  return updateMyTask(taskId, "done");
}

export async function getMyRoster(startDate: string, endDate: string) {
  const query = new URLSearchParams({ start: startDate, end: endDate });
  return request<RosterResponse>(`/me/roster?${query.toString()}`);
}

export async function getMyLeaveRequests() {
  return request<LeaveRequest[]>("/me/leave-requests");
}

export async function getDutyRequestWindow(): Promise<DutyRequestWindow> {
  requireCandidateFeature("dutyRequestWindow");
  const payload = await request<unknown>("/me/request-window?kind=duty");
  const result = objectRow(payload);
  const status = result.status;
  if (!["open", "closed", "scheduled", "expired", "unavailable"].includes(String(status)) ||
      typeof result.available !== "boolean") throw new Error("申請期回應無效");
  if (!result.window) {
    if (result.available) throw new Error("申請期回應無效");
    return { enabled: false, status: "closed", opens_at: null, closes_at: null, target_start: null, target_end: null };
  }
  const window = objectRow(result.window);
  const start = calendarDate(window.target_start);
  const exclusive = calendarDate(window.target_end_exclusive);
  if (exclusive <= start || typeof window.opens_at !== "string" || typeof window.closes_at !== "string")
    throw new Error("申請期回應無效");
  // Legacy PWA date controls compare inclusive ends; UTC calendar arithmetic
  // avoids browser timezone/DST changing the final allowed date.
  const last = new Date(`${exclusive}T00:00:00Z`);
  last.setUTCDate(last.getUTCDate() - 1);
  return { enabled: result.available && status === "open", status: status === "unavailable" ? "closed" : status as DutyRequestWindow["status"],
    opens_at: window.opens_at, closes_at: window.closes_at, target_start: start, target_end: last.toISOString().slice(0, 10) };
}

export async function getShiftDefinitionOptions() {
  return request<ShiftDefinitionOption[]>("/shift-definitions");
}

export async function submitLeaveRequest(data: LeaveRequestPayload) {
  const identity = captureCredentials();
  const start = calendarDate(data.date_start);
  const end = calendarDate(data.date_end);
  if (end < start) throw new Error("結束日期不可早於開始日期");
  if (["do", "duty_request", "shift_swap"].includes(data.leave_type.toLowerCase())) {
    const window = await getDutyRequestWindow();
    if (!window.enabled || !window.target_start || !window.target_end || start < window.target_start || end > window.target_end)
      throw new Error("此指定更期／休息日申請期尚未開放或日期不符");
  }
  assertRequestCurrent(identity);
  const row = objectRow(await requestForIdentity<unknown>("/leave-requests", {
    method: "POST", body: JSON.stringify(data),
  }, true, identity));
  if (typeof row.id !== "string" || !row.id || row.status !== "pending" || row.date_start !== start || row.date_end !== end)
    throw new Error("申請回應無效；請核實紀錄後再試");
  return row as unknown as LeaveRequest;
}

export async function withdrawLeaveRequest(id: string) {
  return request<LeaveRequest>(`/leave-requests/${id}/withdraw`, { method: "POST" });
}

export async function getMyNotifications(unreadOnly = false, signal?: AbortSignal) {
  return request<StaffNotification[]>(`/me/notifications${unreadOnly ? "?unread_only=true" : ""}`, { signal });
}

export async function markNotificationRead(id: string) {
  return request<StaffNotification>(`/me/notifications/${id}/read`, { method: "PATCH" });
}

/** Candidate contract only: release gates remain false until hosted acceptance. */
function requireCandidateFeature(feature: keyof typeof staffApiFeatures) {
  if (!staffApiFeatures[feature].available) throw unavailableFeatureError(staffApiFeatures[feature].unavailableMessage);
}
function objectRow(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("後端回應無效");
  return value as Record<string, unknown>;
}
function calendarDate(value: unknown): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value)
    throw new Error("申請日期無效");
  return value;
}
function messageRow(value: unknown): DirectMessage {
  const row = objectRow(value);
  for (const key of ["id", "sender_profile_id", "recipient_profile_id", "body", "created_at"]) {
    if (typeof row[key] !== "string" || !row[key]) throw new Error("訊息回應無效");
  }
  if (row.read_at !== null && typeof row.read_at !== "string") throw new Error("訊息回應無效");
  return row as unknown as DirectMessage;
}
const messageAttempts = new Map<string, { body: string; key: string }>();
export async function listMessageContacts(): Promise<MessageContact[]> {
  requireCandidateFeature("directMessages");
  const rows = await request<unknown>("/messages/contacts");
  if (!Array.isArray(rows)) throw new Error("聯絡人回應無效");
  return rows.map(value => {
    const row = objectRow(value);
    if (["id", "display_name", "role"].some(key => typeof row[key] !== "string" || !row[key])) throw new Error("聯絡人回應無效");
    return row as unknown as MessageContact;
  });
}
export async function listDirectMessages(options: { peer?: string; before?: string; limit?: number } = {}): Promise<DirectMessage[]> {
  requireCandidateFeature("directMessages");
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(options)) if (value !== undefined) query.set(key, String(value));
  const rows = await request<unknown>(`/messages${query.size ? `?${query}` : ""}`);
  if (!Array.isArray(rows)) throw new Error("訊息回應無效");
  return rows.map(messageRow);
}
export async function sendDirectMessage(recipientProfileId: string, body: string): Promise<DirectMessage> {
  requireCandidateFeature("directMessages");
  if (!body.trim() || Array.from(body).length > 4000) throw new Error("訊息必須為 1–4000 字");
  // One unresolved draft per real recipient. A failed send keeps its exact key;
  // edits replace it. Session changes clear all attempts, including tenant switches.
  let attempt = messageAttempts.get(recipientProfileId);
  if (!attempt || attempt.body !== body) {
    attempt = { body, key: crypto.randomUUID() };
    messageAttempts.set(recipientProfileId, attempt);
  }
  const row = messageRow(await request<unknown>("/messages", { method: "POST", body: JSON.stringify({
    recipient_profile_id: recipientProfileId, body, client_message_id: attempt.key,
  }) }));
  if (row.recipient_profile_id !== recipientProfileId || row.body !== body) throw new Error("訊息回應不符");
  if (messageAttempts.get(recipientProfileId) === attempt) messageAttempts.delete(recipientProfileId);
  return row;
}
export async function markDirectMessageRead(id: string): Promise<DirectMessage> {
  requireCandidateFeature("directMessages");
  const row = messageRow(await request<unknown>(`/messages/${encodeURIComponent(id)}/read`, { method: "PATCH" }));
  if (row.id !== id || !row.read_at) throw new Error("已讀回應無效");
  return row;
}

export async function getReplacementOffers(status?: ReplacementOfferStatus, signal?: AbortSignal) {
  return request<ReplacementOffer[]>(`/me/replacement-offers${status ? `?status=${status}` : ""}`, { signal });
}

export async function respondReplacementOffer(id: string, accept: boolean, note?: string) {
  return request<ReplacementOffer>(`/me/replacement-offers/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ accept, ...(note ? { note } : {}) }),
  });
}

export async function registerPushSubscription(token: string, userAgent = navigator.userAgent) {
  return request<{ id: string }>("/me/push-subscriptions", {
    method: "POST",
    body: JSON.stringify({ token, platform: "web", user_agent: userAgent }),
  });
}

// Certificate Vault is deferred from the immediate MVP. These helpers remain so
// the existing secondary route does not break if the backend later exposes it.
export async function getMyCertificates() {
  return request<Certificate[]>("/me/certificates");
}

export async function uploadCertificate(data: CertificatePayload) {
  return request<Certificate>("/me/certificates", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
