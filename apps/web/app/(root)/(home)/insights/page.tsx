import { supabase } from '@/lib/supabase';
import Link from 'next/link';
import React from 'react';

// Define the type for our data
export const dynamic = 'force-dynamic';

type RecordingInsight = {
    id: string;
    created_at: string;
    summary: string;
    chapters: { time: string; title: string }[];
    dubbed_video_url: string;
};

const InsightsPage = async () => {
  // Fetch all data from the recordings table
  const { data: recordings, error } = await supabase
    .from('recordings')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) {
    return <p className="text-white p-4">Could not fetch insights from the database.</p>;
  }

  return (
    <section className="flex size-full flex-col gap-10 text-white p-8">
      <h1 className="text-3xl font-bold">Meeting Insights</h1>

      <div className="flex flex-col gap-8">
        {recordings && recordings.length > 0 ? (
          recordings.map((rec: RecordingInsight) => (
            <div key={rec.id} className="rounded-lg bg-dark-1 p-6">
              <h2 className="text-xl font-semibold mb-4">
                Recording from: {new Date(rec.created_at).toLocaleString()}
              </h2>
              
              <div className="prose prose-invert max-w-none">
                <h3 className="text-lg font-bold">Summary</h3>
                <p>{rec.summary || "No summary was generated for this recording."}</p>
                
                {rec.chapters && rec.chapters.length > 0 && (
                    <>
                        <h3 className="text-lg font-bold mt-6">Video Chapters</h3>
                        <ul className="list-disc pl-5">
                        {rec.chapters.map((chapter, index) => {
                            // Convert the MM:SS time format to total seconds for the URL
                            const timeParts = chapter.time.split(':').map(Number);
                            const timeInSeconds = (timeParts[0] || 0) * 60 + (timeParts[1] || 0);
                            
                            return (
                            <li key={index} className="mb-1">
                                <Link href={`${rec.dubbed_video_url}#t=${timeInSeconds}`} target="_blank" rel="noopener noreferrer" className="hover:text-blue-1 transition-colors">
                                    <strong>{chapter.time}</strong> - {chapter.title}
                                </Link>
                            </li>
                            );
                        })}
                        </ul>
                    </>
                )}
              </div>
            </div>
          ))
        ) : (
          <p>No insights found. Process a recording with the &apos;Start Dubbing&apos; button to generate insights here.</p>
        )}
      </div>
    </section>
  );
};

export default InsightsPage;