import { SignIn } from '@clerk/nextjs';
import Link from 'next/link';
import React from 'react';
import { hasRealClerkKey } from '@/providers/AuthBridge';

const SignInPage = () => {
  if (!hasRealClerkKey()) {
    return (
      <main className="flex h-screen w-full flex-col items-center justify-center gap-4 bg-dark-2 p-6 text-center text-white">
        <h1 className="text-2xl font-bold">Demo Manager Mode Active</h1>
        <p className="max-w-md text-sm text-white/65">
          Clerk credentials are not configured yet. You are signed in as simulated Demo Manager
          (`org:admin · org_demo_horizon`).
        </p>
        <Link href="/workos" className="rounded-lg bg-blue-1 px-5 py-2.5 text-sm font-bold">
          Continue to WorkOS Hub
        </Link>
      </main>
    );
  }

  return (
    <main className="flex h-screen w-full items-center justify-center">
      <SignIn />
    </main>
  );
};

export default SignInPage;
