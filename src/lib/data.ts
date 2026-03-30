import { Staff, RosterRow } from './types'

export const STAFF: Staff[] = [
  { id:1, name:'余逸詩', nameEn:'Yu Yat Sze', role:'RN', ward:'East Wing', floor:'L4', certs:['ACLS','Triage','BLS'], hoursWorked:140, hoursTotal:160, avatar:'余' },
  { id:2, name:'梁嘉琪', nameEn:'Leung Ka Kei', role:'EN', ward:'West Wing', floor:'F2', certs:['First Aid','Manual Hand.'], hoursWorked:120, hoursTotal:160, avatar:'梁' },
  { id:3, name:'王雅琛', nameEn:'Wong Yat Sum', role:'HW', ward:'General Ward A', floor:'F1', certs:['Elder Care','Vitals'], hoursWorked:149, hoursTotal:160, avatar:'王' },
  { id:4, name:'何啟晴', nameEn:'Ho Kai Ching', role:'CW', ward:'Rehab Suite', floor:'F1', certs:['Personal Care'], hoursWorked:96, hoursTotal:160, avatar:'何' },
  { id:5, name:'黃司琦', nameEn:'Wong Sze Kai', role:'PTA', ward:'Gym', floor:'F1', certs:['Rehab Tech'], hoursWorked:128, hoursTotal:160, avatar:'黃' },
  { id:6, name:'黃靜賢', nameEn:'Wong Jing Yin', role:'PCW', ward:'F3 Night Unit', floor:'F3', certs:['Bathing','Transfer'], hoursWorked:132, hoursTotal:160, avatar:'黃' },
  { id:7, name:'李紹洪', nameEn:'Li Shao Hung', role:'AW', ward:'Facility-wide', floor:'ALL', certs:['Infection Ctrl'], hoursWorked:160, hoursTotal:160, avatar:'李' },
]

export const ROSTER: RosterRow[] = [
  // Yu Yat Sze: 23/3=P, 24/3=A, 25/3=P, 26/3=AN, 27/3=SLEEP, 28/3=OFF, 29/3=AL
  { staffId:1, days:[
    {type:'P', tasks:['Med Checking','ICP Review','FU Chat']},
    {type:'A', tasks:['Medication Mgmt']},
    {type:'P', tasks:['Wound Care','ICP Update']},
    {type:'AN', tasks:['Night Meds','Protocol Check']},
    {type:'SLEEP'},
    {type:'OFF'},
    {type:'AL'}
  ]},
  // Leung Ka Kei: 23/3=OFF, 24/3=P, 25/3=P, 26/3=A, 27/3=P, 28/3=AN, 29/3=SLEEP
  { staffId:2, days:[
    {type:'OFF'},
    {type:'P', tasks:['Wound Dressing','FU PGT']},
    {type:'P', tasks:['Standard Care']},
    {type:'A', tasks:['Wound Mgmt']},
    {type:'P', tasks:['Transferring']},
    {type:'AN', tasks:['Patient Obs']},
    {type:'SLEEP'}
  ]},
  // Wong Yat Sum: 23/3=A, 24/3=AN, 25/3=SLEEP, 26/3=OFF, 27/3=A, 28/3=A, 29/3=OFF
  { staffId:3, days:[
    {type:'A', tasks:['Vital Signs','AOM (Oral)']},
    {type:'AN'},
    {type:'SLEEP'},
    {type:'OFF'},
    {type:'A'},
    {type:'A'},
    {type:'OFF'}
  ]},
  { staffId:4, days:[
    {type:'P', tasks:['Oral Feeding','Diaper Change']},
    {type:'P'},{type:'OFF'},{type:'P'},{type:'P'},{type:'A'},{type:'A'}
  ]},
  { staffId:5, days:[
    {type:'A', tasks:['Rehab Session']},
    {type:'A'},{type:'A'},{type:'A'},{type:'A'},{type:'OFF'},{type:'OFF'}
  ]},
  { staffId:6, days:[
    {type:'N'},{type:'N'},
    {type:'ALERT'},{type:'OFF'},{type:'N'},{type:'N'},{type:'N'}
  ]},
  { staffId:7, days:[
    {type:'P', tasks:['Infection Control']},
    {type:'P'},{type:'P'},{type:'P'},{type:'P'},{type:'A'},{type:'A'}
  ]},
]

export const DAYS = ['MON 23/3','TUE 24/3','WED 25/3','THU 26/3','FRI 27/3','SAT 28/3','SUN 29/3']

export const KPI = {
  staffingRatio: '1:20',
  emergencyResponseTime: '95%',
  otHours: 16,
  otDelta: -18,
  agencyShifts: 12,
  agencyDelta: -10,
  completion: 94,
  otCost: 28400,
  agencyCost: 41600,
  adminSaved: 70,
  lsgRatio: 22.4,
}