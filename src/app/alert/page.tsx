'use client'

import { useState } from 'react'

const PINK = '#f28f9e'
const PINK_HOVER = '#e87a8e'

type FlowStep = 1 | 2 | 3 | 4 | 5
type ChatMsg  = { from: 'system' | 'staff'; text: string }

// ── March 2026 Stats ───────────────────────────────────────────────────
const KPI_CARDS = [
  { label: 'March SL/DSL 總事件', value: '46', unit: '宗',  color: PINK,      sub: 'March 2026 實際' },
  { label: 'Emma AI 自動處理',    value: '38', unit: '宗',  color: '#10b981', sub: '82.6% 自動解決' },
  { label: '平均響應時間',        value: '14', unit: 'min', color: '#f59e0b', sub: '人手處理需 45min' },
  { label: '合規達標率',          value: '98', unit: '%',   color: '#6366f1', sub: 'SWD 人手比率' },
]

const ALERT_TYPES = [
  { icon: '😷', label: 'Sick Leave (SL)',        count: 31, color: PINK,      pct: 67 },
  { icon: '🏥', label: 'DSL（病假 > 3日）',      count: 8,  color: '#f59e0b', pct: 17 },
  { icon: '⚡', label: 'Urgent Leave',            count: 5,  color: '#8b5cf6', pct: 11 },
  { icon: '🕐', label: 'Lateness / Late Report', count: 2,  color: '#6b7280', pct: 4  },
]

const RECENT_RESOLVED = [
  { id: 'SL-2603', type: 'Sick Leave', staff: 'Wong Mei Ling', role: 'RCW', ward: 'F3',        shift: 'N更 21:30–07:00', time: '08:43 AM',  resolvedBy: 'Chan S.M.',     min: 12 },
  { id: 'DSL-2601',type: 'DSL > 3日', staff: 'Lam Yee Ting',  role: 'HW',  ward: 'F1',        shift: 'A更 07:00–15:00', time: '07:15 AM',  resolvedBy: 'Agency PT HW',  min: 27 },
  { id: 'SL-2598', type: 'Sick Leave', staff: 'Yu Yat Sze',    role: 'RN',  ward: 'East Wing', shift: 'A更 07:00–15:00', time: 'Yesterday', resolvedBy: 'Li Wing RN',    min: 8  },
  { id: 'UL-2595', type: 'Urgent',    staff: 'Cheung Ka Man',  role: 'RCW', ward: 'F2',        shift: 'P更 13:30–21:30', time: 'Yesterday', resolvedBy: 'Wong Kai EN',   min: 19 },
]

// ── Alert cards data ───────────────────────────────────────────────────
const ALERTS = [
  { id: 1, title: 'P更人手不足 — F3',      desc: '黃靜賢 (PCW) 標記為 ALERT，P更需要替補人員',          ward: 'F3',            time: '今日 13:30', urgent: true  },
  { id: 2, title: 'OT 超時警報 — 李紹洪', desc: '李紹洪本月已達 160h，繼續排班將超出法定上限',           ward: 'Facility-wide', time: '今日',       urgent: true  },
  { id: 3, title: '合規文件即將到期',       desc: '余逸詩 ACLS 證書將於 30 天內到期，請安排更新',          ward: 'East Wing',     time: '30 天內',    urgent: false },
]

const CANDIDATES = [
  { name: '陳美玲', rank: 'PCW', score: 98, note: '今日放假 · 技能 4.5/5 · 已服務 F3 · TOIL 積分高', badge: '最佳匹配' },
  { name: '林志豪', rank: 'PCW', score: 82, note: 'Day Off · 技能 3.8/5 · 首次 F3',                  badge: '次選' },
]

