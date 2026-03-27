export default function AlertPage() {
  return (
    <div className="p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Alert 警報中心</h1>
          <p className="text-xs text-gray-500 mt-0.5">3 個待處理警報</p>
        </div>
        <button
          className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
          style={{ background: '#E8187A' }}
        >
          + New Request
        </button>
      </div>

      {/* Alert cards */}
      <div className="space-y-3">
        {ALERTS.map((alert) => (
          <div key={alert.id} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 mt-0.5"
                  style={{ background: alert.urgent ? '#FFE4E6' : '#FEF3C7' }}
                >
                  {alert.urgent ? '🚨' : '⚠️'}
                </div>
                <div>
                  <div className="text-sm font-semibold text-gray-900">{alert.title}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{alert.desc}</div>
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{alert.ward}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{alert.time}</span>
                    <span
                      className="text-[10px] px-2 py-0.5 rounded-full text-white font-medium"
                      style={{ background: alert.urgent ? '#E8187A' : '#F59E0B' }}
                    >
                      {alert.urgent ? '緊急' : '一般'}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex gap-2 flex-shrink-0">
                <button className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50">忽略</button>
                <button
                  className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
                  style={{ background: '#E8187A' }}
                >
                  處理
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const ALERTS = [
  {
    id: 1,
    title: '夜更人手不足 — F3',
    desc: '黃靜賢 (PCW) 標記為 ALERT，F3 夜更需要替補人員',
    ward: 'F3 Night Unit',
    time: '今晚 23:00',
    urgent: true,
  },
  {
    id: 2,
    title: 'OT 超時警報 — 李紹洪',
    desc: '李紹洪本月已達 160h，繼續排班將超出法定上限',
    ward: 'Facility-wide',
    time: '今日',
    urgent: true,
  },
  {
    id: 3,
    title: '合規文件即將到期',
    desc: '余逸詩 ACLS 證書將於 30 天內到期，請安排更新',
    ward: 'East Wing',
    time: '30 天內',
    urgent: false,
  },
]