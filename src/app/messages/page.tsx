'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'

const PINK = '#E8187A'
const STORAGE_KEY = 'emma_messages'

// Demo staff list (in production this comes from API)
const DEMO_STAFF = [
  { id: 's1', name: '陳小明', name_en: 'Chan Siu Ming', rank: 'RN', avatar: '👨‍⚕️' },
  { id: 's2', name: '李美玲', name_en: 'Lee Mei Ling', rank: 'HW', avatar: '👩‍⚕️' },
  { id: 's3', name: '王大偉', name_en: 'Wong Tai Wai', rank: 'CW', avatar: '👨' },
  { id: 's4', name: '張惠芳', name_en: 'Cheung Wai Fong', rank: 'CW', avatar: '👩' },
  { id: 's5', name: '劉志強', name_en: 'Lau Chi Keung', rank: 'HCA', avatar: '👨' },
  { id: 's6', name: '黃麗珍', name_en: 'Wong Lai Chun', rank: 'EN', avatar: '👩‍⚕️' },
]

interface Message {
  id: string
  threadId: string
  from: 'admin' | 'staff'
  text: string
  timestamp: string
  context?: string // e.g. "關於你 10月5日嘅 AL request"
}

interface Thread {
  id: string
  staffId: string
  staffName: string
  staffNameEn: string
  staffRank: string
  staffAvatar: string
  lastMessage: string
  lastTimestamp: string
  unreadCount: number
  context?: string
}

function getThreads(): Thread[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY + '_threads')
    return stored ? JSON.parse(stored) : []
  } catch { return [] }
}

function getMessages(threadId: string): Message[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY + '_' + threadId)
    return stored ? JSON.parse(stored) : []
  } catch { return [] }
}

function saveThreads(threads: Thread[]) {
  localStorage.setItem(STORAGE_KEY + '_threads', JSON.stringify(threads))
}

function saveMessages(threadId: string, messages: Message[]) {
  localStorage.setItem(STORAGE_KEY + '_' + threadId, JSON.stringify(messages))
}

