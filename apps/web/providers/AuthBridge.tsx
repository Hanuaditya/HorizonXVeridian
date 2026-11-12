'use client';

import React, { createContext, useContext } from 'react';
import Link from 'next/link';
import { hasRealClerkKey, isDemoModeEnabled } from '@/lib/env-flags';
import {
  ClerkProvider,
  CreateOrganization,
  OrganizationSwitcher,
  SignInButton,
  SignedIn,
  UserButton,
  useAuth as useClerkAuth,
  useUser as useClerkUser,
} from '@clerk/nextjs';

export interface AppUser {
  id: string;
  username: string;
  fullName: string;
  imageUrl: string;
  email?: string | null;
}

export interface AppAuthValue {
  isLoaded: boolean;
  isSignedIn: boolean;
  isDemo: boolean;
  hasRealClerk: boolean;
  userId: string | null;
  orgId: string | null;
  orgRole: string | null;
  isManager: boolean;
  user: AppUser | null;
}

const DEMO_USER: AppUser = {
  id: 'user_clerk_manager_demo',
  username: 'hanu.manager',
  fullName: 'Hanu Aditya (Engineering Manager)',
  imageUrl: '/images/avatar-1.jpeg',
  email: 'aarav.sharma@example.com',
};

const DEFAULT_DEMO_CONTEXT: AppAuthValue = {
  isLoaded: true,
  isSignedIn: true,
  isDemo: true,
  hasRealClerk: false,
  userId: DEMO_USER.id,
  orgId: 'org_demo_horizon',
  orgRole: 'org:admin',
  isManager: true,
  user: DEMO_USER,
};

const AppAuthContext = createContext<AppAuthValue>(DEFAULT_DEMO_CONTEXT);

export { hasRealClerkKey, isDemoModeEnabled };

function ClerkAuthSync({ children }: { children: React.ReactNode }) {
  const { user, isLoaded } = useClerkUser();
  const { userId, orgId, orgRole, has } = useClerkAuth();

  const value: AppAuthValue = {
    isLoaded,
    isSignedIn: Boolean(userId),
    isDemo: false,
    hasRealClerk: true,
    userId: userId ?? null,
    orgId: orgId ?? null,
    orgRole: orgRole ?? null,
    isManager: Boolean(has?.({ role: 'org:admin' })),
    user: user
      ? {
          id: user.id,
          username: user.username || user.firstName || 'user',
          fullName: user.fullName || user.username || 'User',
          imageUrl: user.imageUrl || '/images/avatar-1.jpeg',
          email: user.primaryEmailAddress?.emailAddress || user.emailAddresses?.[0]?.emailAddress || null,
        }
      : null,
  };

  return <AppAuthContext.Provider value={value}>{children}</AppAuthContext.Provider>;
}

export function AppAuthProvider({ children }: { children: React.ReactNode }) {
  const realClerk = hasRealClerkKey();
  const demoMode = isDemoModeEnabled();

  if (realClerk && !demoMode) {
    return (
      <ClerkProvider
        publishableKey={process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY!}
        appearance={{
          layout: {
            socialButtonsVariant: 'iconButton',
            logoImageUrl: '/icons/logo.svg',
          },
          variables: {
            colorText: '#fff',
            colorPrimary: '#0E78F9',
            colorBackground: '#1C1F2E',
            colorInputBackground: '#252A41',
            colorInputText: '#fff',
          },
        }}
      >
        <ClerkAuthSync>{children}</ClerkAuthSync>
      </ClerkProvider>
    );
  }

  if (!demoMode && process.env.NODE_ENV === 'production' && process.env.NEXT_PHASE !== 'phase-production-build') {
    throw new Error(
      'FATAL [Horizon Veridian]: NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is required when DEMO_MODE=false.'
    );
  }

  return (
    <AppAuthContext.Provider value={DEFAULT_DEMO_CONTEXT}>
      {children}
    </AppAuthContext.Provider>
  );
}

export function useAppAuth(): AppAuthValue {
  return useContext(AppAuthContext);
}

