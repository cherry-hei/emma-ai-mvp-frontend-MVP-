import { expect, it, vi } from "vitest";
it("default release gates block candidate network calls", async () => {
  vi.stubGlobal("localStorage", { getItem: () => null });
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  const api = await import("../client/src/lib/api");
  for (const call of [() => api.getDutyRequestWindow(), () => api.listMessageContacts(), () => api.listDirectMessages(), () => api.sendDirectMessage("peer", "draft"), () => api.markDirectMessageRead("id")]) await expect(call()).rejects.toThrow();
  expect(fetchMock).not.toHaveBeenCalled(); vi.unstubAllGlobals();
});
