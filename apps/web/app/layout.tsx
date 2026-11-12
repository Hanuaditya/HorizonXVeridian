import { ReactNode } from 'react';
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';

import '@stream-io/video-react-sdk/dist/css/styles.css';
import 'react-datepicker/dist/react-datepicker.css';
import './globals.css';

import { Providers } from '../providers/providers';
import { AppAuthProvider } from '../providers/AuthBridge';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Horizon Veridian',
  description: 'Sovereign Indic Voice & Agentic WorkOS Platform',
  icons: {
    icon: '/icons/logo.svg',
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <AppAuthProvider>
        <body className={`${inter.className} bg-dark-2`}>
          <Providers>{children}</Providers>
        </body>
      </AppAuthProvider>
    </html>
  );
}
