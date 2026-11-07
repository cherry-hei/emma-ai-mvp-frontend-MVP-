import { beforeEach, afterEach, expect, it, vi } from "vitest";

vi.mock("../client/src/lib/features", () => ({ staffApiFeatures: {
  directMessages: { available: true, unavailableMessage: "disabled" },
  dutyRequestWindow: { available: true, unavailableMessage: "disabled" },
} }));
let api: typeof import("../client/src/lib/api");
let fetchMock: ReturnType<typeof vi.fn>;
const reply = (value: unknown) => new Response(JSON.stringify(value));
const row = { id: "message", sender_profile_id: "sender", recipient_profile_id: "peer", body: "draft", created_at: "2026-11-01T00:00:00Z", read_at: null };
beforeEach(async () => {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE", "https://api.example.test");
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
  fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  api = await import("../client/src/lib/api"); api.setToken("fixture-token");
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
it("maps exclusive leap-month boundary to inclusive date using backend status", async () => {
  fetchMock.mockResolvedValue(reply({ available: true, status: "open", window: { target_start: "2028-02-01", target_end_exclusive: "2028-03-01", opens_at: "server-open", closes_at: "server-close" } }));
  expect(await api.getDutyRequestWindow()).toMatchObject({ enabled: true, target_end: "2028-02-29" });
  expect(fetchMock.mock.calls[0][0]).toBe("https://api.example.test/me/request-window?kind=duty");
});
it("keeps closed windows inactive and missing windows closed", async () => {
  fetchMock.mockResolvedValue(reply({ available: false, status: "closed", window: null }));
  expect(await api.getDutyRequestWindow()).toMatchObject({ enabled: false, status: "closed" });
});
it("rejects malformed windows", async () => {
  fetchMock.mockResolvedValue(reply({ available: true, status: "open", window: {} }));
  await expect(api.getDutyRequestWindow()).rejects.toThrow();
});
it("preserves exact per-recipient retry key and content after failure", async () => {
  fetchMock.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(reply(row));
  await expect(api.sendDirectMessage("peer", "draft")).rejects.toThrow();
  expect(await api.sendDirectMessage("peer", "draft")).toEqual(row);
  const bodies = fetchMock.mock.calls.map(call => JSON.parse(call[1].body));
  expect(bodies[0]).toEqual(bodies[1]);
  expect(Object.keys(bodies[0]).sort()).toEqual(["body", "client_message_id", "recipient_profile_id"]);
});
it("rotates keys for edited content, other recipients and new sessions", async () => {
  fetchMock.mockRejectedValue(new Error("offline"));
  for (const [peer, body] of [["peer", "draft"], ["peer", "edited"], ["other", "edited"]]) await expect(api.sendDirectMessage(peer, body)).rejects.toThrow();
  api.setToken("new-session");
  await expect(api.sendDirectMessage("peer", "edited")).rejects.toThrow();
  const keys = fetchMock.mock.calls.map(call => JSON.parse(call[1].body).client_message_id);
  expect(new Set(keys).size).toBe(4);
});
it.each([null, {}, [], { ok: true }])("rejects non-durable send response %j", async payload => {
  fetchMock.mockResolvedValue(reply(payload));
  await expect(api.sendDirectMessage("peer", "draft")).rejects.toThrow();
});
it("rejects empty/non-JSON and error responses", async () => {
  for (const response of [new Response(null, { status: 204 }), new Response("bad"), new Response('{}', { status: 403 })]) {
    fetchMock.mockResolvedValueOnce(response);
    await expect(api.sendDirectMessage("peer", "draft")).rejects.toThrow();
  }
});
it("uses authenticated contacts, query parameters and persisted read receipt", async () => {
  fetchMock.mockResolvedValueOnce(reply([{ id: "profile-id", display_name: "Synthetic", role: "staff" }])).mockResolvedValueOnce(reply([row])).mockResolvedValueOnce(reply({ ...row, read_at: "server-time" }));
  expect((await api.listMessageContacts())[0].id).toBe("profile-id");
  expect(await api.listDirectMessages({ peer: "peer", limit: 20 })).toEqual([row]);
  expect(fetchMock.mock.calls[1][0]).toContain("peer=peer&limit=20");
  expect((await api.markDirectMessageRead("message")).read_at).toBe("server-time");
});
it("drops old session responses", async () => {
  let resolve!: (value: Response) => void;
  fetchMock.mockImplementation(() => new Promise<Response>(r => { resolve = r; }));
  const pending = api.listMessageContacts();
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
  api.clearToken(); resolve(reply([]));
  await expect(pending).rejects.toThrow("登入狀態已變更");
});
it("rejects out-of-window ordinary requests without POST", async () => {
  fetchMock.mockResolvedValue(reply({ available: false, status: "closed", window: null }));
  await expect(api.submitLeaveRequest({ leave_type: "DO", date_start: "2026-11-01", date_end: "2026-11-01" })).rejects.toThrow();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
it("emergency SL bypasses ordinary window and requires durable pending response", async () => {
  const data = { leave_type: "SL", date_start: "2026-11-01", date_end: "2026-11-01" };
  fetchMock.mockResolvedValueOnce(reply({ ...data, id: "request", status: "pending" })).mockResolvedValueOnce(reply({ ok: true }));
  expect((await api.submitLeaveRequest(data)).status).toBe("pending");
  expect(fetchMock.mock.calls[0][0]).toBe("https://api.example.test/leave-requests");
  await expect(api.submitLeaveRequest(data)).rejects.toThrow();
});
it("does not replay a window-checked request into a new session", async () => {
  let resolve!: (value: Response) => void;
  fetchMock.mockImplementation(() => new Promise<Response>(r => { resolve = r; }));
  const pending = api.submitLeaveRequest({ leave_type: "DO", date_start: "2026-11-01", date_end: "2026-11-01" });
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  api.setToken("new-session");
  resolve(reply({ available: true, status: "open", window: { target_start: "2026-11-01", target_end_exclusive: "2026-12-01", opens_at: "server-open", closes_at: "server-close" } }));
  await expect(pending).rejects.toThrow("登入狀態已變更");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
