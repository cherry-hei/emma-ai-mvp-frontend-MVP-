export function approvalCsv(rows, isZH) {
  const cell = (value) => {
    let text = value == null ? '' : String(value)
    if (/^[\s]*[=+@-]/u.test(text)) text = `'${text}`
    return `"${text.replaceAll('"', '""')}"`
  }
  const header = isZH
    ? ['申請ID', '員工', '職級', '單位', '類型', '開始日期', '結束日期', '申請更碼', '狀態', '理由', '決定備註']
    : ['Request ID', 'Staff', 'Rank', 'Unit', 'Type', 'Start date', 'End date', 'Requested code', 'Status', 'Reason', 'Decision note']
  const body = rows.map(row => [row.id, isZH ? row.name || row.name_en : row.name_en || row.name, row.rank, row.unit_name, row.leave_type, row.date_start, row.date_end, row.requested_shift_type, row.status, row.reason, row.decision_note])
  return '\uFEFF' + [header, ...body].map(line => line.map(cell).join(',')).join('\r\n') + '\r\n'
}
