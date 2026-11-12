'use client';

import React, { createContext, useContext } from 'react';
import {
  ClerkProvider,
  OrganizationSwitcher,
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
  id: 'user_demo_manager',
  username: 'scott.manager',
  fullName: 'Scott Williamson (Demo Manager)',
  imageUrl: '/images/avatar-1.jpeg',
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

export function hasRealClerkKey(): boolean {
  const key = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || '';
  return Boolean(
    key &&
      !key.startsWith('pk_test_ZXhh') &&
      !key.includes('placeholder')
  );
}

export function isDemoModeEnabled(): boolean {
  return process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
}

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
