export type WorkOSPhase =
  | 'IDLE'
  | 'INGESTING'
  | 'EXTRACTING'
  | 'FIREWALL'
  | 'RESOLVING'
  | 'HITL'
  | 'DISPATCHING'
  | 'COMPLETE'
  | 'ERROR';

export interface WorkOSTask {
  task_id: string;
  title: string;
  assignee: string;
  assignee_user_id?: string | null;
  assignee_resolution_flag?: string | null;
  resource_type?: string;
  transcript_quote?: string;
  status?: string;
  hr_status?: string | null;
  hr_provenance?: string | null;
  finance_flag?: string | null;
  finance_provenance?: string | null;
  security_flag?: string | null;
  security_confidence?: number | null;
  security_provenance?: string | null;
  capacity_flag?: string | null;
  capacity_provenance?: string | null;
  rerouted_assignee?: string | null;
  resolution_action?: string | null;
  reframed_title?: string | null;
  reframed_description?: string | null;
  jira_ticket_id?: string | null;
  jira_url?: string | null;
  slack_dm_sent?: boolean;
  dispatch_error?: string | null;
}

export interface WorkOSResolution {
  task_id: string;
  conflict_type: string;
  provenance_tag: string;
  suggested_action: 'REFRAME' | 'REROUTE' | 'DEFER' | 'OVERRIDE' | 'PROCEED';
  new_payload?: Record<string, unknown> | null;
}

export interface WorkOSDecision {
  decision: string;
  context_quote: string;
}

export interface WorkOSMeetingContext {
  title?: string;
  date?: string;
  attendees?: string[];
  tldr_bullets?: string[];
  speaker_resolution_scratchpad?: string;
}

export interface WorkOSDispatchedTicket {
  task_id: string;
  title: string;
  assignee: string;
  jira_key: string;
  jira_url: string;
  slack_sent?: boolean;
  mode?: string;
}

export interface WorkOSThreadState {
  thread_id?: string;
  meeting_id?: string;
  org_id?: string;
  title?: string;
  phase?: WorkOSPhase;
  tasks?: Record<string, WorkOSTask>;
  resolutions?: WorkOSResolution[];
  key_decisions?: WorkOSDecision[];
  meeting_context?: WorkOSMeetingContext;
  dispatched_tickets?: WorkOSDispatchedTicket[];
  approver_user_id?: string | null;
}

export interface WorkOSEmployee {
  id: string;
  org_id: string;
  full_name: string;
  email?: string | null;
  clerk_user_id?: string | null;
  slack_id?: string | null;
  jira_account_id?: string | null;
  status: string;
  capacity_cache: number;
}

export interface WorkOSAuditEntry {
  id?: string;
  meeting_id: string;
  thread_id?: string;
  task_id?: string;
  event_type: string;
  agent_node?: string;
  detail?: string;
  provenance_tag: string;
  actor_id?: string | null;
  created_at: string;
}