export function useAppUser(): { user: AppUser | null; isLoaded: boolean } {
  const ctx = useContext(AppAuthContext);
  return { user: ctx.user, isLoaded: ctx.isLoaded };
}

export function AppHeaderAuthControls() {
  const ctx = useContext(AppAuthContext);

  if (ctx.hasRealClerk) {
    return (
      <SignedIn>
        <OrganizationSwitcher
          appearance={{
            variables: { colorText: '#ffffff', colorBackground: '#252A41' },
          }}
        />
        <UserButton />
      </SignedIn>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-full border border-purple-400/30 bg-purple-500/15 px-3 py-1 text-xs text-purple-200">
      <span className="h-2 w-2 rounded-full bg-emerald-400" />
      <span className="font-medium">Demo Manager</span>
      <span className="hidden font-mono text-[10px] text-white/60 sm:inline">
        org:admin · org_demo_horizon
      </span>
    </div>
  );
}

export function OrgOnboardingGuard({
  children,
  pageName = 'Horizon Veridian WorkOS',
}: {
  children: React.ReactNode;
  pageName?: string;
}) {
  const ctx = useAppAuth();

  if (ctx.isDemo || !ctx.hasRealClerk) {
    return <>{children}</>;
  }

  if (!ctx.isLoaded) {
    return (
      <div className="rounded-xl border border-white/10 bg-dark-1 p-8 text-center text-sm text-white/70">
        Loading Clerk authentication and organization context...
      </div>
    );
  }

  if (!ctx.isSignedIn) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border border-blue-500/30 bg-dark-1 p-8 text-center text-white shadow-xl">
        <h2 className="text-xl font-bold">Sign in to access {pageName}</h2>
        <p className="mt-2 text-sm text-white/65">
          Live mode (<code className="text-sky-300">DEMO_MODE=false</code>) requires an authenticated
          Clerk user session and organization membership.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <SignInButton mode="modal">
            <button
              type="button"
              className="rounded-lg bg-blue-1 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-600"
            >
              Sign In with Clerk
            </button>
          </SignInButton>
          <Link
            href="/sign-in"
            className="rounded-lg border border-white/15 bg-dark-2 px-5 py-2.5 text-sm font-medium text-white/80 hover:bg-dark-3"
          >
            Open Sign-In Page
          </Link>
        </div>
      </div>
    );
  }

  if (!ctx.orgId) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 rounded-2xl border border-purple-500/30 bg-dark-1 p-8 text-white shadow-xl">
        <div className="text-center">
          <span className="rounded-full bg-purple-500/20 px-3 py-1 text-xs font-semibold text-purple-300">
            Clerk Organization Required
          </span>
          <h2 className="mt-3 text-2xl font-bold">Create or Select Your Organization</h2>
          <p className="mt-2 text-sm text-white/65">
            {pageName} enforces strict multi-tenant RLS on Supabase using your active Clerk{' '}
            <code className="text-sky-300">org_id</code> and <code className="text-sky-300">org:admin</code>{' '}
            claims. Create <strong className="text-white">Horizon Veridian</strong> below or switch to
            an existing organization.
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-4">
          <OrganizationSwitcher
            hidePersonal
            afterSelectOrganizationUrl="/workos"
            afterCreateOrganizationUrl="/workos"
            appearance={{
              variables: { colorText: '#ffffff', colorBackground: '#252A41' },
            }}
          />
        </div>

        <CreateOrganization
          afterCreateOrganizationUrl="/workos"
          skipInvitationScreen
          appearance={{
            variables: {
              colorText: '#ffffff',
              colorPrimary: '#0E78F9',
              colorBackground: '#1C1F2E',
              colorInputBackground: '#252A41',
              colorInputText: '#ffffff',
            },
          }}
        />

        <p className="text-center font-mono text-xs text-white/50">
          After creating your org, seed its tenant data with:{' '}
          <span className="text-sky-300">python scripts/seed_live_supabase.py --org-id &lt;org_id&gt;</span>
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
