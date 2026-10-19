'use client';

import { useGetCalls } from '@/hooks/useGetCalls';
import MeetingCard from '@/components/shared/MeetingCard';
import Loader from '@/components/shared/Loader';

const Previous = () => {
  const { endedCalls, isLoading } = useGetCalls();

  if (isLoading) return <Loader />;

  return (
    <section className='flex size-full flex-col gap-10 text-white'>
      <h1 className='text-3xl font-bold'>Previous</h1>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {endedCalls.length > 0 ? (
          endedCalls.map((call) => (
            <MeetingCard
              key={call.id}
              icon="/icons/previous.svg"
              title={call.state?.custom?.description || 'Instant Meeting'}
              date={
                call.state?.startsAt
                  ? new Date(call.state.startsAt).toLocaleString()
                  : ''
              }
              isDubbedView={false}
              // Removed onPlayClick prop so no button is rendered
            />
          ))
        ) : (
          <h1 className="text-2xl font-bold text-white">No Previous Calls</h1>
        )}
      </div>
    </section>
  );
};

export default Previous;
