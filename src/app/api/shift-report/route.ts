import { NextResponse } from "next/server"

// Shift code → hours mapping (from 編更安排 Word document)
const SHIFT_HOURS: Record<string, number> = {
  A1: 8, A7: 8, A9: 8, A10: 8, A130: 8, A230: 8, A610: 8, A630: 8, A730: 8, A830: 8, A1030: 8,
  "A7#": 8, "A230#": 8, "A730#": 8, "A7x": 8.17, "A8x": 8.17, "A9x": 8.17, "A1x": 8.17,
  "A7s": 8.5, "A8s": 8.5, "A9s": 8.5, "A10s": 8.5, "A610s": 8.5, "A630s": 8.5,
  A7N10: 17, A7N1015: 17, A8N10: 17,
  B7: 9, B9: 9, B830: 9, B930: 9, "B7s": 9.5, "B7x": 9.17,
  G7: 7, G9: 7, G130: 7, G2: 7, "G7s": 7.5, "G10s": 7, G7N10: 16.5,
  P1: 9, P2: 8,
  N10: 9, N1015: 9, K10: 10, K830: 10,
  AL: 8, "AL,": 9, ALx: 8.17, SL: 8, SLx: 8.17, BDL: 8, BDLx: 8.17,
  PH: 0, O: 0, "O,": 0, NO: 0, "CL-8": 8, FFLx: 8.17,
}

