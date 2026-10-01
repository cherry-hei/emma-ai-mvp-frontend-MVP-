'use client'

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { useAuth } from '@/components/layout/AuthContext'

export type TextSize = 'standard' | 'comfortable' | 'large'
export type DisplayTheme = 'light' | 'dark'
type DisplayPrefs = { textSize: TextSize; theme: DisplayTheme }
type DisplayCtx = DisplayPrefs & {
  setTextSize: (size: TextSize) => void
  setTheme: (theme: DisplayTheme) => void
}
const DEFAULT: DisplayPrefs = { textSize: 'standard', theme: 'light' }
const Context = createContext<DisplayCtx>({ ...DEFAULT, setTextSize: () => {}, setTheme: () => {} })
const keyFor = (id: string) => `emma_display_v1:${id}`

function read(id: string): DisplayPrefs {
  try {
    const raw = JSON.parse(window.localStorage.getItem(keyFor(id)) || '{}') as Partial<DisplayPrefs>
    return {
      textSize: ['standard', 'comfortable', 'large'].includes(raw.textSize || '') ? raw.textSize! : 'standard',
      theme: raw.theme === 'dark' ? 'dark' : 'light',
    }
  } catch { return DEFAULT }
}

export function DisplayPreferencesProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const id = user?.userId
  const [prefs, setPrefs] = useState<DisplayPrefs>(DEFAULT)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)

  useEffect(() => {
    setPrefs(id ? read(id) : DEFAULT)
    setLoadedFor(id || null)
  }, [id])
  useEffect(() => {
    if (typeof document === 'undefined' || !id || loadedFor !== id) return
    const root = document.documentElement
    root.dataset.emmaTextSize = prefs.textSize
    root.classList.toggle('dark', prefs.theme === 'dark')
    root.style.fontSize = ({ standard: '16px', comfortable: '18px', large: '20px' })[prefs.textSize]
    window.localStorage.setItem(keyFor(id), JSON.stringify(prefs))
  }, [id, loadedFor, prefs])

  const setTextSize = useCallback((textSize: TextSize) => setPrefs(p => ({ ...p, textSize })), [])
  const setTheme = useCallback((theme: DisplayTheme) => setPrefs(p => ({ ...p, theme })), [])
  return <Context.Provider value={{ ...prefs, setTextSize, setTheme }}>{children}</Context.Provider>
}

export function useDisplayPreferences() { return useContext(Context) }
