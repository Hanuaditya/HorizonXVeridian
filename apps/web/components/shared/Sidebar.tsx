'use client';

import { sidebarLinks } from '@/constants';
import { cn } from '@/lib/utils';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import React, { useEffect, useState } from 'react';
import { MessageSquare } from 'lucide-react';

const Sidebar = () => {
  const pathname = usePathname();
  const [unreadCount, setUnreadCount] = useState<number>(0);

  useEffect(() => {
    let mounted = true;
    const fetchUnread = async () => {
      try {
        const res = await fetch('/api/workos/messages/unread');
        if (res.ok) {
          const data = await res.json();
          if (mounted) {
            setUnreadCount(Number(data.unread_total) || 0);
          }
        }
      } catch {
        // Offline / idle tolerance
      }
    };

    fetchUnread();
    const interval = setInterval(fetchUnread, 3500);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [pathname]);

  return (
    <section className='sticky left-0 top-0 flex h-screen w-fit flex-col justify-between bg-dark-1 border-r border-white/[0.08] p-6 pt-28 text-white max-sm:hidden lg:w-[264px]'>
      <div className='flex flex-1 flex-col gap-5'>
        {sidebarLinks.map(item => {
          const isActive =
            pathname === item.route || pathname.startsWith(`${item.route}/`);
          const isMessages = item.route === '/messages';

          return (
            <Link
              href={item.route}
              key={item.label}
              className={cn(
                'flex gap-4 items-center p-3.5 rounded-lg justify-start transition-all hover:bg-white/5',
                { 'bg-blue-1 text-white shadow-md': isActive }
              )}
            >
              {isMessages ? (
                <div className="relative flex items-center justify-center">
                  <MessageSquare className="size-6 text-white" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1.5 size-2.5 rounded-full bg-emerald-400 ring-2 ring-dark-1 lg:hidden" />
                  )}
                </div>
              ) : (
                <Image
                  src={item.imgURL}
                  alt={item.label}
                  width={24}
                  height={24}
                />
              )}
              <p className='text-base font-semibold max-lg:hidden flex-1'>
                {item.label}
              </p>
              {isMessages && unreadCount > 0 && (
                <span className="ml-auto hidden rounded-full bg-emerald-500 px-2 py-0.5 text-[11px] font-bold text-black shadow-sm tabular-nums lg:inline-flex items-center justify-center">
                  {unreadCount}
                </span>
              )}
            </Link>
          );
        })}
      </div>
    </section>
  );
};

export default Sidebar;
