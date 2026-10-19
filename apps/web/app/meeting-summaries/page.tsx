'use client';

import { supabase } from '@/lib/supabase';
import Link from 'next/link';
import React, { useEffect, useState } from 'react';

// Type for rows from Supabase
type RecordingInsight = {
  id: string;
  created_at: string;
  summary: string;
  chapters: { time: string; title: string }[];
  dubbed_video_url: string;
  original_video_url: string;
};

const MeetingSummariesPage = () => {
  const [recordings, setRecordings] = useState<RecordingInsight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchRecordings = async () => {
      setLoading(true);
      const { data, error } = await supabase
        .from('recordings')
        .select('*')
        .order('created_at', { ascending: false });

      if (error) {
        setError('Could not fetch insights from the database.');
      } else {
        setRecordings(data || []);
      }
      setLoading(false);
    };
    fetchRecordings();
  }, []);

  if (loading)
    return <p className="text-white p-8">Loading...</p>;
  if (error)
    return <p className="text-white p-8">{error}</p>;

  return (
    <section className="flex size-full flex-col gap-10 text-white p-8">
      <h1 className="text-3xl font-bold">Meeting Insights</h1>
      <div className="flex flex-col gap-8">
        {recordings && recordings.length > 0 ? (
          recordings.map((rec) => (
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
                        // Convert time MM:SS to seconds for entry link
                        const timeParts = chapter.time.split(':').map(Number);
                        const timeInSeconds = (timeParts[0] || 0) * 60 + (timeParts[1] || 0);
                        // Prefer dubbed_video_url but fallback to original
                        const videoUrl =
                          rec.dubbed_video_url && rec.dubbed_video_url.length > 0
                            ? rec.dubbed_video_url
                            : rec.original_video_url;
                        return (
                          <li key={index} className="mb-1">
                            <Link
                              href={`${videoUrl}#t=${timeInSeconds}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="hover:text-blue-1 transition-colors"
                            >
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
          <p>No insights found. Click the &apos;Insight&apos; button on a recording to generate summaries here.</p>
        )}
      </div>
    </section>
  );
};

export default MeetingSummariesPage;
