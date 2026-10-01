import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Emma AI – Care-home scheduling',
  description: 'Care-home scheduling and compliance workspace',
  manifest: '/manifest.json',
  appleWebApp: { capable: true, title: 'Emma AI', statusBarStyle: 'default' },
  icons: { icon: '/emma-mark.png', apple: '/emma-mark.png' },
}

export const viewport: Viewport = {
  themeColor: '#E8187A',
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
