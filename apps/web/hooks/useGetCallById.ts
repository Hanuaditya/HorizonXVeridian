import { Call, useStreamVideoClient } from '@stream-io/video-react-sdk';
import { useEffect, useState } from 'react';

export const useGetCallById = (id: string | string[]) => {
  const [call, setCall] = useState<Call>();
  const [isCallLoading, setIsCallLoading] = useState(true);

  const client = useStreamVideoClient();

  useEffect(() => {
    if (!client) {
      setIsCallLoading(false);
      return;
    }
    const loadCall = async () => {
      try {
        const { calls } = await client.queryCalls({
          filter_conditions: {
            id,
          },
        });
        if (calls.length > 0) setCall(calls[0]);
      } finally {
        setIsCallLoading(false);
      }
    };
    loadCall();
  }, [client, id]);

  return { call, isCallLoading };
};
