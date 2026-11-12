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

