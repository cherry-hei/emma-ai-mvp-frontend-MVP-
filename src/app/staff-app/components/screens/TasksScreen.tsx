'use client'

import { useState } from 'react'

interface TaskItem {
  id: number
  title: string
  time: string
  status: 'pending' | 'done'
  priority?: 'high' | 'normal'
}

const initialTasks: TaskItem[] = [
  { id: 1, title: 'Med Checking', time: '08:00', status: 'pending', priority: 'high' },
  { id: 2, title: 'ICP Review', time: '10:30', status: 'pending' },
  { id: 3, title: 'FU Chat', time: '14:00', status: 'done' },
  { id: 4, title: 'Wound Care Follow-up', time: '16:30', status: 'pending' },
]

export default function TasksScreen() {
  const [tasks, setTasks] = useState(initialTasks)

  const toggleTask = (id: number) => {
    setTasks((prev) =>
      prev.map((task) =>
        task.id === id
          ? { ...task, status: task.status === 'done' ? 'pending' : 'done' }
          : task
      )
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">今日工作清單</h3>
        <p className="mt-1 text-sm text-gray-500">點擊可切換完成狀態</p>
      </div>

      {tasks.map((task) => (
        <button
          key={task.id}
          onClick={() => toggleTask(task.id)}
          className="flex w-full items-center gap-3 rounded-2xl border border-gray-200 bg-white p-4 text-left shadow-sm transition hover:border-[#f3c7cf] hover:bg-[#fffafb]"
        >
          <div
            className={`flex h-6 w-6 items-center justify-center rounded-full border ${
              task.status === 'done'
                ? 'border-[#e87a8e] bg-[#e87a8e] text-white'
                : 'border-gray-300 bg-white text-transparent'
            }`}
          >
            ✓
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className={`text-sm font-medium ${task.status === 'done' ? 'text-gray-400 line-through' : 'text-gray-900'}`}>
                {task.title}
              </p>
              {task.priority === 'high' && (
                <span className="rounded-full bg-[#fdecef] px-2 py-0.5 text-[10px] font-semibold text-[#e87a8e]">
                  HIGH
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-400">{task.time}</p>
          </div>
        </button>
      ))}
    </div>
  )
}