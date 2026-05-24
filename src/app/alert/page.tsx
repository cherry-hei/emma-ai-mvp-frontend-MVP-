'use client'

import { useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'
const PINK_HOVER = '#c9156a'

type FlowStep = 1 | 2 | 3 | 4 | 5
type ChatMsg = { from: 'system' | 'staff'; text: string }

const KPI_CARDS = [
  {
    label: { zh: 'March SL/DSL 總事件', en: 'March SL/DSL Events' },
    value: '46', unit: { zh: '宗', en: 'cases' }, color: '#E8187A',
    sub: { zh: 'March 2026 實際', en: 'March 2026 Actual' },
  },
  {
    label: { zh: 'Emma AI 自動處理', en: 'Auto-resolved by AI' },
    value: '38', unit: { zh: '宗', en: 'cases' }, color: '#10b981',
    sub: { zh: '82.6% 自動解決', en: '82.6% Auto-resolved' },
  },
  {
    label: { zh: '平均響應時間', en: 'Avg Response Time' },
    value: '14', unit: 'min', color: '#f59e0b',
    sub: { zh: '人手處理需 45min', en: 'Manual handling: 45min' },
  },
  {
    label: { zh: '合規達標率', en: 'Compliance Rate' },
    value: '98', unit: '%', color: '#6366f1',
    sub: { zh: 'SWD 人手比率', en: 'SWD Staffing Ratio' },
  },
]

const ALERT_TYPES = [
  { icon: '😷', label: { zh: 'Sick Leave (SL)', en: 'Sick Leave (SL)' }, count: 31, color: '#E8187A', pct: 67 },
  { icon: '🏥', label: { zh: 'DSL（病假 > 3日）', en: 'DSL (Sick Leave > 3d)' }, count: 8, color: '#f59e0b', pct: 17 },
  { icon: '⚡', label: { zh: 'Urgent Leave', en: 'Urgent Leave' }, count: 5, color: '#8b5cf6', pct: 11 },
  { icon: '🕐', label: { zh: 'Lateness / Late Report', en: 'Lateness / Late Report' }, count: 2, color: '#6b7280', pct: 4 },
]

const RECENT_RESOLVED = [
  { id: 'SL-2603',  type: { zh: '病假', en: 'Sick Leave' }, staff: 'Wong Mei Ling', role: 'RCW', ward: 'F3',        shift: { zh: 'N更 21:30–7:00',  en: 'N shift 21:30–07:00' }, time: '08:43 AM',  resolvedBy: 'Chan S.M.',    min: 12 },
  { id: 'DSL-2601', type: { zh: 'DSL > 3日', en: 'DSL > 3d' }, staff: 'Lam Yee Ting',  role: 'HW',  ward: 'F1',        shift: { zh: 'A更 07:00–15:00', en: 'A shift 07:00–15:00' }, time: '07:15 AM',  resolvedBy: 'Agency PT HW', min: 27 },
  { id: 'SL-2598',  type: { zh: '病假', en: 'Sick Leave' }, staff: 'Yu Yat Sze',    role: 'RN',  ward: 'East Wing', shift: { zh: 'A更 07:00–15:00', en: 'A shift 07:00–15:00' }, time: 'Yesterday', resolvedBy: 'Li Wing RN',   min: 8  },
  { id: 'UL-2595',  type: { zh: '緊急假', en: 'Urgent' }, staff: 'Cheung Ka Man', role: 'RCW', ward: 'F2',        shift: { zh: 'P更 13:30–21:30', en: 'P shift 13:30–21:30' }, time: 'Yesterday', resolvedBy: 'Wong Kai EN',  min: 19 },
]

const ALERTS_DATA = [
  {
    id: 1,
    title:   { zh: 'P更人手不足 — F3',       en: 'P Shift Understaffed — F3' },
    desc:    { zh: '護理員(PCW) 請假 ALERT，需即時補更', en: 'Care Worker (PCW) absent — immediate cover required' },
    ward: 'F3',
    time:    { zh: '今日 13:30', en: 'Today 13:30' },
    urgent: true,
  },
  {
    id: 2,
    title:   { zh: 'OT 警報 — 張曉晴',       en: 'OT Alert — Cheung Hiu Ching' },
    desc:    { zh: '張曉晴本月累計 OT 已達 160h，超出法定上限', en: 'Cheung Hiu Ching has accumulated 160h OT this month, exceeding legal limit' },
    ward:    { zh: '全院', en: 'Facility-wide' },
    time:    { zh: '今日', en: 'Today' },
    urgent: true,
  },
  {
    id: 3,
    title:   { zh: '牌照即將到期提醒',        en: 'Licence Expiry Reminder' },
    desc:    { zh: '員工 ACLS 牌照將於 30 天後到期，請安排更新', en: 'Staff ACLS licence expiring in 30 days — renewal required' },
    ward:    { zh: '東翼', en: 'East Wing' },
    time:    { zh: '30 天後', en: 'In 30 days' },
    urgent: false,
  },
]

const AI_SUMMARY = [
  {
    label:  { zh: '平均響應時間', en: 'Avg Response Time' },
    before: { zh: '45 min',      en: '45 min' },
    after:  { zh: 'AI 自動處理', en: 'AI Auto-handled' },
    save:   { zh: '↓ 69%',       en: '↓ 69%' },
  },
  {
    label:  { zh: '合規核查',     en: 'Compliance Check' },
    before: { zh: '人手核查',     en: 'Manual Check' },
    after:  { zh: 'AI 即時核查',  en: 'AI Instant Check' },
    save:   { zh: '節省 31h/月',  en: 'Saves 31h/month' },
  },
  {
    label:  { zh: 'SWD 合規率',   en: 'SWD Compliance' },
    before: { zh: '人手追蹤',     en: 'Manual Tracking' },
    after:  { zh: 'AI 自動監控',  en: 'AI Auto-monitoring' },
    save:   { zh: '98% 達標率',   en: '98% Compliance Rate' },
  },
]

const STEPS_DATA = [
  { label: { zh: '確認請假資料', en: 'Confirm Leave Details' },    sub: { zh: 'Wong Jing Yin 護理員(CW)\n30/3/2026 P更 · Sick Leave', en: 'Wong Jing Yin Care Worker (CW)\n30/3/2026 P shift · Sick Leave' } },
  { label: { zh: '核查合規影響', en: 'Compliance Impact Check' },  sub: { zh: '人手比率 ⚠️ 低於法定\n需即時補更', en: 'Staffing ratio ⚠️ below legal minimum\nImmediate cover required' } },
  { label: { zh: 'AI 推薦候選',  en: 'AI Recommended Staff' },     sub: { zh: '推薦 3 名候選員工\n(Rule-safe verification)', en: '3 candidates recommended\n(Rule-safe verification)' } },
  { label: { zh: '發送通知',     en: 'Send Notification' },        sub: { zh: '透過 WhatsApp 通知員工 App', en: 'Notify staff via WhatsApp App' } },
  { label: { zh: '完成處理',     en: 'Resolved' },                 sub: { zh: '30/3/2026 P更 完成\nHo Kai Ching (CW) 接更\nRoster 同步更新 ✅', en: '30/3/2026 P shift covered\nHo Kai Ching (CW) assigned\nRoster synchronized ✅' } },
]

const CANDIDATES = [
  { name: '何佳晴', rank: 'PCW', score: 98, note: { zh: '有空 · 評分 4.5/5 · 熟悉 F3 · TOIL 累積中', en: 'Available · Score 4.5/5 · Familiar with F3 · TOIL accruing' }, badge: { zh: '最佳推薦', en: 'Top Pick' } },
  { name: '陳志明', rank: 'PCW', score: 82, note: { zh: 'Day Off · 評分 3.8/5 · 曾駐守 F3', en: 'Day Off · Score 3.8/5 · Previously in F3' }, badge: { zh: '次選', en: 'Alt' } },
]

function ResolutionModal({ onClose, lang }: { onClose: () => void; lang: 'zh' | 'en' }) {
  const [step, setStep]             = useState<FlowStep>(1)
  const [selectedStaff, setSelected] = useState<string | null>(null)
  const [chatOpen, setChatOpen]     = useState(false)
  const [chatMsgs, setChatMsgs]     = useState<ChatMsg[]>([])
  const [chatPhase, setChatPhase]   = useState(0)

  const L = {
    zh: {
      title: 'Resolution Flow: 補更', sub: 'Wong Jing Yin 護理員 · 30/3/2026 P更',
      confirmAlert: '緊急警報', staff: '員工：', date: '日期：', shift: '更次：', reason: '原因：',
      staffVal: 'Wong Jing Yin 護理員(CW)', dateVal: '30/3/2026', shiftVal: 'P更 (13:30–21:30)', reasonVal: 'Sick Leave',
      nextStep: '繼續下一步', complianceWarn: '⚠️ 人手比率低於法定要求',
      complianceDesc: 'P更 (13:30–21:30) 需要最少 1 名CW，目前人手不足',
      needCover: '需即時安排補更', aiSuggest: '查看 AI 推薦', toil: 'TOIL 補時積分說明',
      toilItems: ['TOIL 補時 +1天 自動 HR 記錄', '推薦員工積分 +10pts', 'AI 自動核查規則無違規'],
      viewDetail: '查看詳情', assign: '✓ Assign',
      notifySent: '通知透過 WhatsApp 發送員工 App', staffConfirm: '等待員工確認',
      resolved: '✅ 30/3/2026 P更 完成補更', assignedTo: '接更員工：Ho Kai Ching (CW)',
      rosterSync: 'Roster 已同步更新', toilAdded: 'TOIL +8小時 已自動 HR 記錄 ✅',
      chatSystem: '緊急補更通知\nP更 (13:30-21:30) 有員工請假\n請問你今日有空接更嗎？\n補貼：OT x1.5，TOIL 積分',
      chatReply: '我可以接更 ✓',
      chatConfirm: '✅ 收到！已更新排更表\nP更 (13:30-21:30) 已確認\n工時 +8小時，OT x1.5 積分 已自動記錄',
      staffReplyBtn: '模擬員工接受（點此模擬回覆）✓',
      rosterDone: '✅ 排更已確認，Roster 同步更新',
      aiPanel: 'AI 推薦候選員工', notifyWhatsApp: '📲 通知 WhatsApp', online: '在線',
    },
    en: {
      title: 'Resolution Flow: Cover Shift', sub: 'Wong Jing Yin Care Worker · 30/3/2026 P shift',
      confirmAlert: 'Urgent Alert', staff: 'Staff: ', date: 'Date: ', shift: 'Shift: ', reason: 'Reason: ',
      staffVal: 'Wong Jing Yin Care Worker (CW)', dateVal: '30/3/2026', shiftVal: 'P shift (13:30–21:30)', reasonVal: 'Sick Leave',
      nextStep: 'Next Step', complianceWarn: '⚠️ Staffing ratio below legal minimum',
      complianceDesc: 'P shift (13:30–21:30) requires min. 1 CW — currently understaffed',
      needCover: 'Immediate cover required', aiSuggest: 'View AI Recommendations', toil: 'TOIL Points Explanation',
      toilItems: ['TOIL +1 day auto HR record', 'Recommended staff +10pts', 'AI rule-safe verification passed'],
      viewDetail: 'View Detail', assign: '✓ Assign',
      notifySent: 'Notification sent via WhatsApp Staff App', staffConfirm: 'Awaiting staff confirmation',
      resolved: '✅ 30/3/2026 P shift successfully covered', assignedTo: 'Assigned to: Ho Kai Ching (CW)',
      rosterSync: 'Roster synchronized', toilAdded: 'TOIL +8hrs auto-recorded in HR ✅',
      chatSystem: 'Urgent Cover Request\nP shift (13:30-21:30) has a vacancy\nAre you available to cover today?\nBenefit: OT x1.5 + TOIL points',
      chatReply: 'I can cover ✓',
      chatConfirm: '✅ Confirmed! Roster updated\nP shift (13:30-21:30) confirmed\n+8hrs OT x1.5 points auto-recorded',
      staffReplyBtn: 'Simulate staff acceptance (click to simulate) ✓',
      rosterDone: '✅ Shift confirmed — Roster synchronized',
      aiPanel: 'AI Recommended Staff', notifyWhatsApp: '📲 Notify WhatsApp', online: 'Online',
    },
  }
  const lx = L[lang]

  function handleAssign(name: string) {
    setSelected(name)
    setChatOpen(true)
    setChatMsgs([{ from: 'system', text: lx.chatSystem }])
    setChatPhase(1)
    setStep(4)
  }

  function handleStaffReply() {
    if (chatPhase !== 1) return
    setChatMsgs(m => [...m, { from: 'staff', text: lx.chatReply }])
    setChatPhase(2)
    setTimeout(() => {
      setChatMsgs(m => [...m, { from: 'system', text: lx.chatConfirm }])
      setChatPhase(3)
      setStep(5)
    }, 800)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.45)' }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl mx-4 overflow-hidden flex flex-col" style={{ maxHeight: '92vh' }}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <div>
            <div className="text-sm font-bold text-gray-900">{lx.title}</div>
            <div className="text-[10px] text-gray-400 mt-0.5">{lx.sub}</div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">✕</button>
        </div>
        <div className="flex flex-1 overflow-hidden">
          <div className="w-64 flex-shrink-0 border-r border-gray-100 p-4 space-y-1 overflow-y-auto">
            {STEPS_DATA.map((s, i) => {
              const n = (i + 1) as FlowStep
              const done = step > n
              const active = step === n
              return (
                <button key={n} onClick={() => setStep(n)}
                  className="w-full text-left p-3 rounded-xl transition-all"
                  style={{ background: active ? '#fff0f5' : done ? '#f9fafb' : 'transparent' }}>
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0"
                      style={{ background: done ? '#10B981' : active ? PINK : '#e5e7eb', color: done || active ? '#fff' : '#9ca3af' }}>
                      {done ? '✓' : n}
                    </div>
                    <span className="text-[11px] font-semibold" style={{ color: active ? PINK : done ? '#374151' : '#9ca3af' }}>
                      {s.label[lang]}
                    </span>
                  </div>
                  {active && <p className="text-[10px] text-gray-500 mt-1 pl-7 whitespace-pre-line leading-relaxed">{s.sub[lang]}</p>}
                </button>
              )
            })}
          </div>
          <div className="flex-1 overflow-y-auto p-5">
            {step === 1 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{STEPS_DATA[0].label[lang]}</div>
                <div className="bg-red-50 border border-red-100 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-base">🚨</span>
                    <span className="text-sm font-semibold text-red-700">{lx.confirmAlert}</span>
                  </div>
                  <div className="space-y-1.5 text-[11px] text-gray-700">
                    <div><span className="text-gray-400">{lx.staff}</span>{lx.staffVal}</div>
                    <div><span className="text-gray-400">{lx.date}</span>{lx.dateVal}</div>
                    <div><span className="text-gray-400">{lx.shift}</span>{lx.shiftVal}</div>
                    <div><span className="text-gray-400">{lx.reason}</span>{lx.reasonVal}</div>
                  </div>
                </div>
                <button onClick={() => setStep(2)} className="w-full py-2 rounded-xl text-white text-xs font-semibold" style={{ background: PINK }}>{lx.nextStep}</button>
              </div>
            )}
            {step === 2 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{STEPS_DATA[1].label[lang]}</div>
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <span>⚠️</span>
                    <span className="text-xs font-semibold text-amber-800">{lx.complianceWarn}</span>
                  </div>
                  <div className="text-[11px] text-amber-700">{lx.complianceDesc}</div>
                  <div className="text-[11px] font-medium text-amber-800">{lx.needCover}</div>
                </div>
                <button onClick={() => setStep(3)} className="w-full py-2 rounded-xl text-white text-xs font-semibold" style={{ background: PINK }}>{lx.aiSuggest}</button>
              </div>
            )}
            {step === 3 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900 mb-3">{STEPS_DATA[2].label[lang]}</div>
                {CANDIDATES.map((c) => (
                  <div key={c.name} className="bg-white border border-gray-200 rounded-xl p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold text-white flex-shrink-0" style={{ background: PINK }}>{c.name[0]}</div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-gray-900">{c.name}</span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full text-white font-medium" style={{ background: c.score >= 90 ? '#10B981' : '#F59E0B' }}>
                              {c.badge[lang]} {c.score}分
                            </span>
                          </div>
                          <div className="text-[10px] text-gray-500 mt-0.5">{c.rank} · {c.note[lang]}</div>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button className="px-2.5 py-1 text-[10px] border border-gray-200 rounded-lg hover:bg-gray-50">{lx.viewDetail}</button>
                        <button onClick={() => handleAssign(c.name)} className="px-2.5 py-1 text-[10px] rounded-lg text-white font-medium" style={{ background: PINK }}>{lx.assign}</button>
                      </div>
                    </div>
                  </div>
                ))}
                <div className="bg-gray-50 border border-gray-100 rounded-xl p-3 mt-2">
                  <div className="text-[11px] font-semibold text-gray-700 mb-1.5">{lx.toil}</div>
                  <div className="space-y-1">
                    {lx.toilItems.map(t => (
                      <div key={t} className="flex items-center gap-1.5 text-[10px] text-gray-600">
                        <span className="text-green-500">✓</span>{t}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {step === 4 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{STEPS_DATA[3].label[lang]}</div>
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-[11px] text-blue-800 space-y-1">
                  <div>{lx.notifySent}</div>
                  <div>{lx.staffConfirm}</div>
                </div>
              </div>
            )}
            {step === 5 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{STEPS_DATA[4].label[lang]}</div>
                <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-1.5 text-[11px] text-green-800">
                  <div className="font-semibold text-green-700">{lx.resolved}</div>
                  <div>{lx.assignedTo}</div>
                  <div>{lx.rosterSync}</div>
                  <div>{lx.toilAdded}</div>
                </div>
              </div>
            )}
          </div>
          <div className="w-64 flex-shrink-0 border-l border-gray-100 flex flex-col">
            <div className="p-3 border-b border-gray-100">
              <div className="text-[10px] font-bold text-gray-700 uppercase tracking-wider mb-2">{lx.aiPanel}</div>
              {CANDIDATES.map((c) => (
                <div key={c.name} className="mb-2 p-2.5 rounded-lg border border-gray-100 bg-gray-50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-semibold text-gray-800">{c.name} ({c.rank})</span>
                    <span className="text-[9px] px-1.5 rounded-full text-white" style={{ background: c.score >= 90 ? '#10B981' : '#F59E0B' }}>
                      {c.badge[lang]} {c.score}
                    </span>
                  </div>
                  <div className="text-[9px] text-gray-500 mb-2 leading-relaxed">{c.note[lang]}</div>
                  <div className="flex gap-1.5">
                    <button onClick={() => handleAssign(c.name)} className="flex-1 py-1 text-[9px] rounded-lg text-white font-medium" style={{ background: PINK }}>{lx.notifyWhatsApp}</button>
                    <button className="px-2 py-1 text-[9px] border border-gray-200 rounded-lg hover:bg-white">{lx.viewDetail}</button>
                  </div>
                </div>
              ))}
            </div>
            {chatOpen && (
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="px-3 py-2 border-b border-gray-100 flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0" style={{ background: PINK }}>{selectedStaff?.[0]}</div>
                  <div>
                    <div className="text-[10px] font-semibold text-gray-800">{selectedStaff}</div>
                    <div className="text-[8px] text-green-500">● {lx.online}</div>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
                  {chatMsgs.map((m, i) => (
                    <div key={i} className={`flex ${m.from === 'staff' ? 'justify-end' : 'justify-start'}`}>
                      <div className="max-w-[85%] px-2.5 py-1.5 rounded-xl text-[10px] leading-relaxed whitespace-pre-line"
                        style={{ background: m.from === 'system' ? '#f3f4f6' : PINK, color: m.from === 'system' ? '#374151' : '#fff', borderRadius: m.from === 'system' ? '4px 12px 12px 12px' : '12px 4px 12px 12px' }}>
                        {m.text}
                      </div>
                    </div>
                  ))}
                </div>
                {chatPhase === 1 && (
                  <div className="p-2 border-t border-gray-100">
                    <button onClick={handleStaffReply} className="w-full py-1.5 text-[10px] rounded-lg text-white font-medium" style={{ background: '#10B981' }}>{lx.staffReplyBtn}</button>
                  </div>
                )}
                {chatPhase === 3 && (
                  <div className="p-2 border-t border-gray-100">
                    <div className="text-[9px] text-center text-green-600 font-medium">{lx.rosterDone}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function AlertPage() {
  const { lang } = useLang()
  const [modalOpen, setModalOpen] = useState(false)

  const L = {
    zh: {
      pageTitle: 'Alert 警報中心', pageSub: '3 個緊急警報 · March 2026 實時監控中',
      newRequest: '+ 新增請求', distribTitle: 'March 2026 SL/DSL 事件分佈',
      distribTotal: '共 46 宗', activeTitle: '緊急警報',
      recentTitle: '最近已處理事件', recentSub: 'March 2026 · 最近 4 宗',
      resolvedBy: '由', resolvedSuffix: '處理', resolvedMin: 'min 完成處理',
      resolved: '已處理', viewDetail: '查看', handle: '處理',
      aiTitle: 'Emma AI · March 2026 Alert 分析',
      unitCases: '宗', urgentBadge: '緊急', normalBadge: '一般',
    },
    en: {
      pageTitle: 'Alert Centre', pageSub: '3 active alerts · March 2026 live monitoring',
      newRequest: '+ New Request', distribTitle: 'March 2026 SL/DSL Distribution',
      distribTotal: 'Total: 46 cases', activeTitle: 'Active Alerts',
      recentTitle: 'Recently Resolved', recentSub: 'March 2026 · Last 4 cases',
      resolvedBy: 'By', resolvedSuffix: '', resolvedMin: 'min to resolve',
      resolved: 'Resolved', viewDetail: 'View', handle: 'Handle',
      aiTitle: 'Emma AI · March 2026 Alert Analysis',
      unitCases: 'cases', urgentBadge: 'Urgent', normalBadge: 'Normal',
    },
  }
  const lx = L[lang]

  return (
    <div className="p-5 space-y-5">
      {modalOpen && <ResolutionModal onClose={() => setModalOpen(false)} lang={lang} />}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{lx.pageTitle}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{lx.pageSub}</p>
        </div>
        <button className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
          style={{ background: PINK }}
          onMouseEnter={e => (e.currentTarget.style.background = PINK_HOVER)}
          onMouseLeave={e => (e.currentTarget.style.background = PINK)}>
          {lx.newRequest}
        </button>
      </div>

      {/* Active Alerts */}
      <div>
        <div className="text-sm font-semibold text-gray-900 mb-3">{lx.activeTitle}</div>
        <div className="space-y-3">
          {ALERTS_DATA.map((alert) => (
            <div key={alert.id} className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 mt-0.5"
                    style={{ background: alert.urgent ? '#FFE4E6' : '#FEF3C7' }}>
                    {alert.urgent ? '🚨' : '⚠️'}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-gray-900">{alert.title[lang]}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{alert.desc[lang]}</div>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {typeof alert.ward === 'object' ? alert.ward[lang] : alert.ward}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {typeof alert.time === 'object' ? alert.time[lang] : alert.time}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full text-white font-medium"
                        style={{ background: alert.urgent ? PINK : '#F59E0B' }}>
                        {alert.urgent ? lx.urgentBadge : lx.normalBadge}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <button className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50">{lx.viewDetail}</button>
                  <button
                    onClick={() => alert.id === 1 && setModalOpen(true)}
                    className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
                    style={{ background: PINK }}
                    onMouseEnter={e => (e.currentTarget.style.background = PINK_HOVER)}
                    onMouseLeave={e => (e.currentTarget.style.background = PINK)}>
                    {lx.handle}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recently Resolved */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <div className="text-sm font-semibold text-gray-900">{lx.recentTitle}</div>
          <span className="text-[10px] text-gray-400">{lx.recentSub}</span>
        </div>
        {RECENT_RESOLVED.map((a) => (
          <div key={a.id} className="px-4 py-3 border-b border-gray-50 last:border-b-0 hover:bg-gray-50 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0" style={{ background: PINK }}>
              {a.role.slice(0, 2)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-gray-900">{a.staff}</span>
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded text-white" style={{ background: PINK }}>{a.type[lang]}</span>
                <span className="text-[9px] text-gray-400">{a.id}</span>
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">{a.ward} · {a.shift[lang]}</div>
              <div className="text-[10px] text-emerald-600 font-medium mt-0.5">
                ✅ {lx.resolvedBy} {a.resolvedBy} {lx.resolvedSuffix} · {a.min} {lx.resolvedMin}
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-[10px] text-gray-400">{a.time}</div>
              <div className="text-[10px] font-semibold text-emerald-600 mt-0.5">{lx.resolved}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Emma AI Summary */}
      <div className="rounded-2xl p-5 text-white" style={{ background: 'linear-gradient(135deg, #1a1a2e, #2d2d5e)' }}>
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xl">🤖</span>
          <span className="text-sm font-bold">{lx.aiTitle}</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {AI_SUMMARY.map((s) => (
            <div key={s.label.zh} className="rounded-xl p-3" style={{ background: 'rgba(255,255,255,0.08)' }}>
              <div className="text-[9px] text-gray-400 tracking-wider mb-1.5">{s.label[lang]}</div>
              <div className="text-[10px] text-gray-300 line-through mb-0.5">{s.before[lang]}</div>
              <div className="text-xs font-bold text-white">{s.after[lang]}</div>
              <div className="text-[10px] font-semibold mt-1" style={{ color: '#34d399' }}>{s.save[lang]}</div>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}