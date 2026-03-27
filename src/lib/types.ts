export type ShiftType = 'A' | 'P' | 'N' | 'OFF' | 'REST' | 'SLEEP' | 'ALERT'
export type RoleType = 'RN' | 'EN' | 'HW' | 'PCW' | 'PTA' | 'CW' | 'AW'

export interface Staff {
  id: number
  name: string
  nameEn: string
  role: RoleType
  ward: string
  floor: string
  certs: string[]
  hoursWorked: number
  hoursTotal: number
  avatar: string
}

export interface ShiftDay {
  type: ShiftType
  tasks?: string[]
}

export interface RosterRow {
  staffId: number
  days: ShiftDay[]
}