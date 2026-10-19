import React from 'react';
import CallList from '@/components/shared/CallList';

const RecordingsPage = () => {
  return (
    <section className="flex size-full flex-col gap-10 text-white">
      <h1 className="text-3xl font-bold">Recordings</h1>
      <CallList />
    </section>
  );
};

export default RecordingsPage;