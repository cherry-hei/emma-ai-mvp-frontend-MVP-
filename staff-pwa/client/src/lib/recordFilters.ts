export interface DatedRecord {
  date_start: string;
  date_end: string;
}

export interface RecordDateRange {
  from?: string;
  to?: string;
}

/** ISO calendar dates sort chronologically as strings. */
export function isRecordDateRangeValid({ from, to }: RecordDateRange) {
  return !from || !to || from <= to;
}

/** Includes a record whenever any calendar day overlaps the selected range. */
export function recordOverlapsDateRange(
  record: DatedRecord,
  { from, to }: RecordDateRange,
) {
  return (!from || record.date_end >= from) && (!to || record.date_start <= to);
}

export function filterRecordsByDateRange<T extends DatedRecord>(
  records: T[],
  range: RecordDateRange,
) {
  if (!isRecordDateRangeValid(range)) return [];
  return records.filter((record) => recordOverlapsDateRange(record, range));
}
