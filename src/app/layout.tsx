import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopNav } from '@/components/layout/TopNav'
import { LanguageProvider } from '@/components/layout/LanguageContext'

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
          <div className="flex h-screen overflow-hidden bg-gray-50">
            <Sidebar />
            <div className="flex-1 flex flex-col overflow-hidden">
              <TopNav />
              <main className="flex-1 overflow-y-auto">
                {children}
              </main>
            </div>
          </div>
        </LanguageProvider>
      </body>
    </html>
  )
}