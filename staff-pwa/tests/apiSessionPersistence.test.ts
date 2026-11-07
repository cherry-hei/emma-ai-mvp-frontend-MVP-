import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const API_BASE = "https://api.example.test";
const ACCESS_KEY = "emma_token";
const REFRESH_KEY = "emma_refresh_token";
const EXPIRES_KEY = "emma_expires_at";
const USER_KEY = "emma_user";

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, String(value));
  }
}

type ApiClient = typeof import("../client/src/lib/api");

interface FetchCall {
  url: string;
  init?: RequestInit;
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("nullable session persistence across accounts", () => {
  let storage: MemoryStorage;
  let calls: FetchCall[];
  let api: ApiClient;
  let profileResponse: Response;

  beforeEach(async () => {
    storage = new MemoryStorage();
    calls = [];
    profileResponse = jsonResponse({ id: "profile-b" });
    vi.resetModules();
    vi.stubEnv("VITE_API_BASE", API_BASE);
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, init });

        if (url === `${API_BASE}/auth/login`) {
          const { email } = JSON.parse(String(init?.body)) as { email: string };
          if (email === "account-a@example.test") {
            // A deliberately expired session establishes the stale preflight
            // condition which must not survive Account B's login.
            return jsonResponse({
              access_token: "access-account-a-test-only",
              refresh_token: "refresh-account-a-test-only",
              expires_at: 1,
              user_id: "user-a",
            });
          }
          if (email === "account-b@example.test") {
            // refresh_token and expires_at are both contract-valid omissions.
            return jsonResponse({
              access_token: "access-account-b-test-only",
              user_id: "user-b",
            });
          }
        }

        if (url === `${API_BASE}/auth/me`) {
          const accessToken = new Headers(init?.headers).get("Authorization");
          if (accessToken === "Bearer access-account-a-test-only") {
            return jsonResponse({
              id: "profile-a",
              role: "FRONTLINE",
              staff_id: "staff-a",
              facility_id: "facility-a",
              facility: { name: "Facility A" },
            });
          }
          if (accessToken === "Bearer access-account-b-test-only") {
            return jsonResponse({
              id: "profile-b",
              role: "FRONTLINE",
              staff_id: "staff-b",
              facility_id: "facility-b",
              facility: { name: "Facility B" },
            });
          }
        }

        if (url === `${API_BASE}/me/profile`) return profileResponse;
        throw new Error(`Unexpected dummy API request: ${url}`);
      })
    );

    api = await import("../client/src/lib/api");
    await api.login("account-a@example.test", "password-placeholder");
    await api.login("account-b@example.test", "password-placeholder");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("removes Account A optional credentials before Account B's expired-token preflight", async () => {
    expect(storage.getItem(ACCESS_KEY)).toBe("access-account-b-test-only");
    expect(storage.getItem(REFRESH_KEY)).toBeNull();
    expect(storage.getItem(EXPIRES_KEY)).toBeNull();
    expect(JSON.parse(storage.getItem(USER_KEY) || "{}")).toMatchObject({
      id: "user-b",
      role: "FRONTLINE",
      staff_id: "staff-b",
      facility_id: "facility-b",
      facility_name: "Facility B",
    });

    await expect(api.getMyProfile()).resolves.toEqual({ id: "profile-b" });

    expect(
      calls.filter(call => call.url === `${API_BASE}/auth/refresh`)
    ).toEqual([]);
    const profileCall = calls.find(
      call => call.url === `${API_BASE}/me/profile`
    );
    expect(new Headers(profileCall?.init?.headers).get("Authorization")).toBe(
      "Bearer access-account-b-test-only"
    );
    expect(api.getToken()).toBe("access-account-b-test-only");
    expect(api.getStoredUser()).toMatchObject({ id: "user-b" });
  });

  it("uses the documented Bearer identity endpoint after each login", () => {
    const identityCalls = calls.filter(call => call.url === `${API_BASE}/auth/me`);
    expect(identityCalls).toHaveLength(2);
    expect(new Headers(identityCalls[0].init?.headers).get("Authorization")).toBe(
      "Bearer access-account-a-test-only",
    );
    expect(new Headers(identityCalls[1].init?.headers).get("Authorization")).toBe(
      "Bearer access-account-b-test-only",
    );
  });

  it("accepts only an HTTPS backend origin without a path or credentials", () => {
    expect(api.isConfiguredApiOrigin("https://api.example.test")).toBe(true);
    expect(api.isConfiguredApiOrigin("https://api.example.test/")).toBe(true);
    expect(api.isConfiguredApiOrigin("http://api.example.test")).toBe(false);
    expect(api.isConfiguredApiOrigin("https://api.example.test/v1")).toBe(false);
    expect(api.isConfiguredApiOrigin("https://user:pass@api.example.test")).toBe(false);
  });

  it("does not use Account A's refresh value after a 401 and keeps Account B active", async () => {
    profileResponse = jsonResponse({ detail: "unauthorized" }, 401);

    await expect(api.getMyProfile()).rejects.toThrow("unauthorized");

    expect(
      calls.filter(call => call.url === `${API_BASE}/auth/refresh`)
    ).toEqual([]);
    expect(storage.getItem(REFRESH_KEY)).toBeNull();
    expect(storage.getItem(EXPIRES_KEY)).toBeNull();
    expect(api.getToken()).toBe("access-account-b-test-only");
    expect(api.getStoredUser()).toMatchObject({ id: "user-b" });
  });
});

