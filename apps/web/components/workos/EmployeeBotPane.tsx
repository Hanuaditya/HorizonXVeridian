'use client';

import React, { useEffect, useMemo, useState } from 'react';
import type {
  WorkOSDispatchedTicket,
  WorkOSSlackMessage,
  WorkOSTask,
} from '@/lib/workos-types';

interface EmployeeBotPaneProps {
  threadId: string | null;
  tasks: Record<string, WorkOSTask>;
  dispatchedTickets: WorkOSDispatchedTicket[];
  slackFeed: WorkOSSlackMessage[];
  onAfterReply: () => Promise<void>;
}

const QUICK_REPLIES = [
  '60% done: staging environment provisioned and API integration tests running.',
  'Blocked waiting on AppSec allowlist exception for Legacy v1 Payment API.',
  'My work assigned during the meeting is completed and pushed cleanly.',
];

export default function EmployeeBotPane({
  threadId,
  tasks,
  dispatchedTickets,
  slackFeed,
  onAfterReply,
}: EmployeeBotPaneProps) {
  const activeAssignees = useMemo(() => {
    const items: Array<{ label: string; assignee: string; taskId: string; jiraKey?: string }> = [];
    const dispatchedByTask = new Map(dispatchedTickets.map((d) => [d.task_id, d]));

    const sourceList =
      dispatchedTickets.length > 0
        ? dispatchedTickets.map((d) => ({
            task_id: d.task_id,
            assignee: d.assignee,
            jira_key: d.jira_key,
          }))
        : Object.values(tasks || {})
            .filter((t) => t.status !== 'DEFERRED' && t.status !== 'CANCELLED')
            .map((t) => ({
              task_id: t.task_id,
              assignee: t.rerouted_assignee || t.assignee,
              jira_key: dispatchedByTask.get(t.task_id)?.jira_key || t.jira_ticket_id || undefined,
            }));

    sourceList.forEach((item, idx) => {
      const prefix = idx === 0 ? 'Employee A' : idx === 1 ? 'Employee B' : `Employee ${idx + 1}`;
      items.push({
        label: `${prefix}: ${item.assignee}`,
        assignee: item.assignee,
        taskId: item.task_id,
        jiraKey: item.jira_key,
      });
    });
    return items;
  }, [dispatchedTickets, tasks]);

  const [selectedTaskId, setSelectedTaskId] = useState<string>('');
  const [replyText, setReplyText] = useState<string>('');
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);

  useEffect(() => {
    if (activeAssignees.length > 0 && !activeAssignees.some((a) => a.taskId === selectedTaskId)) {
      setSelectedTaskId(activeAssignees[0].taskId);
    }
  }, [activeAssignees, selectedTaskId]);

  const currentTab =
    activeAssignees.find((a) => a.taskId === selectedTaskId) || activeAssignees[0] || null;

  const employeeMessages = useMemo(() => {
    if (!currentTab) return [];
    return (slackFeed || []).filter(
      (m) =>
        m.role === 'employee' &&
        (m.task_id === currentTab.taskId ||
          m.recipient.toLowerCase() === currentTab.assignee.toLowerCase() ||
          m.sender.toLowerCase() === currentTab.assignee.toLowerCase())
    );
  }, [slackFeed, currentTab]);

  const sendReply = async (textToSend: string) => {
    if (!threadId || !currentTab || !textToSend.trim()) return;
    setSending(true);
    setReplyError(null);
    try {
      const res = await fetch(
        `/api/workos/threads/${encodeURIComponent(threadId)}/employee-reply`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: currentTab.taskId,
            reply_text: textToSend.trim(),
          }),
        }
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || `Reply failed (${res.status})`);
      }
      setReplyText('');
      await onAfterReply();
    } catch (err: unknown) {
      setReplyError(err instanceof Error ? err.message : 'Failed to send employee reply');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-sky-400/25 bg-dark-1 p-5 text-white shadow-lg">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
        <div>
          <span className="rounded bg-sky-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-300">
            Right Pane · Employee 1-on-1 Bot Console
          </span>
          <h2 className="mt-1 text-base font-bold text-white">
            Veridian Bot ↔ Employee Slack DM Loop
          </h2>
        </div>
        {currentTab?.jiraKey && (
          <span className="rounded-full border border-sky-400/30 bg-sky-500/15 px-3 py-1 font-mono text-[11px] text-sky-200">
            {currentTab.jiraKey}
          </span>
        )}
      </div>

      {activeAssignees.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {activeAssignees.map((tab) => (
            <button
              key={tab.taskId}
              type="button"
              onClick={() => setSelectedTaskId(tab.taskId)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                currentTab?.taskId === tab.taskId
                  ? 'border-sky-400 bg-sky-500/25 text-white'
                  : 'border-white/10 bg-dark-2 text-white/65 hover:text-white'
              }`}
            >
              {tab.label}
              {tab.jiraKey ? ` (${tab.jiraKey})` : ''}
            </button>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-white/10 bg-dark-2 p-4 text-xs text-white/45">
          Employee A and Employee B tabs appear once sprint tasks are extracted and approved.
        </div>
      )}

      <div className="flex-1 space-y-2 overflow-y-auto rounded-lg border border-white/10 bg-dark-2 p-3 min-h-[260px] max-h-80">
        {employeeMessages.length === 0 ? (
          <p className="py-12 text-center text-xs text-white/40">
            {dispatchedTickets.length === 0
              ? 'Waiting for Manager approval — 1-on-1 assignment & check-in DMs will arrive here.'
              : 'Assignment DM delivered. Click "Run Scheduled Check-In Now" or reply below.'}
          </p>
        ) : (
          employeeMessages.map((m) => {
            const isBot = m.sender === 'Veridian Bot';
            return (
              <div
                key={m.id}
                className={`rounded-lg p-2.5 text-xs ${
                  isBot
                    ? 'mr-6 border border-purple-400/25 bg-purple-500/10 text-white'
                    : 'ml-6 border border-sky-400/30 bg-sky-500/15 text-sky-100'
                }`}
              >
                <div className="mb-1 flex items-center justify-between text-[10px] opacity-60">
                  <span className="font-semibold">{m.sender}</span>
                  <span>{m.kind || 'dm'}</span>
                </div>
                <pre className="whitespace-pre-wrap font-sans text-[11px] leading-relaxed">
                  {m.text}
                </pre>
              </div>
            );
          })
        )}
      </div>

      {currentTab && dispatchedTickets.length > 0 && (
        <div className="space-y-2.5 border-t border-white/10 pt-3">
          <div className="flex flex-wrap gap-1.5">
            {QUICK_REPLIES.map((preset) => (
              <button
                key={preset}
                type="button"
                disabled={sending}
                onClick={() => sendReply(preset)}
                className="rounded-md border border-white/15 bg-dark-2 px-2.5 py-1 text-left text-[10px] text-white/80 transition hover:border-sky-400 hover:text-white disabled:opacity-50"
              >
                {preset}
              </button>
            ))}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendReply(replyText);
                }
              }}
              placeholder={`Reply as ${currentTab.assignee} (synced to Slack + Jira)...`}
              className="flex-1 rounded-lg border border-white/15 bg-dark-2 px-3 py-2 text-xs text-white placeholder:text-white/40 focus:border-sky-400 focus:outline-none"
            />
            <button
              type="button"
              disabled={sending || !replyText.trim()}
              onClick={() => sendReply(replyText)}
              className="rounded-lg bg-blue-1 px-4 py-2 text-xs font-bold text-white transition hover:bg-blue-600 disabled:opacity-50"
            >
              {sending ? 'Syncing...' : 'Send Reply'}
            </button>
          </div>

          {replyError && (
            <p className="text-[11px] text-red-300">{replyError}</p>
          )}
        </div>
      )}
    </div>
  );
}

