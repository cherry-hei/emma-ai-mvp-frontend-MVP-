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
  tasks?: string[]
}

export interface RosterRow {
  staffId: number
  days: DayEntry[]
}