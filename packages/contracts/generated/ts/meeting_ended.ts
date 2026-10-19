/**
 * Auto-generated from packages/contracts/meeting_ended.schema.json
 * DO NOT EDIT DIRECTLY. Run `npm run contracts` to regenerate.
 */

export interface Participant {
  clerk_user_id: string;
  display_name: string;
  email: string;
}

export interface TranscriptSegment {
  speaker: string;
  speaker_user_id?: string | null;
  start: number;
  end: number;
  text: string;
}

export interface MeetingEndedPayload {
  meeting_id: string;
  org_id: string;
  title: string;
  started_at: string;
  ended_at: string;
  language: string;
  participants: Participant[];
  transcript: TranscriptSegment[];
  summary?: string | null;
  recording_url?: string | null;
}
