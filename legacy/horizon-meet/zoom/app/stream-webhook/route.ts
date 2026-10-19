import { NextResponse } from "next/server";

// ✅ This endpoint will catch ALL events from Stream
export async function POST(req: Request) {
  try {
    const body = await req.json();

    console.log("📩 Stream Webhook Event:", JSON.stringify(body, null, 2));

    // Always reply 200 so Stream knows we got it
    return NextResponse.json({ received: true });
  } catch (err) {
    console.error("❌ Webhook error:", err);
    return NextResponse.json({ error: "Webhook failed" }, { status: 500 });
  }
}
