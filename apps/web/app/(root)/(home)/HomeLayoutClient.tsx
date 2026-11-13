'use client';

import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';
import Navbar from '@/components/shared/Navbar';
import Sidebar from '@/components/shared/Sidebar';
import { cn } from '@/lib/utils';

export default function HomeLayoutClient({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isMessages = pathname === '/messages' || pathname.startsWith('/messages/');

  return (
    <main className="relative">
      <Navbar />
      <div className="flex">
        <Sidebar />
        <section
          className={cn(
            'flex flex-1 flex-col',
            isMessages
              ? 'h-[calc(100vh-72px)] w-full overflow-hidden p-0 pt-[72px]'
              : 'min-h-screen px-6 pb-6 pt-28 max-md:pb-14 sm:px-14'
          )}
        >
          <div className={cn('w-full', isMessages && 'h-full')}>{children}</div>
        </section>
      </div>
    </main>
  );
}
