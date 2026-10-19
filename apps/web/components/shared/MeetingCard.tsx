'use client';

import Image from 'next/image';
import { Button } from '../ui/button';
import { useToast } from '../ui/use-toast';

interface MeetingCardProps {
  icon: string;
  title: string;
  date: string;
  isDubbedView: boolean;
  onPlayClick?: () => void;
  onDubClick?: () => void;
  onDeleteClick?: () => void;
  onInsightClick?: () => void;
  insightLoading?: boolean;
  buttonText?: string;
  link?: string;
}

const MeetingCard = ({
  icon,
  title,
  date,
  isDubbedView,
  onPlayClick,
  onDubClick,
  onDeleteClick,
  onInsightClick,
  insightLoading,
  buttonText,
  link,
}: MeetingCardProps) => {
  const { toast } = useToast();

  return (
    <section className="flex min-h-[258px] w-full flex-col justify-between rounded-[14px] bg-dark-1 px-5 py-8 xl:max-w-[568px]">
      <article className="flex flex-col gap-5">
        <Image src={icon} alt="meeting icon" width={28} height={28} />
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="text-base font-normal">{date}</p>
        </div>
      </article>
      <article className="flex justify-end">
        <div className="flex gap-2">
          {/* Play Button */}
          {onPlayClick && (
            <Button onClick={onPlayClick} className="rounded bg-blue-1 px-6">
              <Image src="/icons/play.svg" alt="play" width={20} height={20} />
              &nbsp; {isDubbedView ? 'Play Dubbed' : 'Play Original'}
            </Button>
          )}
          {/* Insight Button */}
          {!isDubbedView && onInsightClick && (
            <Button
              onClick={onInsightClick}
              className="rounded bg-green-600 px-6 hover:bg-green-700"
              disabled={insightLoading}
            >
              {insightLoading ? 'Generating...' : 'Insight'}
            </Button>
          )}
          {/* Dubbing Button */}
          {!isDubbedView && onDubClick && (
            <Button
              onClick={onDubClick}
              className="rounded bg-purple-600 px-6 hover:bg-purple-700 disabled:opacity-50"
              disabled={!onDubClick}
            >
              {buttonText || 'Start Dubbing'}
            </Button>
          )}
          {/* Delete Button */}
          {!isDubbedView && onDeleteClick && (
            <Button
              onClick={onDeleteClick}
              className="rounded bg-red-500 px-6 hover:bg-red-600"
            >
              Delete
            </Button>
          )}
          {/* Copy Link for Dubbed */}
          {isDubbedView && link && (
            <Button
              onClick={() => {
                navigator.clipboard.writeText(link);
                toast({
                  title: 'Link Copied',
                  description: 'Dubbed video link copied to clipboard',
                });
              }}
              className="rounded bg-dark-4 px-6 hover:bg-dark-3"
            >
              Copy Link
            </Button>
          )}
          {/* Delete for Dubbed */}
          {isDubbedView && onDeleteClick && (
            <Button
              onClick={onDeleteClick}
              className="rounded bg-red-500 px-6 hover:bg-red-600"
            >
              Delete
            </Button>
          )}
        </div>
      </article>
    </section>
  );
};

export default MeetingCard;
