import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { NextResponse } from 'next/server';

const isProtectedRoute = createRouteMatcher([
  '/',
  '/upcoming(.*)',
  '/previous(.*)',
  '/recording(.*)',
  '/personal-room(.*)',
  '/meeting(.*)',
  '/meetings(.*)',
  '/workos(.*)',
  '/messages(.*)',
  '/admin(.*)',
]);

const hasRealClerk = Boolean(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY &&
    !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY.startsWith('pk_test_ZXhh')
);

const isDevDemoBypass =
  process.env.NODE_ENV !== 'production' &&
  (process.env.DEMO_MODE === 'true' ||
    process.env.NEXT_PUBLIC_DEMO_MODE === 'true' ||
    !hasRealClerk);

export default isDevDemoBypass
  ? function demoMiddleware() {
      return NextResponse.next();
    }
  : clerkMiddleware(async (auth, req) => {
      if (isProtectedRoute(req)) {
        await auth.protect();
      }
    });

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
