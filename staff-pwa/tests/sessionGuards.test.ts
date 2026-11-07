import { describe, expect, it } from "vitest";
import { isCredentialGenerationCurrent, isSameCredentialSnapshot } from "../client/src/lib/sessionGuards";

const initial = { generation: 4, accessToken: "access-a", refreshToken: "refresh-a" };

describe("credential-generation session guards", () => {
  it("accepts an unchanged credential snapshot", () => {
    expect(isSameCredentialSnapshot(initial, { ...initial })).toBe(true);
  });
  it("does not coalesce refreshes across access-token changes", () => {
    expect(isSameCredentialSnapshot(initial, { ...initial, accessToken: "access-b" })).toBe(false);
  });
  it("does not coalesce refreshes across refresh-token changes", () => {
    expect(isSameCredentialSnapshot(initial, { ...initial, refreshToken: "refresh-b" })).toBe(false);
  });
  it("invalidates a late request after logout or new login changes the generation", () => {
    expect(isCredentialGenerationCurrent(initial, 5)).toBe(false);
  });
  it("allows the request that still belongs to the active generation", () => {
    expect(isCredentialGenerationCurrent(initial, 4)).toBe(true);
  });
});
