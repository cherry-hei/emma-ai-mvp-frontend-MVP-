import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { LanguageProvider } from '@/components/layout/LanguageContext'
import { AuthProvider } from '@/components/layout/AuthContext'
import { AppShell } from '@/components/layout/AppShell'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Emma AI – Medical Intelligence',
  description: 'AI-powered roster management for RCHE',
  // The staff app is installed to a phone home screen (spec SA.4b); the manifest
  // and theme colour are what make that offer appear.
  manifest: '/manifest.json',
  appleWebApp: { capable: true, title: 'Emma AI', statusBarStyle: 'default' },
  icons: { icon: '/icons/emma-192.png', apple: '/icons/emma-192.png' },
}

export const viewport: Viewport = {
  themeColor: '#e87a8e',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      {/* suppressHydrationWarning: browser extensions (e.g. Bitdefender) inject
          attributes like `bis_register` / `__processed_*` onto <body> before React
          hydrates. Scoped to <body>'s own attributes only - app-tree mismatches still warn. */}
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