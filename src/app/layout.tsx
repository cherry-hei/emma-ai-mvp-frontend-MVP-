import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { LanguageProvider } from '@/components/layout/LanguageContext'
import { AuthProvider } from '@/components/layout/AuthContext'
import { AppShell } from '@/components/layout/AppShell'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Emma AI – Medical Intelligence',
  description: 'AI-powered roster management for RCHE',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      {/* suppressHydrationWarning: browser extensions (e.g. Bitdefender) inject
          attributes like `bis_register` / `__processed_*` onto <body> before React
          hydrates. Scoped to <body>'s own attributes only — app-tree mismatches still warn. */}
      <body className={inter.className} suppressHydrationWarning>
        <LanguageProvider>
          <AuthProvider>
            <AppShell>{children}</AppShell>
          </AuthProvider>
        </LanguageProvider>
      </body>
    </html>
  )
}