// src/lib/types.ts

export type ShiftType = 'A' | 'B' | 'E' | 'P' | 'N' | 'AN' | 'OFF' | 'AL' | 'SLEEP' | 'ALERT'

export interface Staff {
  id: number
  name: string
  nameEn: string
  role: string
  ward: string
  floor: string
  certs: string[]
  hoursWorked: number
  hoursTotal: number
  avatar: string
}

export interface DayEntry {
  type: ShiftType
  /** The original shift code from the Google Sheet (e.g. A7, B7, P2, K10, A7N1015) */
  shiftLabel?: string
  /** Meal time code (e.g. >1, <615, <1230) indicating when staff eats */
  mealCode?: string
  /** Note for OFF/PH days explaining the reason */
  note?: string
  tasks?: string[]
}

export interface RosterRow {
  staffId: number
  days: DayEntry[]
}
