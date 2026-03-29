export type ShiftType = 'A' | 'B' | 'E' | 'P' | 'AN' | 'OFF' | 'AL' | 'SLEEP' | 'ALERT'
export type RoleType = 'RN' | 'EN' | 'HW' | 'PCW' | 'PTA' | 'CW' | 'AW'

export interface Staff {
  id: number
  name: string
  nameEn: string
  role: RoleType
  ward: string
  floor: string
  certs: string[]        // ← 保持 string[]
  hoursWorked: number
  hoursTotal: number
  avatar: string
}

export interface ShiftDay {
  type: ShiftType
  tasks?: string[]       // ← 保持 string[]
}

export interface RosterRow {
  staffId: number
  days: ShiftDay[]
}