function getHours(code: string): number {
  if (!code) return 0
  // Try exact match first
  if (SHIFT_HOURS[code] !== undefined) return SHIFT_HOURS[code]
  // Try without trailing modifiers
  const base = code.replace(/#$/, "")
  if (SHIFT_HOURS[base] !== undefined) return SHIFT_HOURS[base]
  // Infer from prefix
  if (code.startsWith("A") && code.includes("N")) return 17
  if (code.startsWith("G") && code.includes("N")) return 16.5
  if (code.startsWith("A")) return 8
  if (code.startsWith("B")) return 9
  if (code.startsWith("G")) return 7
  if (code.startsWith("P")) return 8
  if (code.startsWith("K")) return 10
  if (code.startsWith("N")) return 9
  return 0
}

function isNightShift(code: string): boolean {
  if (!code) return false
  return code.includes("N10") || code.includes("N1015") || code.startsWith("K") || code.includes("N10")
}

function isAShift(code: string): boolean {
  if (!code) return false
  if (code === "O" || code === "O," || code === "PH" || code === "NO") return false
  if (code.startsWith("AL") || code.startsWith("SL") || code.startsWith("CL") || code.startsWith("BDL") || code.startsWith("FFL")) return false
  if (code.startsWith("P")) return false
  if (isNightShift(code)) return false
  return code.startsWith("A") || code.startsWith("B") || code.startsWith("G")
}

function isPShift(code: string): boolean {
  if (!code) return false
  return code.startsWith("P")
}

function isOffDay(code: string): boolean {
  if (!code) return true
  return code === "O" || code === "O," || code === "PH" || code === "NO"
}

function escapeCsv(val: string): string {
  if (val.includes(",") || val.includes('"') || val.includes("\n")) {
    return `"${val.replace(/"/g, '""')}"`
  }
  return val
}

interface StaffRow {
  staffId: number
  position: string
  name: string
  days: { shiftCode?: string; mealCode?: string; taskCode?: string }[]
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const reportType = searchParams.get("type") || "hours"
  const baseUrl = new URL(request.url).origin

  // Load all 6 weeks
  const allWeeks: StaffRow[][] = []
  for (let w = 1; w <= 6; w++) {
    const res = await fetch(`${baseUrl}/api/naac-week?week=${w}`)
    const data = await res.json()
    allWeeks.push(data.rows || [])
  }

  let csv = ""
  let filename = ""

  switch (reportType) {
    case "hours": {
      // Hours report: staff name, position, total hours over 6 weeks
      const lines = ["staffName,position,totalHours,weeklyBreakdown"]
      const staffCount = allWeeks[0]?.length || 0
      for (let s = 0; s < staffCount; s++) {
        const staff = allWeeks[0][s]
        let total = 0
        const weekly: number[] = []
        for (let w = 0; w < 6; w++) {
          let weekTotal = 0
          const row = allWeeks[w]?.[s]
          if (row) {
            for (const day of row.days) {
              weekTotal += getHours(day.shiftCode || "")
            }
          }
          weekly.push(Math.round(weekTotal * 10) / 10)
          total += weekTotal
        }
        lines.push(`${escapeCsv(staff.name)},${escapeCsv(staff.position)},${Math.round(total * 10) / 10},"${weekly.join("|")}"`)
      }
      csv = lines.join("\n")
      filename = "shift-report-hours.csv"
      break
    }

    case "ph-dayoff": {
      // PH & Day Off report
      const lines = ["staffName,position,phDays,offDays,alDays,slDays,totalOffDays"]
      const staffCount = allWeeks[0]?.length || 0
      for (let s = 0; s < staffCount; s++) {
        const staff = allWeeks[0][s]
        let ph = 0, off = 0, al = 0, sl = 0
        for (let w = 0; w < 6; w++) {
          const row = allWeeks[w]?.[s]
          if (row) {
            for (const day of row.days) {
              const c = day.shiftCode || ""
              if (c === "PH") ph++
              else if (c === "O" || c === "O," || c === "NO") off++
              else if (c.startsWith("AL")) al++
              else if (c.startsWith("SL")) sl++
            }
          }
        }
        lines.push(`${escapeCsv(staff.name)},${escapeCsv(staff.position)},${ph},${off},${al},${sl},${ph + off + al + sl}`)
      }
      csv = lines.join("\n")
      filename = "shift-report-ph-dayoff.csv"
      break
    }

    case "do-count": {
      // DO shift count report
      const lines = ["staffName,position,doCount,totalWorkingDays,avgHoursBetweenDOs"]
      const staffCount = allWeeks[0]?.length || 0
      for (let s = 0; s < staffCount; s++) {
        const staff = allWeeks[0][s]
        let doCount = 0, workDays = 0, totalHours = 0
        for (let w = 0; w < 6; w++) {
          const row = allWeeks[w]?.[s]
          if (row) {
            for (const day of row.days) {
              const c = day.shiftCode || ""
              if (isOffDay(c)) doCount++
              else { workDays++; totalHours += getHours(c) }
            }
          }
        }
        const avgHours = doCount > 1 ? Math.round(totalHours / (doCount - 1) * 10) / 10 : 0
        lines.push(`${escapeCsv(staff.name)},${escapeCsv(staff.position)},${doCount},${workDays},${avgHours}`)
      }
      csv = lines.join("\n")
      filename = "shift-report-do-count.csv"
      break
    }

    case "ap-shifts": {
      // A/P shift distribution report
      const lines = ["staffName,position,aShiftCount,pShiftCount,nightCount,totalShifts"]
      const staffCount = allWeeks[0]?.length || 0
      for (let s = 0; s < staffCount; s++) {
        const staff = allWeeks[0][s]
        let aCount = 0, pCount = 0, nCount = 0
        for (let w = 0; w < 6; w++) {
          const row = allWeeks[w]?.[s]
          if (row) {
            for (const day of row.days) {
              const c = day.shiftCode || ""
              if (isAShift(c)) aCount++
              else if (isPShift(c)) pCount++
              else if (isNightShift(c)) nCount++
            }
          }
        }
        lines.push(`${escapeCsv(staff.name)},${escapeCsv(staff.position)},${aCount},${pCount},${nCount},${aCount + pCount + nCount}`)
      }
      csv = lines.join("\n")
      filename = "shift-report-ap-distribution.csv"
      break
    }

    case "night-gender": {
      // Night shift gender report (using position-based gender inference for demo)
      // In NAAC context: 雄=male, others=female (simplified)
      const lines = ["staffName,position,gender,nightShiftCount_MonFri,nightShiftCount_Weekend"]
      const staffCount = allWeeks[0]?.length || 0
      for (let s = 0; s < staffCount; s++) {
        const staff = allWeeks[0][s]
        // Simple gender inference from name suffix (demo only)
        const gender = staff.name.includes("雄") ? "M" : "F"
        let monFri = 0, weekend = 0
        for (let w = 0; w < 6; w++) {
          const row = allWeeks[w]?.[s]
          if (row) {
            row.days.forEach((day, dayIdx) => {
              if (isNightShift(day.shiftCode || "")) {
                if (dayIdx < 5) monFri++
                else weekend++
              }
            })
          }
        }
        if (monFri > 0 || weekend > 0) {
          lines.push(`${escapeCsv(staff.name)},${escapeCsv(staff.position)},${gender},${monFri},${weekend}`)
        }
      }
      csv = lines.join("\n")
      filename = `shift-report-night-gender.csv`
      break
    }

    default:
      csv = "error,Unknown report type"
      filename = "error.csv"
  }

  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename=${filename}`,
    },
  })
}
