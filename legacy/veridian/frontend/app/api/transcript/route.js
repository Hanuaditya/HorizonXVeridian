import { readFileSync } from 'fs'
import { join } from 'path'
import { NextResponse } from 'next/server'

// Reads transcript.txt from the project root (one level above frontend/)
export async function GET() {
  try {
    const filePath = join(process.cwd(), '..', 'transcript.txt')
    const content = readFileSync(filePath, 'utf-8')
    return NextResponse.json({ transcript: content, chars: content.length })
  } catch (err) {
    return NextResponse.json(
      { error: `Could not read transcript.txt: ${err.message}` },
      { status: 500 }
    )
  }
}