export default function MessagesPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const isZH = lang === 'zh'

  const [threads, setThreads] = useState<Thread[]>([])
  const [activeThread, setActiveThread] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [showNewThread, setShowNewThread] = useState(false)
  const [newContext, setNewContext] = useState('')

  const L = useMemo(() => ({
    title: isZH ? '訊息中心' : 'Messages',
    subtitle: isZH ? '與員工溝通 · 假期協商 · 更表通知' : 'Staff communication · Leave negotiation · Roster notifications',
    new_msg: isZH ? '+ 新訊息' : '+ New Message',
    no_threads: isZH ? '暫無對話記錄' : 'No conversations yet',
    no_threads_sub: isZH ? '點擊「+ 新訊息」開始與員工溝通' : 'Click "+ New Message" to start communicating with staff',
    type_msg: isZH ? '輸入訊息…' : 'Type a message…',
    send: isZH ? '發送' : 'Send',
    select_staff: isZH ? '選擇員工' : 'Select Staff',
    context_ph: isZH ? '關於什麼？（可選）例如：關於你10月5日嘅AL request' : 'Context (optional) e.g. About your AL request on Oct 5',
    start: isZH ? '開始對話' : 'Start Conversation',
    cancel: isZH ? '取消' : 'Cancel',
    back: isZH ? '← 返回' : '← Back',
    demo_note: isZH ? '💡 Demo 模式：訊息儲存在本機。正式版將由 Kien 接入後端 API。' : '💡 Demo mode: Messages stored locally. Production will use backend API.',
    admin: isZH ? '管理員' : 'Admin',
  }), [isZH])

  useEffect(() => { setThreads(getThreads()) }, [])

  const openThread = useCallback((threadId: string) => {
    setActiveThread(threadId)
    setMessages(getMessages(threadId))
    // Mark as read
    setThreads(prev => {
      const updated = prev.map(t => t.id === threadId ? { ...t, unreadCount: 0 } : t)
      saveThreads(updated)
      return updated
    })
  }, [])

  const sendMessage = useCallback(() => {
    if (!input.trim() || !activeThread) return
    const msg: Message = {
      id: `msg-${Date.now()}`,
      threadId: activeThread,
      from: 'admin',
      text: input.trim(),
      timestamp: new Date().toISOString(),
    }
    const updated = [...messages, msg]
    setMessages(updated)
    saveMessages(activeThread, updated)
    setInput('')

    // Update thread last message
    setThreads(prev => {
      const newThreads = prev.map(t => t.id === activeThread
        ? { ...t, lastMessage: msg.text, lastTimestamp: msg.timestamp }
        : t)
      saveThreads(newThreads)
      return newThreads
    })

    // Simulate staff reply after 2 seconds
    setTimeout(() => {
      const replies = isZH
        ? ['收到，多謝通知', '好的，我明白了', '了解，我會跟進', '謝謝院長']
        : ['Received, thanks for letting me know', 'OK, understood', 'Got it, I will follow up', 'Thank you']
      const reply: Message = {
        id: `msg-${Date.now()}-reply`,
        threadId: activeThread,
        from: 'staff',
        text: replies[Math.floor(Math.random() * replies.length)],
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => {
        const newMsgs = [...prev, reply]
        saveMessages(activeThread, newMsgs)
        return newMsgs
      })
      setThreads(prev => {
        const newThreads = prev.map(t => t.id === activeThread
          ? { ...t, lastMessage: reply.text, lastTimestamp: reply.timestamp }
          : t)
        saveThreads(newThreads)
        return newThreads
      })
    }, 2000)
  }, [input, activeThread, messages, isZH])

  const createThread = useCallback((staffId: string) => {
    const staff = DEMO_STAFF.find(s => s.id === staffId)
    if (!staff) return
    const thread: Thread = {
      id: `thread-${Date.now()}`,
      staffId: staff.id,
      staffName: staff.name,
      staffNameEn: staff.name_en,
      staffRank: staff.rank,
      staffAvatar: staff.avatar,
      lastMessage: newContext || (isZH ? '新對話' : 'New conversation'),
      lastTimestamp: new Date().toISOString(),
      unreadCount: 0,
      context: newContext || undefined,
    }
    const updated = [thread, ...threads]
    setThreads(updated)
    saveThreads(updated)
    setShowNewThread(false)
    setNewContext('')

    // If context provided, add as first system message
    if (newContext) {
      const msg: Message = {
        id: `msg-${Date.now()}-ctx`,
        threadId: thread.id,
        from: 'admin',
        text: newContext,
        timestamp: new Date().toISOString(),
        context: newContext,
      }
      saveMessages(thread.id, [msg])
    }

    openThread(thread.id)
  }, [threads, newContext, isZH, openThread])

  const formatTime = (iso: string) => {
    const d = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - d.getTime()
    if (diff < 60000) return isZH ? '剛剛' : 'Just now'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m`
    if (diff < 86400000) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    return d.toLocaleDateString(isZH ? 'zh-HK' : 'en-GB', { month: 'short', day: 'numeric' })
  }

  // Thread detail view
  if (activeThread) {
    const thread = threads.find(t => t.id === activeThread)
    return (
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-3 bg-white flex-shrink-0">
          <button onClick={() => setActiveThread(null)}
            className="text-xs text-gray-500 hover:text-gray-700 md:hidden">
            {L.back}
          </button>
          <button onClick={() => setActiveThread(null)}
            className="text-xs text-gray-500 hover:text-gray-700 hidden md:block">
            {L.back}
          </button>
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-base bg-pink-50">
            {thread?.staffAvatar}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-gray-800 truncate">
              {isZH ? thread?.staffName : thread?.staffNameEn}
            </div>
            <div className="text-[10px] text-gray-400">{thread?.staffRank}</div>
          </div>
          {thread?.context && (
            <div className="text-[9px] px-2 py-1 rounded-full bg-pink-50 text-pink-600 hidden sm:block">
              {thread.context}
            </div>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50">
          {messages.length === 0 && (
            <div className="text-center text-[11px] text-gray-400 py-8">
              {isZH ? '開始輸入訊息…' : 'Start typing a message…'}
            </div>
          )}
          {messages.map(msg => (
            <div key={msg.id} className={`flex ${msg.from === 'admin' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[75%] rounded-2xl px-3.5 py-2.5 ${
                msg.from === 'admin'
                  ? 'bg-pink-500 text-white rounded-br-md'
                  : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md'
              }`}>
                <div className="text-[12px] leading-relaxed">{msg.text}</div>
                <div className={`text-[9px] mt-1 ${msg.from === 'admin' ? 'text-pink-200' : 'text-gray-400'}`}>
                  {formatTime(msg.timestamp)}
                  {msg.from === 'admin' && <span className="ml-1">✓✓</span>}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-gray-100 bg-white flex gap-2 flex-shrink-0">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
            placeholder={L.type_msg}
            className="flex-1 px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-1 focus:ring-pink-200 bg-gray-50"
          />
          <button onClick={sendMessage} disabled={!input.trim()}
            className="px-4 py-2.5 rounded-xl text-xs font-semibold text-white disabled:opacity-40 transition-opacity"
            style={{ background: PINK }}>
            {L.send}
          </button>
        </div>
      </div>
    )
  }

  // Thread list view
  return (
    <div className="p-4 md:p-5 space-y-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{L.title}</h1>
          <p className="text-[10px] text-gray-400 mt-0.5">{L.subtitle}</p>
        </div>
        <button onClick={() => setShowNewThread(true)}
          className="px-3 py-2 rounded-xl text-xs font-semibold text-white"
          style={{ background: PINK }}>
          {L.new_msg}
        </button>
      </div>

      {/* Demo note */}
      <div className="text-[10px] px-3 py-2 rounded-lg border border-amber-200 bg-amber-50 text-amber-700 flex-shrink-0">
        {L.demo_note}
      </div>

      {/* New thread dialog */}
      {showNewThread && (
        <div className="border border-pink-200 rounded-xl p-4 bg-pink-50/50 space-y-3 flex-shrink-0">
          <div className="text-xs font-semibold text-gray-700">{L.select_staff}</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {DEMO_STAFF.map(s => (
              <button key={s.id} onClick={() => createThread(s.id)}
                className="flex items-center gap-2 p-2.5 rounded-lg border border-gray-200 bg-white hover:border-pink-300 hover:bg-pink-50 transition-colors text-left">
                <span className="text-base">{s.avatar}</span>
                <div className="min-w-0">
                  <div className="text-[11px] font-medium text-gray-800 truncate">
                    {isZH ? s.name : s.name_en}
                  </div>
                  <div className="text-[9px] text-gray-400">{s.rank}</div>
                </div>
              </button>
            ))}
          </div>
          <input
            type="text"
            value={newContext}
            onChange={e => setNewContext(e.target.value)}
            placeholder={L.context_ph}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-[11px] bg-white"
          />
          <button onClick={() => setShowNewThread(false)}
            className="text-[10px] text-gray-500 hover:text-gray-700">
            {L.cancel}
          </button>
        </div>
      )}

      {/* Thread list */}
      <div className="flex-1 overflow-y-auto space-y-1">
        {threads.length === 0 && !showNewThread ? (
          <div className="text-center py-12">
            <div className="text-3xl mb-3">💬</div>
            <div className="text-sm text-gray-500">{L.no_threads}</div>
            <div className="text-[10px] text-gray-400 mt-1">{L.no_threads_sub}</div>
          </div>
        ) : (
          threads.map(thread => (
            <button key={thread.id} onClick={() => openThread(thread.id)}
              className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-gray-50 transition-colors text-left border border-transparent hover:border-gray-200">
              <div className="w-10 h-10 rounded-full flex items-center justify-center text-lg bg-pink-50 flex-shrink-0">
                {thread.staffAvatar}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-800 truncate">
                    {isZH ? thread.staffName : thread.staffNameEn}
                  </span>
                  <span className="text-[9px] text-gray-400 flex-shrink-0 ml-2">
                    {formatTime(thread.lastTimestamp)}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[11px] text-gray-500 truncate">{thread.lastMessage}</span>
                  {thread.unreadCount > 0 && (
                    <span className="text-[8px] text-white rounded-full w-4 h-4 flex items-center justify-center flex-shrink-0 ml-2"
                      style={{ background: PINK }}>
                      {thread.unreadCount}
                    </span>
                  )}
                </div>
                {thread.context && (
                  <div className="text-[9px] text-pink-500 mt-0.5 truncate">{thread.context}</div>
                )}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  )
}