// ── Resolution Modal (原版保留) ────────────────────────────────────────
function ResolutionModal({ onClose }: { onClose: () => void }) {
  const [step,          setStep]       = useState<FlowStep>(1)
  const [selectedStaff, setSelected]  = useState<string | null>(null)
  const [chatOpen,      setChatOpen]  = useState(false)
  const [chatMsgs,      setChatMsgs]  = useState<ChatMsg[]>([])
  const [chatPhase,     setChatPhase] = useState(0)

  const STEPS: { label: string; sub: string }[] = [
    { label: '收到病假要求', sub: 'Wong Jing Yin 黃靜賢 (CW)\n30/3/2026 P shift · Sick Leave' },
    { label: '觸發警告',     sub: '人手比例 — 不合格\n需要突發補充人手' },
    { label: 'AI 智能配對', sub: '識別到 3 名員工符合\n(Rule-safe verification)' },
    { label: '通知員工',     sub: '推送替更通知到員工 App' },
    { label: '已解決',       sub: '30/3/2026 P shift 已由\nHo Kai Ching (CW) 填補\nRoster synchronized ✓' },
  ]

  function handleAssign(name: string) {
    setSelected(name)
    setChatOpen(true)
    setChatMsgs([{
      from: 'system',
      text: '⚑ 緊急替更通知\n今日P更 (13:30-21:30) 需要人手替更。\n你今日係放假，願意接受今晚更嗎？\n備注：補假+8小時 ＋ 下月優先排假積分',
    }])
    setChatPhase(1)
  }

  function handleStaffReply() {
    if (chatPhase !== 1) return
    setChatMsgs(m => [...m, { from: 'staff', text: '我可以接更 ✓' }])
    setChatPhase(2)
    setTimeout(() => {
      setChatMsgs(m => [...m, {
        from: 'system',
        text: '好的！已幫你更新更表。\n今日P更 (13:30-21:30) 已確認。\n補假+8小時 ＋ 下月優先排假積分 已記錄入系統。',
      }])
      setChatPhase(3)
      setStep(5)
    }, 800)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.45)' }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl mx-4 overflow-hidden flex flex-col" style={{ maxHeight: '92vh' }}>

        {/* Modal header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <div>
            <div className="text-sm font-bold text-gray-900">Resolution Flow: 突發病假</div>
            <div className="text-[10px] text-gray-400 mt-0.5">Wong Jing Yin 黃靜賢 · 30/3/2026 P Shift</div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">✕</button>
        </div>

        <div className="flex flex-1 overflow-hidden">

          {/* Left: Flow steps */}
          <div className="w-64 flex-shrink-0 border-r border-gray-100 p-4 space-y-1 overflow-y-auto">
            {STEPS.map((s, i) => {
              const n      = (i + 1) as FlowStep
              const done   = step > n
              const active = step === n
              return (
                <button key={n} onClick={() => setStep(n)}
                  className="w-full text-left p-3 rounded-xl transition-all"
                  style={{ background: active ? '#fff5f7' : done ? '#f9fafb' : 'transparent' }}>
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0"
                      style={{ background: done ? '#10B981' : active ? PINK : '#e5e7eb', color: done || active ? '#fff' : '#9ca3af' }}>
                      {done ? '✓' : n}
                    </div>
                    <span className="text-[11px] font-semibold"
                      style={{ color: active ? PINK : done ? '#374151' : '#9ca3af' }}>
                      {s.label}
                    </span>
                  </div>
                  {active && (
                    <p className="text-[10px] text-gray-500 mt-1 pl-7 whitespace-pre-line leading-relaxed">{s.sub}</p>
                  )}
                </button>
              )
            })}
          </div>

          {/* Centre: Step content */}
          <div className="flex-1 overflow-y-auto p-5">

            {step === 1 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">收到病假要求</div>
                <div className="bg-red-50 border border-red-100 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-base">🤒</span>
                    <span className="text-sm font-semibold text-red-700">病假申請</span>
                  </div>
                  <div className="space-y-1.5 text-[11px] text-gray-700">
                    <div><span className="text-gray-400">員工：</span>Wong Jing Yin 黃靜賢 (CW)</div>
                    <div><span className="text-gray-400">日期：</span>30/3/2026</div>
                    <div><span className="text-gray-400">更期：</span>P shift (13:30–21:30)</div>
                    <div><span className="text-gray-400">類別：</span>Sick Leave</div>
                  </div>
                </div>
                <button onClick={() => setStep(2)} className="w-full py-2 rounded-xl text-white text-xs font-semibold"
                  style={{ background: PINK }}>下一步 →</button>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">觸發警告</div>
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <span>⚠️</span>
                    <span className="text-xs font-semibold text-amber-800">人手比例 — 不合格</span>
                  </div>
                  <div className="text-[11px] text-amber-700">P更 (13:30–21:30) 缺少 1 名 CW，未達最低人手要求 (1:20)。</div>
                  <div className="text-[11px] font-medium text-amber-800">需要突發補充人手</div>
                </div>
                <button onClick={() => setStep(3)} className="w-full py-2 rounded-xl text-white text-xs font-semibold"
                  style={{ background: PINK }}>啟動 AI 配對 →</button>
              </div>
            )}

            {step === 3 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900 mb-3">AI 智能配對</div>
                {CANDIDATES.map((c) => (
                  <div key={c.name} className="bg-white border border-gray-200 rounded-xl p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
                          style={{ background: PINK }}>{c.name[0]}</div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-gray-900">{c.name}</span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full text-white font-medium"
                              style={{ background: c.score >= 90 ? '#10B981' : '#F59E0B' }}>
                              {c.badge} {c.score}分
                            </span>
                          </div>
                          <div className="text-[10px] text-gray-500 mt-0.5">{c.rank} · {c.note}</div>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button className="px-2.5 py-1 text-[10px] border border-gray-200 rounded-lg hover:bg-gray-50">略過</button>
                        <button onClick={() => handleAssign(c.name)}
                          className="px-2.5 py-1 text-[10px] rounded-lg text-white font-medium"
                          style={{ background: PINK }}
                          onMouseEnter={e => (e.currentTarget.style.background = PINK_HOVER)}
                          onMouseLeave={e => (e.currentTarget.style.background = PINK)}>
                          ✓ Assign
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
                <div className="bg-gray-50 border border-gray-100 rounded-xl p-3 mt-2">
                  <div className="text-[11px] font-semibold text-gray-700 mb-1.5">TOIL 補假積分系統</div>
                  <div className="space-y-1">
                    {['TOIL 補假 +1日 記入 HR 系統', '下月排更優先積分 +10pts', 'AI 下月排更自動考慮積分空間'].map(t => (
                      <div key={t} className="flex items-center gap-1.5 text-[10px] text-gray-600">
                        <span className="text-green-500">•</span>{t}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {step === 4 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">通知員工</div>
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-[11px] text-blue-800 space-y-1">
                  <div>✅ 替更通知已推送至員工 App</div>
                  <div>✅ 等待員工確認回覆</div>
                </div>
              </div>
            )}

            {step === 5 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">已解決 ✓</div>
                <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-1.5 text-[11px] text-green-800">
                  <div className="font-semibold text-green-700">🎉 30/3/2026 P shift 已填補</div>
                  <div>填補員工：Ho Kai Ching (CW)</div>
                  <div>Roster 已同步更新 ✓</div>
                  <div>TOIL +8小時 已記錄入 HR 系統 ✓</div>
                </div>
              </div>
            )}

          </div>

          {/* Right panel: AI Suggestions + Chat */}
          <div className="w-64 flex-shrink-0 border-l border-gray-100 flex flex-col">
            <div className="p-3 border-b border-gray-100">
              <div className="text-[10px] font-bold text-gray-700 uppercase tracking-wider mb-2">AI 建議替更員工</div>
              {CANDIDATES.map((c) => (
                <div key={c.name} className="mb-2 p-2.5 rounded-lg border border-gray-100 bg-gray-50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-semibold text-gray-800">{c.name} ({c.rank})</span>
                    <span className="text-[9px] px-1.5 rounded-full text-white"
                      style={{ background: c.score >= 90 ? '#10B981' : '#F59E0B' }}>
                      {c.badge} {c.score}分
                    </span>
                  </div>
                  <div className="text-[9px] text-gray-500 mb-2 leading-relaxed">{c.note}</div>
                  <div className="flex gap-1.5">
                    <button onClick={() => { setStep(3); handleAssign(c.name) }}
                      className="flex-1 py-1 text-[9px] rounded-lg text-white font-medium"
                      style={{ background: PINK }}>
                      ✓ 發送 WhatsApp
                    </button>
                    <button className="px-2 py-1 text-[9px] border border-gray-200 rounded-lg hover:bg-white">略過</button>
                  </div>
                </div>
              ))}
            </div>

            {chatOpen && (
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="px-3 py-2 border-b border-gray-100 flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0"
                    style={{ background: PINK }}>{selectedStaff?.[0]}</div>
                  <div>
                    <div className="text-[10px] font-semibold text-gray-800">{selectedStaff}</div>
                    <div className="text-[8px] text-green-500">● 線上</div>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
                  {chatMsgs.map((m, i) => (
                    <div key={i} className={`flex ${m.from === 'staff' ? 'justify-end' : 'justify-start'}`}>
                      <div className="max-w-[85%] px-2.5 py-1.5 rounded-xl text-[10px] leading-relaxed whitespace-pre-line"
                        style={{
                          background: m.from === 'system' ? '#f3f4f6' : PINK,
                          color:      m.from === 'system' ? '#374151' : '#fff',
                          borderRadius: m.from === 'system' ? '4px 12px 12px 12px' : '12px 4px 12px 12px',
                        }}>
                        {m.text}
                      </div>
                    </div>
                  ))}
                </div>
                {chatPhase === 1 && (
                  <div className="p-2 border-t border-gray-100">
                    <button onClick={handleStaffReply}
                      className="w-full py-1.5 text-[10px] rounded-lg text-white font-medium"
                      style={{ background: '#10B981' }}>
                      模擬員工回覆：我可以接更 ✓
                    </button>
                  </div>
                )}
                {chatPhase === 3 && (
                  <div className="p-2 border-t border-gray-100">
                    <div className="text-[9px] text-center text-green-600 font-medium">✓ 替更已確認，Roster 已同步</div>
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

// ── Main Page ──────────────────────────────────────────────────────────
export default function AlertPage() {
  const [modalOpen, setModalOpen] = useState(false)

  return (
    <div className="p-5 space-y-5">
      {modalOpen && <ResolutionModal onClose={() => setModalOpen(false)} />}

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Alert 警報中心</h1>
          <p className="text-xs text-gray-500 mt-0.5">3 個待處理警報 · March 2026 實際數字</p>
        </div>
        <button
          className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
          style={{ background: PINK }}
          onMouseEnter={e => (e.currentTarget.style.background = PINK_HOVER)}
          onMouseLeave={e => (e.currentTarget.style.background = PINK)}>
          + New Request
        </button>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-4 gap-3">
        {KPI_CARDS.map((k) => (
          <div key={k.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{k.label}</div>
            <div className="flex items-end gap-0.5">
              <span className="text-[28px] font-bold tabular-nums leading-none" style={{ color: k.color }}>{k.value}</span>
              <span className="text-xs text-gray-400 mb-1">{k.unit}</span>
            </div>
            <div className="text-[10px] text-gray-400 mt-1">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* ── March SL/DSL 分佈 ── */}
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-semibold text-gray-900">March 2026 SL/DSL 事件分佈</div>
          <span className="text-xs font-bold px-2.5 py-1 rounded-full"
            style={{ background: '#fce8f3', color: PINK }}>共 46 宗</span>
        </div>
        <div className="space-y-2.5">
          {ALERT_TYPES.map((a) => (
            <div key={a.label} className="flex items-center gap-3">
              <span className="text-base w-6 text-center flex-shrink-0">{a.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-medium text-gray-700">{a.label}</span>
                  <span className="text-xs font-bold tabular-nums" style={{ color: a.color }}>{a.count} 宗</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${a.pct}%`, background: a.color }} />
                </div>
              </div>
              <span className="text-[10px] text-gray-400 w-8 text-right flex-shrink-0">{a.pct}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── 待處理 Alert Cards ── */}
      <div>
        <div className="text-sm font-semibold text-gray-900 mb-3">待處理警報</div>
        <div className="space-y-3">
          {ALERTS.map((alert) => (
            <div key={alert.id} className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 mt-0.5"
                    style={{ background: alert.urgent ? '#FFE4E6' : '#FEF3C7' }}>
                    {alert.urgent ? '🚨' : '⚠️'}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-gray-900">{alert.title}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{alert.desc}</div>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{alert.ward}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{alert.time}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full text-white font-medium"
                        style={{ background: alert.urgent ? PINK : '#F59E0B' }}>
                        {alert.urgent ? '緊急' : '一般'}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <button className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50">忽略</button>
                  <button
                    onClick={() => alert.id === 1 && setModalOpen(true)}
                    className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
                    style={{ background: PINK }}
                    onMouseEnter={e => (e.currentTarget.style.background = PINK_HOVER)}
                    onMouseLeave={e => (e.currentTarget.style.background = PINK)}>
                    處理
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── 近期已解決紀錄 ── */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <div className="text-sm font-semibold text-gray-900">近期已解決紀錄</div>
          <span className="text-[10px] text-gray-400">March 2026 · 最新 4 宗</span>
        </div>
        {RECENT_RESOLVED.map((a) => (
          <div key={a.id} className="px-4 py-3 border-b border-gray-50 last:border-b-0 hover:bg-gray-50 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
              style={{ background: PINK }}>
              {a.role.slice(0, 2)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-gray-900">{a.staff}</span>
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded text-white"
                  style={{ background: PINK }}>{a.type}</span>
                <span className="text-[9px] text-gray-400">{a.id}</span>
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">{a.ward} · {a.shift}</div>
              <div className="text-[10px] text-emerald-600 font-medium mt-0.5">
                ✓ 由 {a.resolvedBy} 替更 · {a.min}min 內解決
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-[10px] text-gray-400">{a.time}</div>
              <div className="text-[10px] font-semibold text-emerald-600 mt-0.5">已解決</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Emma AI 效益摘要 ── */}
      <div className="rounded-2xl p-5 text-white" style={{ background: 'linear-gradient(135deg, #1a1a2e, #2d2d5e)' }}>
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xl">✦</span>
          <span className="text-sm font-bold">Emma AI · March 2026 Alert 效益</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: '平均響應時間', before: '45 min',   after: '14 min',    save: '↓ 69%' },
            { label: '人手自動配對', before: '人手搜尋', after: 'AI 即時推薦', save: '節省 31h/月' },
            { label: 'SWD 合規達標', before: '人手監察', after: 'AI 即時警示', save: '98% 達標率' },
          ].map((s) => (
            <div key={s.label} className="rounded-xl p-3" style={{ background: 'rgba(255,255,255,0.08)' }}>
              <div className="text-[9px] text-gray-400 tracking-wider mb-1.5">{s.label}</div>
              <div className="text-[10px] text-gray-300 line-through mb-0.5">{s.before}</div>
              <div className="text-xs font-bold text-white">{s.after}</div>
              <div className="text-[10px] font-semibold mt-1" style={{ color: '#34d399' }}>{s.save}</div>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}