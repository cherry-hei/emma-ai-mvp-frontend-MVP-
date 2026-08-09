'use client'
import { LanguageProvider } from '@/components/layout/LanguageContext'
import { AuthProvider } from '@/components/layout/AuthContext'
import { AppShell } from '@/components/layout/AppShell'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <AuthProvider>
        <AppShell>{children}</AppShell>
      </AuthProvider>
    </LanguageProvider>
  )
}