function sessionFor(account: "a" | "b", options: { expired?: boolean } = {}) {
  return {
    access_token: `access-account-${account}-test-only`,
    refresh_token: `refresh-account-${account}-test-only`,
    expires_at: options.expired ? 1 : undefined,
    user_id: `user-${account}`,
  };
}

function profileFor(account: "a" | "b") {
  return {
    id: `profile-${account}`,
    role: "FRONTLINE",
    staff_id: `staff-${account}`,
    facility_id: `facility-${account}`,
  };
}

function expectNoPersistedSession(storage: MemoryStorage, api: ApiClient) {
  expect(storage.getItem(ACCESS_KEY)).toBeNull();
  expect(storage.getItem(REFRESH_KEY)).toBeNull();
  expect(storage.getItem(EXPIRES_KEY)).toBeNull();
  expect(storage.getItem(USER_KEY)).toBeNull();
  expect(api.getToken()).toBeNull();
  expect(api.getStoredUser()).toBeNull();
}

function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  let reject: (reason?: unknown) => void = () => {};
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("login attempt session isolation", () => {
  let storage: MemoryStorage;
  let api: ApiClient;

  beforeEach(() => {
    storage = new MemoryStorage();
    vi.resetModules();
    vi.stubEnv("VITE_API_BASE", API_BASE);
    vi.stubGlobal("localStorage", storage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("revokes Account A immediately when Account B's login is rejected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === `${API_BASE}/auth/login`) {
          const { email } = JSON.parse(String(init?.body)) as { email: string };
          return email === "account-a@example.test"
            ? jsonResponse(sessionFor("a"))
            : jsonResponse({ detail: "invalid credentials" }, 401);
        }
        if (url === `${API_BASE}/auth/me`) return jsonResponse(profileFor("a"));
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    api = await import("../client/src/lib/api");

    await api.login("account-a@example.test", "password-placeholder");
    await expect(api.login("account-b@example.test", "wrong-password")).rejects.toThrow(
      "invalid credentials",
    );

    expectNoPersistedSession(storage, api);
  });

  it("refuses generic requests while a new login is pending instead of sending Account A's Bearer token", async () => {
    const calls: FetchCall[] = [];
    const bLogin = deferred<Response>();
    const bIdentity = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, init });
        if (url === `${API_BASE}/auth/login`) {
          const { email } = JSON.parse(String(init?.body)) as { email: string };
          if (email === "account-a@example.test") return jsonResponse(sessionFor("a"));
          return bLogin.promise;
        }
        if (url === `${API_BASE}/auth/me`) {
          const bearer = new Headers(init?.headers).get("Authorization");
          return bearer === "Bearer access-account-b-test-only" ? bIdentity.promise : jsonResponse(profileFor("a"));
        }
        if (url === `${API_BASE}/me/profile`) return jsonResponse({ id: "should-not-be-requested" });
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    api = await import("../client/src/lib/api");
    await api.login("account-a@example.test", "password-placeholder");

    const pendingLogin = api.login("account-b@example.test", "password-placeholder");
    await expect(api.getMyProfile()).rejects.toThrow("登入程序進行中");
    expect(calls.filter(call => call.url === `${API_BASE}/me/profile`)).toEqual([]);

    bLogin.resolve(jsonResponse(sessionFor("b")));
    await vi.waitFor(() =>
      expect(calls.filter(call => call.url === `${API_BASE}/auth/me`)).toHaveLength(2),
    );
    await expect(api.getMyProfile()).rejects.toThrow("登入程序進行中");
    expect(calls.filter(call => call.url === `${API_BASE}/me/profile`)).toEqual([]);

    bIdentity.resolve(jsonResponse(profileFor("b")));
    await pendingLogin;
    expect(api.getToken()).toBe("access-account-b-test-only");
  });

  it("does not retain Account A when Account B's /auth/me verification fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === `${API_BASE}/auth/login`) {
          const { email } = JSON.parse(String(init?.body)) as { email: string };
          return jsonResponse(sessionFor(email === "account-a@example.test" ? "a" : "b"));
        }
        if (url === `${API_BASE}/auth/me`) {
          const bearer = new Headers(init?.headers).get("Authorization");
          return bearer === "Bearer access-account-a-test-only"
            ? jsonResponse(profileFor("a"))
            : jsonResponse({ detail: "identity rejected" }, 403);
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    api = await import("../client/src/lib/api");
    await api.login("account-a@example.test", "password-placeholder");

    await expect(api.login("account-b@example.test", "password-placeholder")).rejects.toThrow(
      "identity rejected",
    );

    expectNoPersistedSession(storage, api);
  });

  it("does not authenticate after a malformed successful /auth/me response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === `${API_BASE}/auth/login`) {
          const { email } = JSON.parse(String(init?.body)) as { email: string };
          return jsonResponse(sessionFor(email === "account-a@example.test" ? "a" : "b"));
        }
        if (url === `${API_BASE}/auth/me`) {
          const bearer = new Headers(init?.headers).get("Authorization");
          return bearer === "Bearer access-account-a-test-only"
            ? jsonResponse(profileFor("a"))
            : jsonResponse({ id: "profile-b-without-required-role" });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    api = await import("../client/src/lib/api");
    await api.login("account-a@example.test", "password-placeholder");

    await expect(api.login("account-b@example.test", "password-placeholder")).rejects.toThrow(
      "未能驗證登入身分",
    );

    expectNoPersistedSession(storage, api);
  });

  it("does not let an older failed login clear a newer successful login", async () => {
    const aLogin = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === `${API_BASE}/auth/login`) {
          const { email } = JSON.parse(String(init?.body)) as { email: string };
          return email === "account-a@example.test" ? aLogin.promise : jsonResponse(sessionFor("b"));
        }
        if (url === `${API_BASE}/auth/me`) return jsonResponse(profileFor("b"));
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    api = await import("../client/src/lib/api");

    const olderLogin = api.login("account-a@example.test", "password-placeholder");
    await api.login("account-b@example.test", "password-placeholder");
    aLogin.resolve(jsonResponse({ detail: "invalid credentials" }, 401));

    await expect(olderLogin).rejects.toThrow("登入狀態已變更");
    expect(storage.getItem(ACCESS_KEY)).toBe("access-account-b-test-only");
    expect(api.getStoredUser()).toMatchObject({ id: "user-b", role: "FRONTLINE" });
  });

  it("cannot resurrect Account A when its delayed refresh completes after Account B signs in", async () => {
    const refresh = deferred<Response>();
    let refreshStarted = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === `${API_BASE}/auth/login`) {
          const { email } = JSON.parse(String(init?.body)) as { email: string };
          return email === "account-a@example.test"
            ? jsonResponse(sessionFor("a", { expired: true }))
            : jsonResponse(sessionFor("b"));
        }
        if (url === `${API_BASE}/auth/me`) {
          const bearer = new Headers(init?.headers).get("Authorization");
          return jsonResponse(bearer === "Bearer access-account-b-test-only" ? profileFor("b") : profileFor("a"));
        }
        if (url === `${API_BASE}/auth/refresh`) {
          refreshStarted = true;
          return refresh.promise;
        }
        if (url === `${API_BASE}/me/profile`) return jsonResponse({ id: "profile-a" });
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    api = await import("../client/src/lib/api");
    await api.login("account-a@example.test", "password-placeholder");

    const oldRequest = api.getMyProfile();
    await vi.waitFor(() => expect(refreshStarted).toBe(true));
    await api.login("account-b@example.test", "password-placeholder");
    refresh.resolve(jsonResponse(sessionFor("a")));

    await expect(oldRequest).rejects.toThrow("登入狀態已變更");
    expect(storage.getItem(ACCESS_KEY)).toBe("access-account-b-test-only");
    expect(storage.getItem(REFRESH_KEY)).toBe("refresh-account-b-test-only");
    expect(api.getStoredUser()).toMatchObject({ id: "user-b", role: "FRONTLINE" });
  });
});
