import { describe, expect, it } from "vitest";
import { filterRecordsByDateRange, isRecordDateRangeValid, recordOverlapsDateRange } from "../client/src/lib/recordFilters";

const records = [
  { id: "before", date_start: "2026-10-01", date_end: "2026-10-03" },
  { id: "overlap-start", date_start: "2026-10-08", date_end: "2026-10-12" },
  { id: "inside", date_start: "2026-10-10", date_end: "2026-10-10" },
  { id: "overlap-end", date_start: "2026-10-12", date_end: "2026-10-15" },
  { id: "after", date_start: "2026-10-18", date_end: "2026-10-20" },
];

describe("Records date-range filters", () => {
  it("keeps a record touching the selected start boundary", () => {
    expect(recordOverlapsDateRange(records[1], { from: "2026-10-12" })).toBe(true);
  });
  it("keeps a record touching the selected end boundary", () => {
    expect(recordOverlapsDateRange(records[3], { to: "2026-10-12" })).toBe(true);
  });
  it("uses inclusive overlap rather than requiring the entire record inside", () => {
    expect(filterRecordsByDateRange(records, { from: "2026-10-10", to: "2026-10-12" }).map((record) => record.id)).toEqual(["overlap-start", "inside", "overlap-end"]);
  });
  it("supports an open-ended lower bound", () => {
    expect(filterRecordsByDateRange(records, { from: "2026-10-18" }).map((record) => record.id)).toEqual(["after"]);
  });
  it("rejects reversed date ranges", () => {
    expect(isRecordDateRangeValid({ from: "2026-10-12", to: "2026-10-10" })).toBe(false);
    expect(filterRecordsByDateRange(records, { from: "2026-10-12", to: "2026-10-10" })).toEqual([]);
  });
});
