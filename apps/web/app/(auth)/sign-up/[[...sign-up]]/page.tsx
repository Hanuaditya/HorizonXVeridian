import { SignUp } from '@clerk/nextjs';
import Link from 'next/link';
import React from 'react';
import { hasRealClerkKey } from '@/providers/AuthBridge';

const SignUpPage = () => {
  if (!hasRealClerkKey()) {
    return (
      <main className="flex h-screen w-full flex-col items-center justify-center gap-4 bg-dark-2 p-6 text-center text-white">
        <h1 className="text-2xl font-bold">Demo Manager Mode Active</h1>
        <p className="max-w-md text-sm text-white/65">
          Clerk sign-up activates automatically once real Clerk keys are added to `.env`.
        </p>
        <Link href="/workos" className="rounded-lg bg-blue-1 px-5 py-2.5 text-sm font-bold">
          Continue to WorkOS Hub
        </Link>
      </main>
    );
  }

  return (
    <main className="flex h-screen w-full items-center justify-center">
      <SignUp />
    </main>
  );
};

export default SignUpPage;
