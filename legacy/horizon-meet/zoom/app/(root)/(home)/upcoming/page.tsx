'use client';

import { useGetCalls } from '@/hooks/useGetCalls';
import MeetingCard from '@/components/shared/MeetingCard';
import Loader from '@/components/shared/Loader';

const Upcoming = () => {
  const { upcomingCalls, isLoading } = useGetCalls();

  if (isLoading) return <Loader />;

  return (
    <section className='flex size-full flex-col gap-10 text-white'>
      <h1 className='text-3xl font-bold'>Upcoming</h1>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {upcomingCalls.length > 0 ? (
          upcomingCalls.map((call) => (
            <MeetingCard
              key={call.id}
              icon="/icons/upcoming.svg"
              title={call.state?.custom?.description || 'Scheduled Meeting'}
              date={
                call.state?.startsAt
                  ? new Date(call.state.startsAt).toLocaleString()
                  : ''
              }
              isDubbedView={false}
              onPlayClick={() => window.location.href = `/meeting/${call.id}`}
            />
          ))
        ) : (
          <h1 className="text-2xl font-bold text-white">No Upcoming Calls</h1>
        )}
      </div>
    </section>
  );
};

export default Upcoming;
