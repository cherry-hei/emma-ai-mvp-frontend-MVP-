import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Emma AI – Medical Intelligence',
  description: 'AI-powered roster management for RCHE',
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
      <body className={inter.className} suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
