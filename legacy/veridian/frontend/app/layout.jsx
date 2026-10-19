import './globals.css'

export const metadata = {
  title: 'Veridian WorkOS — AI Chief of Staff',
  description: 'Enterprise AI orchestration — meeting transcript to Jira + Slack in real-time.',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="h-screen overflow-hidden grid-bg">
        {children}
      </body>
    </html>
  )
}
