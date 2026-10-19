/**
 * Auto-generated from packages/contracts/sse_events.schema.json
 * DO NOT EDIT DIRECTLY. Run `npm run contracts` to regenerate.
 */

export type SSEEventType =
  | 'processing_started'
  | 'resolution_ready'
  | 'hitl_ready'
  | 'dispatched'
  | 'tracker_update'
  | 'complete'
  | 'error';

export interface SSEEventEnvelope<T = Record<string, unknown>> {
  event_type: SSEEventType;
  thread_id: string;
  payload: T;
}
