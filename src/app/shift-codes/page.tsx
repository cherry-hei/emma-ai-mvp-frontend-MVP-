'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { ShiftDef } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

export default function ShiftCodesPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'
  const [defs, setDefs] = useState<ShiftDef[]>([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'working' | 'leave'>('all')
  const [loading, setLoading] = useState(true)

  const T = {
    title: isZH ? '更期代號字典' : 'Shift Code Dictionary',
    subtitle: isZH ? '機構所有更期代號及定義' : 'All shift codes and definitions for this organisation',
    search: isZH ? '搜尋代號…' : 'Search codes…',
    all: isZH ? '全部' : 'All',
    working: isZH ? '工作更' : 'Working',
    leave: isZH ? '假期/休息' : 'Leave/Rest',
    code: isZH ? '代號' : 'Code',
    label: isZH ? '名稱' : 'Label',
    time: isZH ? '時間' : 'Time',
    hours: isZH ? '時數' : 'Hours',
    type: isZH ? '類型' : 'Type',
    cross: isZH ? '跨日' : 'Cross-midnight',
    total: isZH ? '共' : 'Total:',
    codes: isZH ? '個代號' : ' codes',
    workingLabel: isZH ? '工作' : 'Working',
    restLabel: isZH ? '休息' : 'Rest',
    yes: isZH ? '是' : 'Yes',
    no: isZH ? '否' : 'No',
  }

  useEffect(() => {
    api.shiftDefinitions()
      .then(setDefs)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = defs.filter(d => {
    if (filter === 'working' && !d.is_working) return false
    if (filter === 'leave' && d.is_working) return false
    if (search) {
      const q = search.toLowerCase()
      return d.shift_type.toLowerCase().includes(q) || (d.label || '').toLowerCase().includes(q)
    }
    return true
  })

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl" style={{ background: '#fce8f3' }}>📖</div>
        <div>
          <h1 className="text-xl font-bold">{T.title}</h1>
          <p className="text-xs text-gray-500">{T.subtitle}</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <input type="text" value={search} onChange={e => setSearch(e.target.value)}
          placeholder={T.search}
          className="px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 w-56" />
        <div className="flex gap-1">
          {(['all', 'working', 'leave'] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium border transition-all"
              style={{
                background: filter === f ? PINK : '#fff',
                color: filter === f ? '#fff' : '#6b7280',
                borderColor: filter === f ? PINK : '#e5e7eb',
              }}>
              {f === 'all' ? T.all : f === 'working' ? T.working : T.leave}
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-400 ml-auto">{T.total} {filtered.length}{T.codes}</span>
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading...</div>
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded-xl">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-2.5 text-[10px] font-bold text-gray-500 uppercase">{T.code}</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-bold text-gray-500 uppercase">{T.label}</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-bold text-gray-500 uppercase">{T.time}</th>
                <th className="text-center px-4 py-2.5 text-[10px] font-bold text-gray-500 uppercase">{T.hours}</th>
                <th className="text-center px-4 py-2.5 text-[10px] font-bold text-gray-500 uppercase">{T.type}</th>
                <th className="text-center px-4 py-2.5 text-[10px] font-bold text-gray-500 uppercase">{T.cross}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(d => (
                <tr key={d.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2">
                    <span className="px-2 py-0.5 rounded text-xs font-bold"
                      style={{ background: d.is_working ? '#dbeafe' : '#f1f5f9', color: d.is_working ? '#1e40af' : '#64748b' }}>
                      {d.shift_type}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-700">{d.label || '—'}</td>
                  <td className="px-4 py-2 text-xs text-gray-600">
                    {d.start_time && d.end_time ? `${d.start_time.slice(0,5)} - ${d.end_time.slice(0,5)}` : '—'}
                  </td>
                  <td className="px-4 py-2 text-center text-xs font-medium">
                    {d.paid_minutes ? (d.paid_minutes / 60).toFixed(1) : '—'}
                  </td>
                  <td className="px-4 py-2 text-center">
                    <span className="text-[10px] px-2 py-0.5 rounded-full"
                      style={{ background: d.is_working ? '#dcfce7' : '#fef3c7', color: d.is_working ? '#166534' : '#92400e' }}>
                      {d.is_working ? T.workingLabel : T.restLabel}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-center text-[10px] text-gray-500">
                    {d.cross_midnight ? T.yes : T.no}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
