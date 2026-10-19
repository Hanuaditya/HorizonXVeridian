// app/api/stream-token/route.ts
import { NextResponse } from "next/server";
import { currentUser } from "@clerk/nextjs/server";
import { StreamChat } from "stream-chat";

const apiKey = process.env.STREAM_API_KEY as string;
const apiSecret = process.env.STREAM_API_SECRET as string;

export async function GET() {
  try {
    const user = await currentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const serverClient = StreamChat.getInstance(apiKey, apiSecret);

    // ✅ Create token with 1 hour expiry (second param must be a number)
    const token = serverClient.createToken(
      user.id,
      Math.floor(Date.now() / 1000) + 60 * 60 // 1 hour
    );

    return NextResponse.json({ token });
  } catch (error) {
    console.error("Stream token generation failed:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
