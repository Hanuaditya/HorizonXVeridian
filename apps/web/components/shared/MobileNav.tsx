'use client';
import React, { useEffect, useState } from 'react';
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetTrigger
} from '@/components/ui/sheet';
import Image from 'next/image';
import Link from 'next/link';
import { sidebarLinks } from '@/constants';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { MessageSquare } from 'lucide-react';

const MobileNav = () => {
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
        // Offline tolerance
      }
    };
    fetchUnread();
    const interval = setInterval(fetchUnread, 4000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [pathname]);

  return (
    <section className='w-full max-w-[264px]'>
      <Sheet>
        <SheetTrigger asChild>
          <div className="relative cursor-pointer sm:hidden">
            <Image
              src={`/icons/hamburger.svg`}
              width={36}
              height={36}
              alt='mobile-nav'
            />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 size-2.5 rounded-full bg-emerald-400 ring-2 ring-dark-1" />
            )}
          </div>
        </SheetTrigger>
        <SheetContent side={`left`} className='border-none bg-dark-1'>
          <Link className='flex items-center gap-1' href={'/'}>
            <Image
              src={'/icons/logo.svg'}
              width={32}
              height={32}
              alt='logo'
              className='max-sm:size-10'
            />
            <p className='text-[26px] font-extrabold text-white'>Zoom</p>
          </Link>

          <div className='flex h-[calc(100vh-72px)] flex-col justify-between overflow-y-auto'>
            <SheetClose asChild>
              <section className='flex h-full flex-col gap-5 pt-16 text-white'>
                {sidebarLinks.map(item => {
                  const isActive =
                    pathname === item.route ||
                    pathname.startsWith(`${item.route}/`);
                  const isMessages = item.route === '/messages';

                  return (
                    <SheetClose asChild key={item.route}>
                      <Link
                        href={item.route}
                        key={item.label}
                        className={cn(
                          'flex gap-4 items-center p-3.5 rounded-lg w-full max-w-60 transition-all hover:bg-white/5',
                          { 'bg-blue-1 text-white shadow-md': isActive }
                        )}
                      >
                        {isMessages ? (
                          <MessageSquare className="size-5 text-white" />
                        ) : (
                          <Image
                            src={item.imgURL}
                            alt={item.label}
                            width={20}
                            height={20}
                          />
                        )}
                        <p className='font-semibold flex-1'>{item.label}</p>
                        {isMessages && unreadCount > 0 && (
                          <span className="rounded-full bg-emerald-500 px-2 py-0.5 text-[11px] font-bold text-black shadow-sm tabular-nums">
                            {unreadCount}
                          </span>
                        )}
                      </Link>
                    </SheetClose>
                  );
                })}
              </section>
            </SheetClose>
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
};

export default MobileNav;
