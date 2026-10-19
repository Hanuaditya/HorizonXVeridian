// actions/stream.action.ts
// ✅ Client-safe tokenProvider (no "use server" here)

export const tokenProvider = async (): Promise<string> => {
  try {
    const res = await fetch('/api/stream-token', {
      method: 'GET',
      credentials: 'include', // send Clerk cookies/session
    });

    if (!res.ok) {
      throw new Error(`Failed to fetch Stream token: ${res.status}`);
    }

    const data = await res.json();

    if (!data?.token) {
      throw new Error("No token returned from API");
    }

    return data.token; // MUST return raw JWT string
  } catch (err) {
    console.error("❌ Stream tokenProvider error:", err);
    throw err;
  }
};
