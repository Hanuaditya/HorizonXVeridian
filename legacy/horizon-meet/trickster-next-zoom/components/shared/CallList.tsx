'use client';

import { useGetCalls } from '@/hooks/useGetCalls';
import { CallRecording } from '@stream-io/video-react-sdk';
import { useRouter } from 'next/navigation';
import React, { useEffect, useState, useCallback } from 'react';
import MeetingCard from './MeetingCard';
import Loader from './Loader';
import { useToast } from '../ui/use-toast';
import { supabase } from '@/lib/supabase';
import { Button } from '../ui/button';

type CallListProps = {
  type?: 'ended' | 'recordings' | 'upcoming';
};

type DubbedRecording = {
  id: number;
  created_at: string;
  original_video_url: string;
  dubbed_video_url: string;
  summary?: string;
  chapters?: any;
};

type RecordingWithCallId = CallRecording & {
  callId: string;
};

const CallList = ({ type }: CallListProps) => {
  const router = useRouter();
  const { callRecordings, isLoading } = useGetCalls();
  const [originalRecordings, setOriginalRecordings] = useState<RecordingWithCallId[]>([]);
  const [dubbedRecordings, setDubbedRecordings] = useState<DubbedRecording[]>([]);
  const [view, setView] = useState<'original' | 'dubbed'>('original');
  const [dubbingStatus, setDubbingStatus] = useState<Record<string, boolean>>({});
  const [deletingCallIds, setDeletingCallIds] = useState<Set<string>>(new Set());
  const [loadingDubbed, setLoadingDubbed] = useState(false);
  const [insightStatus, setInsightStatus] = useState<Record<string, boolean>>({});
  const [modalData, setModalData] = useState<{ summary: string, chapters: any[] } | null>(null);
  const { toast } = useToast();

  const fetchDubbedRecordings = useCallback(async () => {
    try {
      setLoadingDubbed(true);
      const { data, error } = await supabase
        .from('recordings')
        .select('*')
        .neq('dubbed_video_url', '')  // Only fetch records with actual dubbed videos
        .order('created_at', { ascending: false });
      if (error) {
        toast({
          title: 'Error loading dubbed recordings',
          description: error.message || 'Could not fetch recordings',
          variant: 'destructive'
        });
      } else {
        setDubbedRecordings(data || []);
      }
    } catch {
      toast({
        title: 'Connection error',
        description: 'Failed to connect to database',
        variant: 'destructive'
      });
    } finally {
      setLoadingDubbed(false);
    }
  }, [toast]);

  useEffect(() => {
    const fetchOriginals = async () => {
      try {
        const callData = await Promise.all(
          callRecordings?.map(async (meeting) => {
            try {
              const result = await meeting.queryRecordings();
              return result.recordings.map((rec) => ({
                ...rec,
                callId: meeting.id,
              }));
            } catch (error) {
              console.error(`[fetchOriginals] Failed for ${meeting.id}:`, error);
              return [];
            }
          }) ?? []
        );
        const allRecs = callData.flat().filter(Boolean);
        setOriginalRecordings(allRecs);
      } catch (error) {
        toast({
          title: 'Could not fetch original recordings',
          variant: 'destructive'
        });
      }
    };
    if (callRecordings && callRecordings.length > 0) {
      fetchOriginals();
    }
    fetchDubbedRecordings();
  }, [callRecordings, toast, fetchDubbedRecordings]);

  useEffect(() => {
    if (view === 'dubbed') {
      fetchDubbedRecordings();
    }
  }, [view, fetchDubbedRecordings]);

  const handleStartDubbing = async (recording: CallRecording) => {
    setDubbingStatus((prev) => ({ ...prev, [recording.url]: true }));
    toast({
      title: 'Starting dubbing...',
      description: 'This may take several minutes depending on video length.'
    });

    try {
      const response = await fetch('/api/start-dubbing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videoUrl: recording.url }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to start dubbing');
      }

      await response.json();
      toast({
        title: 'Dubbing completed!',
        description: 'Video has been dubbed and saved to cloud storage.'
      });

      fetchDubbedRecordings();

    } catch (error) {
      toast({
        title: 'Error during dubbing',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive'
      });
    } finally {
      setDubbingStatus((prev) => ({ ...prev, [recording.url]: false }));
    }
  };

  const handleGenerateInsight = async (recording: RecordingWithCallId) => {
    setInsightStatus(prev => ({ ...prev, [recording.url]: true }));
    try {
      const response = await fetch('/api/generate-insight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videoUrl: recording.url }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Failed to generate insight');
      setModalData({ summary: data.summary, chapters: data.chapters });
      toast({ title: 'Insight Generated', description: 'Summary ready!' });
    } catch (error) {
      toast({ title: 'Error', description: error instanceof Error ? error.message : String(error), variant: 'destructive' });
    } finally {
      setInsightStatus(prev => ({ ...prev, [recording.url]: false }));
    }
  };

  const handleDelete = async (recording: RecordingWithCallId) => {
    if (deletingCallIds.has(recording.callId)) {
      toast({
        title: 'Delete in progress',
        description: 'Please wait for the current deletion to complete',
      });
      return;
    }

    const confirmDelete = window.confirm(
      'Are you sure you want to delete this call and ALL its recordings? This action cannot be undone and may take up to 15 seconds.'
    );
    if (!confirmDelete) return;

    setDeletingCallIds((prev) => new Set(prev).add(recording.callId));

    try {
      toast({
        title: 'Deleting call...',
        description: 'This may take up to 15 seconds. Please wait.',
      });

      const response = await fetch('/api/delete-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ callId: recording.callId }),
      });

      let data: any = {};
      try {
        data = await response.json();
      } catch {
        data = {};
      }

      if (!response.ok) {
        throw new Error(data.error || 'Failed to delete call');
      }

      setOriginalRecordings((prev) => prev.filter((rec) => rec.callId !== recording.callId));
      toast({
        title: 'Call deleted successfully',
        description: 'All recordings have been permanently removed.',
      });
    } catch (error: any) {
      let errorMessage = 'Unknown error occurred';
      if (error.name === 'TimeoutError' || error.name === 'AbortError') {
        errorMessage = 'Request timed out. The call may still be deleting. Please refresh and try again.';
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }
      toast({
        title: 'Error deleting call',
        description: errorMessage,
        variant: 'destructive',
      });
    } finally {
      setDeletingCallIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(recording.callId);
        return newSet;
      });
    }
  };

  const handleDeleteDubbed = async (dubbedId: number) => {
    const confirmDelete = window.confirm(
      'Are you sure you want to delete this dubbed recording? This action cannot be undone.'
    );
    if (!confirmDelete) return;

    try {
      toast({ title: 'Deleting dubbed recording...' });

      const { error } = await supabase
        .from('recordings')
        .delete()
        .eq('id', dubbedId);

      if (error) throw error;

      setDubbedRecordings((prev) => prev.filter((rec) => rec.id !== dubbedId));

      toast({
        title: 'Deleted successfully',
        description: 'Dubbed recording has been removed.',
      });
    } catch (error) {
      toast({
        title: 'Error deleting recording',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  if (isLoading) return <Loader />;

  return (
    <section className="flex size-full flex-col gap-10 text-white">
      <h1 className="text-3xl font-bold">Recordings</h1>

      <div className="flex gap-4 border-b border-gray-600 pb-4">
        <Button
          onClick={() => setView('original')}
          variant={view === 'original' ? 'default' : 'outline'}
        >
          Original Recordings
        </Button>
        <Button
          onClick={() => setView('dubbed')}
          variant={view === 'dubbed' ? 'default' : 'outline'}
        >
          Dubbed Recordings ({dubbedRecordings.length})
        </Button>
      </div>

      {loadingDubbed && view === 'dubbed' && <Loader />}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {view === 'original' && (
          <>
            {originalRecordings.length > 0 ? (
              originalRecordings.map((recording) => (
                <MeetingCard
                  key={recording.url}
                  icon="/icons/recordings.svg"
                  title={recording.filename?.substring(0, 20) || 'Recording'}
                  date={recording.start_time?.toLocaleString() || new Date().toLocaleString()}
                  isDubbedView={false}
                  onPlayClick={() => router.push(recording.url)}
                  onInsightClick={() => handleGenerateInsight(recording)}
                  insightLoading={!!insightStatus[recording.url]}
                  onDubClick={dubbingStatus[recording.url] ? undefined : () => handleStartDubbing(recording)}
                  onDeleteClick={
                    deletingCallIds.has(recording.callId) ? undefined : () => handleDelete(recording)
                  }
                  buttonText={dubbingStatus[recording.url] ? 'Dubbing...' : 'Start Dubbing'}
                />
              ))
            ) : (
              <p>No original recordings found.</p>
            )}
          </>
        )}

        {view === 'dubbed' && !loadingDubbed && (
          <>
            {dubbedRecordings.length > 0 ? (
              dubbedRecordings.map((dubbedRec) => (
                <MeetingCard
                  key={dubbedRec.id}
                  icon="/icons/video.svg"
                  title={`Dubbed Recording #${dubbedRec.id}`}
                  date={new Date(dubbedRec.created_at).toLocaleString()}
                  isDubbedView={true}
                  onPlayClick={() => window.open(dubbedRec.dubbed_video_url, '_blank')}
                  onDeleteClick={() => handleDeleteDubbed(dubbedRec.id)}
                  link={dubbedRec.dubbed_video_url}
                />
              ))
            ) : (
              <p>
                No dubbed recordings found. Click &apos;Start Dubbing&apos; on an original recording to create one.
              </p>
            )}
          </>
        )}
      </div>
      {modalData && (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-70 z-50">
          <div className="bg-dark-2 rounded-lg p-8 shadow-xl max-w-lg w-full">
            <h2 className="text-xl font-bold mb-4 text-white">Meeting Summary</h2>
            <p className="mb-4 text-white">{modalData.summary}</p>
            <h3 className="text-lg font-semibold text-white">Chapters:</h3>
            <ul className="mb-6">
              {modalData.chapters.map((ch, i) => (
                <li key={i} className="text-white">
                  <strong>{ch.time}</strong>: {ch.title}
                </li>
              ))}
            </ul>
            <Button onClick={() => setModalData(null)} className="bg-blue-600 rounded px-4 py-2">
              Close
            </Button>
          </div>
        </div>
      )}
    </section>
  );
};

export default CallList;
