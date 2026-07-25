import { NextResponse } from "next/server"

const WEEK_DATES: Record<string, string[]> = {
  "1": ["2026-05-25","2026-05-26","2026-05-27","2026-05-28","2026-05-29","2026-05-30","2026-05-31"],
  "2": ["2026-06-01","2026-06-02","2026-06-03","2026-06-04","2026-06-05","2026-06-06","2026-06-07"],
  "3": ["2026-06-08","2026-06-09","2026-06-10","2026-06-11","2026-06-12","2026-06-13","2026-06-14"],
  "4": ["2026-06-15","2026-06-16","2026-06-17","2026-06-18","2026-06-19","2026-06-20","2026-06-21"],
  "5": ["2026-06-22","2026-06-23","2026-06-24","2026-06-25","2026-06-26","2026-06-27","2026-06-28"],
  "6": ["2026-06-29","2026-06-30","2026-07-01","2026-07-02","2026-07-03","2026-07-04","2026-07-05"],
}

function escapeCsv(val: string): string {
  if (val.includes(",") || val.includes('"') || val.includes("\n")) {
    return `"${val.replace(/"/g, '""')}"`
  }
  return val
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const weekIndex = searchParams.get("week") || "3"

  // Fetch the week data from our own API
  const baseUrl = new URL(request.url).origin
  const res = await fetch(`${baseUrl}/api/naac-week?week=${weekIndex}`)
  const data = await res.json()
  const rows = data.rows || []
  const dates = WEEK_DATES[weekIndex] || WEEK_DATES["3"]

  const header = "staffName,position,date,mealCode,shiftCode,taskCode,note"
  const lines: string[] = [header]

  for (const row of rows) {
    for (let i = 0; i < (row.days?.length || 0); i++) {
      const day = row.days[i]
      const date = dates[i] || ""
      const isOff = day.shiftCode === "O" || day.shiftCode === "O," || day.shiftCode === "PH"
      const note = isOff ? (day.taskCode || "") : ""
      const taskCode = isOff ? "" : (day.taskCode || "")
      lines.push(
        [
          escapeCsv(row.name || row.position),
          escapeCsv(row.position || ""),
          date,
          escapeCsv(day.mealCode || ""),
          escapeCsv(day.shiftCode || ""),
          escapeCsv(taskCode),
          escapeCsv(note),
        ].join(",")
      )
    }
  }

  const csv = lines.join("\n")

  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename=naac-week${weekIndex}-roster.csv`,
    },
  })
}
