import { NextResponse } from 'next/server';

// Configure timeout for long-running process
export const maxDuration = 300; // 5 minutes
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    console.log('NEXT.JS: Received dubbing request');
    
    const { videoUrl } = await request.json();

    if (!videoUrl) {
      return NextResponse.json(
        { error: 'Video URL is required' },
        { status: 400 }
      );
    }

    console.log('NEXT.JS: Forwarding to Python service:', videoUrl);

    // Flask service URL
    const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || 'http://localhost:5001';

    const response = await fetch(`${PYTHON_SERVICE_URL}/api/start-dubbing`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ videoUrl }),
      signal: AbortSignal.timeout(300000), // 5 minutes
    });

    // Check content type
    const contentType = response.headers.get('content-type');
    
    if (!response.ok) {
      console.error('NEXT.JS: Python service error:', response.status);
      
      // Handle HTML response (404/500 error pages)
      if (contentType && contentType.includes('text/html')) {
        const htmlText = await response.text();
        console.error('NEXT.JS: Received HTML (likely error page):', htmlText.substring(0, 200));
        return NextResponse.json(
          { 
            error: 'Python dubbing service unavailable',
            details: `Flask server returned ${response.status}. Ensure Flask is running on ${PYTHON_SERVICE_URL}`
          },
          { status: 503 }
        );
      }
      
      // Try to parse JSON error
      try {
        const errorData = await response.json();
        console.error('NEXT.JS: Error from Python:', errorData);
        return NextResponse.json(
          { error: 'Dubbing service error', details: errorData },
          { status: response.status }
        );
      } catch {
        return NextResponse.json(
          { error: 'Failed to parse error response' },
          { status: 500 }
        );
      }
    }

    // Parse successful response
    const result = await response.json();
    console.log('NEXT.JS: Dubbing completed successfully');

    return NextResponse.json({
      message: 'Dubbing completed successfully',
      dubbedUrl: result.dubbed_url,
      summary: result.summary,
      chapters: result.chapters,
    });

  } catch (error: any) {
    console.error('NEXT.JS: Error:', error);
    
    if (error.name === 'TimeoutError' || error.name === 'AbortError') {
      return NextResponse.json(
        { 
          error: 'Dubbing timeout',
          details: 'Processing took too long. Try a shorter video.'
        },
        { status: 504 }
      );
    }

    if (error.code === 'ECONNREFUSED') {
      return NextResponse.json(
        { 
          error: 'Cannot connect to dubbing service',
          details: 'Flask server is not running. Start it with: python app.py'
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      { 
        error: 'Unexpected error',
        details: error.message || 'Unknown error'
      },
      { status: 500 }
    );
  }
}
