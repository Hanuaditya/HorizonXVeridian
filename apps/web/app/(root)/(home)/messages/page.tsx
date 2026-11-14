'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { OrgOnboardingGuard, useAppAuth } from '@/providers/AuthBridge';
import { useAgentStream } from '@/lib/sse';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  Send,
  Shield,
  ShieldAlert,
  Sparkles,
  Ticket,
  User,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface MessageItem {
  id: string;
  client_msg_id?: string;
  sender?: string;
  sender_id?: string;
  recipient?: string;
  recipient_id?: string;
  role?: string;
  text: string;
  created_at: string;
  kind?: string;
  task_id?: string;
  jira_key?: string;
  metadata?: Record<string, unknown>;
  slack_ts?: string;
}

interface ThreadItem {
  channel_key: string;
  title: string;
  subtitle?: string;
  role: 'bot' | 'employee' | 'manager' | 'peer';
  hr_status?: string;
  status?: string;
  ticket_key?: string | null;
  progress_pct?: number;
  badge?: string;
  unread_count?: number;
  slack_deep_link?: string;
  active_ticket?: {
    key: string;
    title: string;
    status: string;
    progress_pct: number;
    jira_url?: string;
    task_id?: string;
  } | null;
  member?: {
    id?: string;
    name: string;
    email?: string;
    role?: string;
    hr_status?: string;
    domain_skills?: string[];
  };
}

function parseInlineSpans(text: string): React.ReactNode[] {
  const regex = /(`[^`]+`|\*[^*\n]+\*|<https?:\/\/[^>]+>|https?:\/\/[^\s<]+|\b[A-Z]{2,10}-\d+\b)/g;

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    const key = `${match.index}-${token}`;

    if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(
        <code key={key} className="rounded bg-white/[0.08] px-1.5 py-0.5 font-mono text-[11px] text-sky-200">
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith('*') && token.endsWith('*')) {
      parts.push(
        <strong key={key} className="font-semibold text-white">
          {token.slice(1, -1)}
        </strong>
      );
    } else if (token.startsWith('<http') && token.endsWith('>')) {
      const inner = token.slice(1, -1);
      const [url, label] = inner.split('|');
      parts.push(
        <a
          key={key}
          href={url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-0.5 text-blue-400 hover:text-blue-300 underline underline-offset-2"
        >
          {label || url} ↗
        </a>
      );
    } else if (token.startsWith('http')) {
      parts.push(
        <a
          key={key}
          href={token}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-0.5 text-blue-400 hover:text-blue-300 underline underline-offset-2"
        >
          {token} ↗
        </a>
      );
    } else if (/^[A-Z]{2,10}-\d+$/.test(token)) {
      parts.push(
        <span
          key={key}
          className="inline-flex items-center gap-1 rounded bg-sky-500/15 border border-sky-500/30 px-1.5 py-0.2 font-mono text-[10px] font-bold text-sky-300"
        >
          Open {token} ↗
        </span>
      );
    } else {
      parts.push(token);
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function renderFormattedText(text: string): React.ReactNode {
  if (!text) return null;

  const lines = text.split('\n');

  return (
    <div className="space-y-1">
      {lines.map((line, lineIdx) => {
        const trimmed = line.trim();
        const isQuote = trimmed.startsWith('>') || trimmed.startsWith('&gt;');
        const content = isQuote ? trimmed.replace(/^(&gt;|>)\s*/, '') : line;

        const parsedSpans = parseInlineSpans(content);

        if (isQuote) {
          return (
            <div
              key={lineIdx}
              className="my-1 border-l-2 border-amber-400/80 bg-amber-500/[0.07] pl-3 py-1 rounded-r text-amber-200/90 italic text-xs leading-relaxed"
            >
              {parsedSpans}
            </div>
          );
        }

        if (trimmed.startsWith('• ') || trimmed.startsWith('- ')) {
          return (
            <div key={lineIdx} className="flex items-start gap-2 pl-1 leading-relaxed">
              <span className="text-white/40 select-none leading-relaxed">•</span>
              <span className="flex-1 leading-relaxed">{parseInlineSpans(trimmed.slice(2))}</span>
            </div>
          );
        }

        if (!trimmed) {
          return <div key={lineIdx} className="h-1" />;
        }

        return (
          <div key={lineIdx} className="leading-relaxed">
            {parsedSpans}
          </div>
        );
      })}
    </div>
  );
}

// Memoized message bubble to eliminate keystroke re-rendering
const MessageBubble = React.memo(function MessageBubble({
  m,
  isCurrentUser,
  isBot,
  isAdmin,
  onDirectMessage,
  onApproveTickets,
  sending,
}: {
  m: MessageItem;
  isCurrentUser: boolean;
  isBot: boolean;
  isAdmin: boolean;
  onDirectMessage: (name: string) => void;
  onApproveTickets: () => void;
  sending: boolean;
}) {
  const isBlocker =
    m.kind === 'blocker_escalation' ||
    m.text.includes('[URGENT BLOCKER ESCALATION]');
  const isAlert =
    !isBlocker &&
    (m.kind === 'alert' ||
      m.kind === 'compliance_alert' ||
      m.text.includes('[IMMEDIATE COMPLIANCE ALERT]') ||
      m.text.includes('[ALERT]'));
  const isReviewMenu =
    m.kind === 'review_menu' ||
    m.text.includes('[MANAGER REVIEW MENU]');
  const isDigest =
    m.kind === 'progress_digest' ||
    m.text.includes('[Progress Digest]') ||
    m.text.includes('[Progress Update]');
  const isCompleted =
    m.kind === 'closure' ||
    m.kind === 'closure_confirmation' ||
    m.text.includes('[Task Completed');
  const isAssignment =
    m.kind === 'assignment' ||
    m.text.includes('[1-on-1 Task Assignment');

  const blockerAssignee =
    (m.metadata?.assignee as string) ||
    (m.text.match(/@([a-zA-Z0-9_\s]+?)\s+is BLOCKED/i)?.[1]?.trim());

  return (
    <div
      key={m.id || `${m.created_at}-${m.text.slice(0, 10)}`}
      className={cn('flex gap-3', isCurrentUser ? 'justify-end' : 'justify-start')}
    >
      {!isCurrentUser && (
        <div
          className={cn(
            'flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-bold shadow-sm',
            isBot
              ? 'bg-purple-600/30 text-purple-200 border border-purple-500/30'
              : 'bg-dark-3 text-white/80 border border-white/[0.1]'
          )}
        >
          {isBot ? <Bot className="size-4" /> : (m.sender || 'U')[0].toUpperCase()}
        </div>
      )}

      <div className={cn('flex max-w-[76%] flex-col', isCurrentUser ? 'items-end' : 'items-start')}>
        <div className="mb-1 flex items-center gap-2 text-[11px] text-white/40">
          <span className="font-semibold text-white/70">{m.sender || 'Sender'}</span>
          <span>·</span>
          <span>
            {m.created_at
              ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              : 'Just now'}
          </span>
          {m.jira_key && (
            <span className="rounded bg-sky-500/20 px-1.5 py-0.2 font-mono text-[9px] font-bold text-sky-300">
              {m.jira_key}
            </span>
          )}
        </div>

        {/* Message Bubble & Structured Cards */}
        {isBlocker ? (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/[0.1] p-4 text-xs text-rose-200 shadow-md">
            <div className="flex items-center justify-between gap-2 font-semibold text-rose-300 mb-2">
              <div className="flex items-center gap-2">
                <AlertTriangle className="size-4 text-rose-400" />
                <span className="uppercase tracking-wider text-[11px] font-bold">Urgent Blocker Escalation</span>
              </div>
              {m.jira_key && (
                <span className="rounded bg-rose-500/20 px-2 py-0.5 font-mono text-[10px] text-rose-300 border border-rose-500/30">
                  {m.jira_key}
                </span>
              )}
            </div>
            <div className="text-white/95 leading-relaxed">
              {renderFormattedText(m.text)}
            </div>
            {isAdmin && (
              <div className="mt-3 pt-2.5 border-t border-rose-500/20 flex items-center justify-between gap-3">
                <span className="text-[11px] text-white/50">Employee needs unblocking</span>
                <button
                  type="button"
                  onClick={() => onDirectMessage(blockerAssignee || m.text)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-rose-400/50 bg-rose-500/20 px-3 py-1 text-xs font-semibold text-rose-200 hover:bg-rose-500/35 transition"
                >
                  <span>Message Directly</span>
                  <ArrowRight className="size-3.5" />
                </button>
              </div>
            )}
          </div>
        ) : isAlert ? (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/[0.08] p-3.5 text-xs text-rose-200 shadow-md">
            <div className="flex items-center gap-2 font-semibold text-rose-300 mb-1.5">
              <ShieldAlert className="size-4" />
              <span className="uppercase tracking-wider text-[11px] font-bold">Immediate Compliance Alert</span>
            </div>
            <div className="text-white/90 leading-relaxed">
              {renderFormattedText(m.text)}
            </div>
          </div>
        ) : isReviewMenu ? (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.08] p-4 text-xs text-amber-200 shadow-md">
            <div className="flex items-center justify-between gap-2 font-semibold text-amber-300 mb-2">
              <div className="flex items-center gap-2">
                <Shield className="size-4" />
                <span className="uppercase tracking-wider text-[11px] font-bold">Manager Review & Governance Gate</span>
              </div>
              <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[10px] text-amber-300 border border-amber-500/30">
                Zero Tickets Created
              </span>
            </div>
            <div className="text-white/90 leading-relaxed">
              {renderFormattedText(m.text)}
            </div>
            {isAdmin && (
              <div className="mt-3 pt-2.5 border-t border-amber-500/20 flex items-center justify-between gap-3">
                <span className="text-[11px] text-white/50">One-click Jira ticket dispatch & employee Slack DMs</span>
                <button
                  type="button"
                  disabled={sending}
                  onClick={onApproveTickets}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition shadow-sm disabled:opacity-40"
                >
                  <CheckCircle2 className="size-3.5" />
                  <span>Approve & Create Tickets</span>
                </button>
              </div>
            )}
          </div>
        ) : isDigest ? (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/[0.08] p-3.5 text-xs text-emerald-200 shadow-md">
            <div className="flex items-center justify-between gap-2 font-semibold text-emerald-300 mb-1.5">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="size-4" />
                <span className="uppercase tracking-wider text-[11px] font-bold">Sprint Progress Digest</span>
              </div>
              {m.jira_key && (
                <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] text-emerald-300 border border-emerald-500/30">
                  {m.jira_key}
                </span>
              )}
            </div>
            <div className="text-white/90 leading-relaxed">
              {renderFormattedText(m.text)}
            </div>
          </div>
        ) : isCompleted ? (
          <div className="rounded-xl border border-teal-500/30 bg-teal-500/[0.08] p-3.5 text-xs text-teal-200 shadow-md">
            <div className="flex items-center justify-between gap-2 font-semibold text-teal-300 mb-1.5">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="size-4" />
                <span className="uppercase tracking-wider text-[11px] font-bold">Task Completed & Ticket Closed</span>
              </div>
              {m.jira_key && (
                <span className="rounded bg-teal-500/20 px-2 py-0.5 font-mono text-[10px] text-teal-300 border border-teal-500/30">
                  {m.jira_key}
                </span>
              )}
            </div>
            <div className="text-white/90 leading-relaxed">
              {renderFormattedText(m.text)}
            </div>
          </div>
        ) : isAssignment ? (
          <div className="rounded-xl border border-sky-500/30 bg-sky-500/[0.08] p-3.5 text-xs text-sky-200 shadow-md">
            <div className="flex items-center justify-between gap-2 font-semibold text-sky-300 mb-1.5">
              <div className="flex items-center gap-2">
                <Ticket className="size-4" />
                <span className="uppercase tracking-wider text-[11px] font-bold">1-on-1 Task Assignment</span>
              </div>
              {m.jira_key && (
                <span className="rounded bg-sky-500/20 px-2 py-0.5 font-mono text-[10px] text-sky-300 border border-sky-500/30">
                  {m.jira_key}
                </span>
              )}
            </div>
            <div className="text-white/90 leading-relaxed">
              {renderFormattedText(m.text)}
            </div>
          </div>
        ) : (
          <div
            className={cn(
              'rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm',
              isCurrentUser
                ? 'bg-blue-1 text-white rounded-tr-sm'
                : 'bg-dark-2 border border-white/[0.07] text-slate-100 rounded-tl-sm'
            )}
          >
            {renderFormattedText(m.text)}
          </div>
        )}
      </div>
    </div>
  );
});

export default function MessagesPage() {
  return (
    <OrgOnboardingGuard pageName="Messages Workspace">
      <MessagesWorkspace />
    </OrgOnboardingGuard>
  );
}

function MessagesWorkspace() {
  const { isManager, orgRole, userId, user } = useAppAuth();
  const isAdmin = isManager || orgRole === 'org:admin';

  const [threads, setThreads] = useState<ThreadItem[]>([]);
  const [activeChannelKey, setActiveChannelKey] = useState<string>('veridian-bot');
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [inputText, setInputText] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loadingThreads, setLoadingThreads] = useState<boolean>(true);
  const [loadingMessages, setLoadingMessages] = useState<boolean>(false);
  const [sending, setSending] = useState<boolean>(false);
  const [pingingUser, setPingingUser] = useState<string | null>(null);
  const [showRightDrawer, setShowRightDrawer] = useState<boolean>(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingMessagesRef = useRef<Map<string, MessageItem>>(new Map());
  const isSendingRef = useRef<boolean>(false);
  const inFlightRef = useRef<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // SSE Stream for live event push
  const { refreshState } = useAgentStream(activeThreadId);

  // 1. Load threads
  const loadThreads = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    try {
      const res = await fetch('/api/workos/messages/threads');
      if (res.ok) {
        const data = await res.json();
        const list: ThreadItem[] = data.threads || [];
        setThreads(list);
        if (data.active_thread_id) {
          setActiveThreadId(data.active_thread_id);
        }
      }
    } catch {
      // Offline tolerance
    } finally {
      setLoadingThreads(false);
    }
  }, []);

  useEffect(() => {
    loadThreads();
    const interval = setInterval(loadThreads, 6000);
    return () => clearInterval(interval);
  }, [loadThreads]);

  // 2. Load messages for active channel with optimistic preservation & AbortController guard
  const loadChannelMessages = useCallback(async (chKey: string, silent: boolean = false) => {
    if (typeof document !== 'undefined' && document.hidden) return;
    if (inFlightRef.current) return;
    inFlightRef.current = true;

    if (!silent) {
      setLoadingMessages(true);
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), 6000);

    try {
      const qs = activeThreadId ? `?thread_id=${encodeURIComponent(activeThreadId)}` : '';
      const res = await fetch(`/api/workos/messages/${encodeURIComponent(chKey)}${qs}`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        const incoming: MessageItem[] = data.messages || [];

        // Reconcile incoming server messages with pending optimistic messages
        for (const inc of incoming) {
          if (inc.client_msg_id && pendingMessagesRef.current.has(inc.client_msg_id)) {
            pendingMessagesRef.current.delete(inc.client_msg_id);
          }
          for (const [pId, pMsg] of pendingMessagesRef.current.entries()) {
            if (pMsg.text.trim() === inc.text.trim()) {
              pendingMessagesRef.current.delete(pId);
            }
          }
        }

        // Merge any unconfirmed pending optimistic messages at the end so they NEVER disappear
        const unconfirmedPending = Array.from(pendingMessagesRef.current.values());
        const combined = [...incoming, ...unconfirmedPending];

        // Deduplicate messages by client_msg_id or id or timestamp+text
        const seen = new Set<string>();
        const deduped: MessageItem[] = [];
        for (const m of combined) {
          const key = m.client_msg_id || m.id || `${m.created_at}-${m.text.slice(0, 32)}`;
          if (!seen.has(key)) {
            seen.add(key);
            deduped.push(m);
          }
        }

        setMessages((prev) => {
          if (
            prev.length === deduped.length &&
            prev.length > 0 &&
            (prev[prev.length - 1]?.client_msg_id || prev[prev.length - 1]?.id) ===
              (deduped[deduped.length - 1]?.client_msg_id || deduped[deduped.length - 1]?.id)
          ) {
            return prev;
          }
          return deduped;
        });
      }
    } catch {
      // Offline / aborted tolerance
    } finally {
      clearTimeout(timeoutId);
      inFlightRef.current = false;
      if (!silent) {
        setLoadingMessages(false);
      }
    }
  }, [activeThreadId]);

  useEffect(() => {
    pendingMessagesRef.current.clear();
    if (activeChannelKey) {
      loadChannelMessages(activeChannelKey, false);
      const interval = setInterval(() => {
        loadChannelMessages(activeChannelKey, true);
      }, 4000);
      return () => clearInterval(interval);
    }
  }, [activeChannelKey, loadChannelMessages]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const activeThread = useMemo(
    () => threads.find((t) => t.channel_key === activeChannelKey) || threads[0],
    [threads, activeChannelKey]
  );

  const filteredThreads = useMemo(() => {
    if (!searchQuery.trim()) return threads;
    const q = searchQuery.toLowerCase();
    return threads.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        (t.subtitle && t.subtitle.toLowerCase().includes(q)) ||
        (t.active_ticket && t.active_ticket.key.toLowerCase().includes(q))
    );
  }, [threads, searchQuery]);

  const currentUserName = (user?.fullName || user?.username || '').toLowerCase();
  const currentUserEmail = (user?.email || '').toLowerCase();
  const currentUserId = (userId || '').toLowerCase();

  const botThreads = useMemo(
    () => filteredThreads.filter((t) => t.role === 'bot'),
    [filteredThreads]
  );

  // List ONLY other team members in Direct Messages (never list logged-in user to themselves)
  const dmThreads = useMemo(() => {
    return filteredThreads.filter((t) => {
      if (t.role === 'bot') return false;
      const titleLow = t.title.toLowerCase();
      const emailLow = (t.member?.email || '').toLowerCase();
      const idLow = (t.member?.id || '').toLowerCase();

      if (
        currentUserName &&
        (titleLow === currentUserName ||
          titleLow.includes(currentUserName) ||
          currentUserName.includes(titleLow))
      ) {
        return false;
      }
      if (currentUserEmail && emailLow === currentUserEmail) {
        return false;
      }
      if (currentUserId && idLow && idLow.includes(currentUserId)) {
        return false;
      }
      return true;
    });
  }, [filteredThreads, currentUserName, currentUserEmail, currentUserId]);

  // Find logged-in employee's assigned ticket for MY SPRINT TICKET card
  const myEmployeeTicket = useMemo(() => {
    for (const t of threads) {
      const member = t.member;
      const memName = (member?.name || t.title || '').toLowerCase();
      const memEmail = (member?.email || '').toLowerCase();
      const memId = (member?.id || '').toLowerCase();

      if (
        (currentUserName && (memName.includes(currentUserName) || currentUserName.includes(memName))) ||
        (currentUserEmail && memEmail === currentUserEmail) ||
        (currentUserId && memId && memId.includes(currentUserId))
      ) {
        if (t.active_ticket) return t.active_ticket;
      }
    }
    if (activeThread?.active_ticket && !isAdmin) return activeThread.active_ticket;
    const anyWithTicket = threads.find((t) => t.active_ticket);
    return anyWithTicket?.active_ticket || null;
  }, [threads, activeThread, currentUserName, currentUserEmail, currentUserId, isAdmin]);

  // Handle Send Message with Instant Optimistic UI Update (<10ms) & Double-Submit Guard
  const handleSendMessage = async (customText?: string) => {
    if (isSendingRef.current) return;
    const textToSend = (customText ?? inputText).trim();
    if (!textToSend) return;

    isSendingRef.current = true;
    setSending(true);

    const clientMsgId = `cmsg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    const optimisticMsg: MessageItem = {
      id: clientMsgId,
      client_msg_id: clientMsgId,
      sender: user?.fullName || user?.username || (isAdmin ? 'Manager' : 'You'),
      sender_id: userId || 'temp-id',
      role: isAdmin ? 'manager' : 'user',
      text: textToSend,
      created_at: new Date().toISOString(),
    };

    pendingMessagesRef.current.set(clientMsgId, optimisticMsg);
    setMessages((prev) => [...prev, optimisticMsg]);

    if (!customText) {
      setInputText('');
    }

    try {
      const res = await fetch(`/api/workos/messages/${encodeURIComponent(activeChannelKey)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: textToSend,
          thread_id: activeThreadId,
          task_id: activeThread?.active_ticket?.task_id,
          client_msg_id: clientMsgId,
        }),
      });

      if (res.ok) {
        pendingMessagesRef.current.delete(clientMsgId);
        try {
          const data = await res.json();
          if (data?.messages && Array.isArray(data.messages) && data.messages.length > 0) {
            setMessages((prev) => {
              const idSet = new Set(prev.map((m: any) => m.id));
              const clientIdSet = new Set(prev.map((m: any) => m.client_msg_id).filter(Boolean));
              const incoming = data.messages.filter(
                (m: any) => m.id && !idSet.has(m.id) && (!m.client_msg_id || !clientIdSet.has(m.client_msg_id))
              );
              const confirmedClientIds = new Set(data.messages.map((m: any) => m.client_msg_id).filter(Boolean));
              const filteredPrev = prev.filter((m: any) => !m._optimistic || !confirmedClientIds.has(m.client_msg_id));
              return [...filteredPrev, ...incoming];
            });
          }
        } catch {
          // Non-blocking parse error tolerance
        }
        loadChannelMessages(activeChannelKey, true);
        refreshState();
        loadThreads();
      }
    } catch {
      // Offline tolerance
    } finally {
      isSendingRef.current = false;
      setSending(false);
    }
  };

  // Manager-Only Check-In Trigger
  const handleCheckInTrigger = async () => {
    if (!isAdmin) return;
    setPingingUser('all');
    try {
      await fetch('/api/workos/checkin/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: activeThreadId }),
      });
      loadChannelMessages(activeChannelKey, true);
      loadThreads();
    } catch {
      // Ignore
    } finally {
      setPingingUser(null);
    }
  };

  // Quick Action Prompts
  const quickActions = useMemo(() => {
    if (isAdmin) {
      return [
        { label: 'Check in now', command: 'Check in with team now' },
        { label: 'Sprint status', command: 'Give me the sprint status summary' },
        { label: 'Explain policies', command: 'Explain SEC-POL-089 and SEC-POL-104' },
      ];
    }
    return [
      {
        label: '60% completed',
        command: '60% done: staging environment provisioned and API integration tests running.',
      },
      {
        label: 'Report blocker',
        command: 'Blocked on AWS IAM permissions for staging cluster.',
      },
      {
        label: 'Completed + PR',
        command: 'Task completed — PR https://github.com/example/repo/pull/42',
      },
    ];
  }, [isAdmin]);

  const activeIsOnLeave = (activeThread?.hr_status || '').toLowerCase().includes('leave');

  const handleDirectMessage = useCallback(
    (name: string) => {
      const targetEmp = dmThreads.find((t) => {
        const tName = t.title.toLowerCase();
        const bName = name.toLowerCase();
        return (
          (bName && (tName.includes(bName) || bName.includes(tName))) ||
          bName.includes(tName)
        );
      });
      if (targetEmp) {
        setActiveChannelKey(targetEmp.channel_key);
      }
    },
    [dmThreads]
  );

  const handleApproveTickets = useCallback(() => {
    handleSendMessage('Approve sprint tickets');
  }, [handleSendMessage]);

  return (
    <div className="flex h-full w-full overflow-hidden bg-dark-1 text-white rounded-none border-0">
      {/* ======================================================== */}
      {/* COLUMN 1: LEFT CONVERSATION RAIL (290px)                 */}
      {/* ======================================================== */}
      <aside className="flex w-[290px] shrink-0 flex-col border-r border-white/[0.08] bg-dark-1 h-full">
        {/* Header */}
        <div className="px-4 pt-4 pb-3 border-b border-white/[0.08]">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-semibold tracking-tight text-white">Messages</h2>
            </div>
            <span className="rounded bg-white/[0.06] px-2 py-0.5 text-[10px] font-mono text-white/50">
              {isAdmin ? 'Manager' : 'Member'}
            </span>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-2.5 size-4 text-white/40" />
            <input
              type="text"
              placeholder="Search messages..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-full border border-white/[0.07] bg-dark-2/90 py-2 pl-9 pr-3 text-sm text-white placeholder-white/35 focus:border-blue-1 focus:outline-none transition"
            />
          </div>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto px-2.5 py-3 space-y-4">
          {/* Section: Governance Bot */}
          <div>
            <div className="px-2 mb-1.5 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                Governance Bot
              </span>
              <Sparkles className="size-3 text-purple-400/60" />
            </div>

            {botThreads.map((t) => {
              const isSelected = activeChannelKey === t.channel_key;
              const lastMsgText =
                messages.length > 0 && activeChannelKey === t.channel_key
                  ? messages[messages.length - 1].text
                  : 'Automated Sprint Governance & Jira Execution';

              return (
                <button
                  key={t.channel_key}
                  type="button"
                  onClick={() => setActiveChannelKey(t.channel_key)}
                  className={cn(
                    'group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all',
                    isSelected
                      ? 'bg-blue-1 text-white shadow-sm'
                      : 'text-white/80 hover:bg-white/[0.05] hover:text-white'
                  )}
                >
                  <div className="relative flex size-10 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-purple-300">
                    <Bot className="size-5" />
                    <span className="absolute bottom-0 right-0 size-2.5 rounded-full bg-emerald-400 ring-2 ring-dark-1" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="truncate text-sm font-semibold">{t.title}</p>
                      {t.unread_count && t.unread_count > 0 ? (
                        <span className="rounded-full bg-emerald-500 px-1.5 py-0.2 text-[10px] font-bold text-black tabular-nums">
                          {t.unread_count}
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium opacity-50">Now</span>
                      )}
                    </div>
                    <p
                      className={cn(
                        'truncate text-xs mt-0.5',
                        isSelected ? 'text-white/85' : 'text-white/45'
                      )}
                    >
                      {lastMsgText}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Section: Direct Messages */}
          <div>
            <div className="px-2 mb-1.5 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                Direct Messages
              </span>
              <span className="text-[10px] font-mono text-white/30">{dmThreads.length}</span>
            </div>

            <div className="space-y-1">
              {dmThreads.length === 0 ? (
                <p className="px-2 text-xs text-white/30 italic">No teammates found</p>
              ) : (
                dmThreads.map((t) => {
                  const isSelected = activeChannelKey === t.channel_key;
                  const isOnLeave = (t.hr_status || '').toLowerCase().includes('leave');
                  const initials = t.title
                    .split(' ')
                    .map((n) => n[0])
                    .join('')
                    .slice(0, 2)
                    .toUpperCase();

                  return (
                    <button
                      key={t.channel_key}
                      type="button"
                      onClick={() => setActiveChannelKey(t.channel_key)}
                      className={cn(
                        'group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all',
                        isSelected
                          ? 'bg-blue-1 text-white shadow-sm'
                          : 'text-white/70 hover:bg-white/[0.05] hover:text-white'
                      )}
                    >
                      <div className="relative flex size-10 shrink-0 items-center justify-center rounded-full bg-dark-3 border border-white/[0.08] text-xs font-bold text-white">
                        {initials}
                        <span
                          className={cn(
                            'absolute bottom-0 right-0 size-2.5 rounded-full ring-2 ring-dark-1',
                            isOnLeave ? 'bg-amber-400' : 'bg-emerald-400'
                          )}
                          title={isOnLeave ? 'On Leave' : 'Active'}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <p className="truncate text-sm font-medium text-white">{t.title}</p>
                          {t.unread_count && t.unread_count > 0 ? (
                            <span className="rounded-full bg-emerald-500 px-1.5 py-0.2 text-[10px] font-bold text-black tabular-nums">
                              {t.unread_count}
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          {t.active_ticket ? (
                            <span className="truncate text-xs text-sky-300 font-mono">
                              {t.active_ticket.key} • {t.active_ticket.title}
                            </span>
                          ) : (
                            <span
                              className={cn(
                                'truncate text-xs',
                                isSelected ? 'text-white/80' : 'text-white/45'
                              )}
                            >
                              {t.subtitle || (isOnLeave ? 'On Leave' : 'Active')}
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* User Identity Footer */}
        <div className="p-3.5 border-t border-white/[0.08] bg-dark-1 flex items-center justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-blue-1/20 text-xs font-bold text-blue-300">
              {(user?.fullName || user?.username || 'U')[0].toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-white">
                {user?.fullName || user?.username || 'You'}
              </p>
              <p className="truncate text-[10px] text-white/40">{isAdmin ? 'Org Admin' : 'Org Member'}</p>
            </div>
          </div>
          <span className="size-2 rounded-full bg-emerald-400" title="Online" />
        </div>
      </aside>

      {/* ======================================================== */}
      {/* COLUMN 2: CENTER CONVERSATION STREAM                     */}
      {/* ======================================================== */}
      <main className="flex flex-1 flex-col h-full overflow-hidden bg-dark-1 min-w-0">
        {/* Header */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.08] px-6 bg-dark-1">
          <div className="flex items-center gap-3 min-w-0">
            <div className="relative flex size-10 shrink-0 items-center justify-center rounded-full bg-dark-3 border border-white/[0.08]">
              {activeThread?.role === 'bot' ? (
                <Bot className="size-5 text-purple-300" />
              ) : (
                <span className="text-sm font-bold text-white">
                  {(activeThread?.title || 'U')[0].toUpperCase()}
                </span>
              )}
              <span
                className={cn(
                  'absolute bottom-0 right-0 size-2.5 rounded-full ring-2 ring-dark-1',
                  activeIsOnLeave ? 'bg-amber-400' : 'bg-emerald-400'
                )}
              />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="truncate text-sm font-bold text-white">{activeThread?.title}</h3>
                <span
                  className={cn(
                    'rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                    activeThread?.role === 'bot'
                      ? 'bg-purple-500/20 text-purple-300'
                      : activeIsOnLeave
                      ? 'bg-amber-500/15 border border-amber-500/20 text-amber-300'
                      : 'bg-emerald-500/20 text-emerald-300'
                  )}
                >
                  {activeThread?.role === 'bot'
                    ? 'Verified Bot'
                    : activeIsOnLeave
                    ? 'On Leave'
                    : 'Active'}
                </span>
              </div>
              <p className="truncate text-xs text-white/45">
                {activeThread?.role === 'bot'
                  ? 'Online • Governance & Sprint Bot'
                  : `${activeIsOnLeave ? 'On Leave' : 'Active'} • ${activeThread?.subtitle || 'Platform Engineer'}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Quick Check-In Trigger - Manager ONLY */}
            {isAdmin && (
              <button
                type="button"
                disabled={pingingUser !== null}
                onClick={handleCheckInTrigger}
                className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-1/15 px-3 py-1.5 text-xs font-semibold text-blue-200 transition hover:bg-blue-1 hover:text-white disabled:opacity-40"
                title="Trigger sprint check-in across all assigned engineers"
              >
                {pingingUser === 'all' ? (
                  <RefreshCw className="size-3.5 animate-spin text-blue-400" />
                ) : (
                  <Zap className="size-3.5 text-blue-400" />
                )}
                <span>Check-In All</span>
              </button>
            )}

            {/* Open in Slack */}
            <a
              href={activeThread?.slack_deep_link || 'https://app.slack.com/client'}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg border border-white/[0.12] bg-white/[0.05] px-3 py-1.5 text-xs font-medium text-white/80 transition hover:bg-white/[0.1] hover:text-white"
            >
              <span>Open in Slack</span>
              <ExternalLink className="size-3 text-white/50" />
            </a>

            {/* Toggle Right Drawer */}
            <button
              type="button"
              onClick={() => setShowRightDrawer((prev) => !prev)}
              title={showRightDrawer ? 'Hide Profile Drawer' : 'Show Profile Drawer'}
              className="rounded-lg p-2 text-white/50 hover:bg-white/[0.08] hover:text-white transition"
            >
              {showRightDrawer ? (
                <PanelRightClose className="size-4" />
              ) : (
                <PanelRightOpen className="size-4" />
              )}
            </button>
          </div>
        </header>

        {/* Message Thread */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {/* Centered Date Separator Pill */}
          <div className="flex items-center justify-center my-2">
            <span className="rounded-full border border-white/[0.07] bg-dark-2 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              TODAY
            </span>
          </div>

          {messages.length === 0 ? (
            <div className="flex h-64 flex-col items-center justify-center text-center p-8">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-white/[0.05] text-white/40 mb-3">
                <MessageSquare className="size-6" />
              </div>
              <h4 className="text-sm font-semibold text-white">No messages yet</h4>
              <p className="mt-1 max-w-sm text-xs text-white/50">
                {isAdmin
                  ? 'No messages yet — send a command or trigger a sprint check-in below.'
                  : 'No messages yet — your assigned sprint check-ins and bot responses will appear here.'}
              </p>
            </div>
          ) : (
            messages.map((m) => {
              const isBot = m.role === 'bot' || m.sender === 'Veridian Bot';
              const isCurrentUser =
                m.sender_id === userId ||
                (user?.fullName && m.sender === user.fullName) ||
                m.role === 'user' ||
                (isAdmin && m.role === 'manager' && m.sender !== 'Veridian Bot');

              return (
                <MessageBubble
                  key={m.id || `${m.created_at}-${m.text.slice(0, 10)}`}
                  m={m}
                  isCurrentUser={Boolean(isCurrentUser)}
                  isBot={Boolean(isBot)}
                  isAdmin={Boolean(isAdmin)}
                  onDirectMessage={handleDirectMessage}
                  onApproveTickets={handleApproveTickets}
                  sending={sending}
                />
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Flush Bottom Composer */}
        <div className="border-t border-white/[0.08] bg-dark-1 px-5 py-3.5">
          {/* Quick-Prompt Pills */}
          <div className="mb-2.5 flex items-center gap-2">
            {quickActions.map((action) => (
              <button
                key={action.label}
                type="button"
                disabled={sending}
                onClick={() => handleSendMessage(action.command)}
                className="flex items-center gap-1.5 rounded-full border border-white/[0.07] bg-dark-3/70 px-3 py-1 text-[11px] font-medium text-white/70 transition hover:border-blue-1/50 hover:bg-white/[0.08] hover:text-white disabled:opacity-40"
              >
                <Clock className="size-3 text-blue-300" />
                <span>{action.label}</span>
              </button>
            ))}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex items-center gap-2"
          >
            <div className="flex-1 flex items-center rounded-full border border-white/[0.08] bg-dark-2 px-4 py-2.5 focus-within:border-blue-1 transition">
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder={
                  activeThread?.role === 'bot'
                    ? isAdmin
                      ? "Message Veridian Bot or enter command (e.g. 'Check in with team now')..."
                      : "Reply to Veridian Bot with your progress or completion evidence..."
                    : `Message ${activeThread?.title} directly (synced to Slack)...`
                }
                className="w-full bg-transparent text-sm text-white placeholder-white/35 focus:outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={sending || !inputText.trim()}
              className="flex size-10 shrink-0 items-center justify-center rounded-full bg-blue-1 text-white shadow-lg transition hover:bg-blue-1/90 disabled:opacity-40"
            >
              {sending ? <RefreshCw className="size-4 animate-spin" /> : <Send className="size-4" />}
            </button>
          </form>
        </div>
      </main>

      {/* ======================================================== */}
      {/* COLUMN 3: RIGHT PROFILE & LIVE SPRINT DRAWER (310px)     */}
      {/* ======================================================== */}
      {showRightDrawer && (
        <aside className="w-[310px] shrink-0 border-l border-white/[0.08] bg-dark-1 flex flex-col h-full overflow-y-auto">
          {/* Centered Profile Header */}
          <div className="px-5 pt-6 pb-5 border-b border-white/[0.08] text-center">
            <div className="relative mx-auto flex size-16 items-center justify-center rounded-full bg-dark-3 border border-white/[0.1] shadow-md">
              {activeThread?.role === 'bot' ? (
                <Bot className="size-8 text-purple-300" />
              ) : (
                <span className="text-xl font-bold text-white">
                  {(activeThread?.title || 'U')[0].toUpperCase()}
                </span>
              )}
              <span
                className={cn(
                  'absolute bottom-0 right-0 size-3.5 rounded-full ring-2 ring-dark-1',
                  activeIsOnLeave ? 'bg-amber-400' : 'bg-emerald-400'
                )}
              />
            </div>

            <h3 className="text-base font-bold text-white mt-3">{activeThread?.title}</h3>
            <p className="text-xs text-white/50 mt-0.5">
              {activeThread?.role === 'bot'
                ? 'Governance & Sprint Assistant'
                : `${activeThread?.subtitle || 'Backend Engineer'} • ${activeIsOnLeave ? 'On Paternity Leave' : 'Active'}`}
            </p>

            {/* Quick-Action Icon Buttons */}
            <div className="mt-4 flex items-center justify-center gap-3">
              {/* 1. Open Slack */}
              <a
                href={activeThread?.slack_deep_link || 'https://app.slack.com/client'}
                target="_blank"
                rel="noreferrer"
                title="Open in Slack"
                className="flex size-9 items-center justify-center rounded-full bg-dark-3/80 border border-white/[0.08] text-white/70 hover:text-white hover:border-white/[0.2] transition"
              >
                <ExternalLink className="size-4" />
              </a>

              {/* 2. Ping Check-In - Manager ONLY */}
              {isAdmin && (
                <button
                  type="button"
                  disabled={activeIsOnLeave || pingingUser !== null}
                  onClick={handleCheckInTrigger}
                  title="Trigger sprint check-in DMs"
                  className="flex size-9 items-center justify-center rounded-full bg-dark-3/80 border border-white/[0.08] text-white/70 hover:text-amber-400 hover:border-white/[0.2] transition disabled:opacity-30"
                >
                  {pingingUser ? (
                    <RefreshCw className="size-4 animate-spin text-blue-400" />
                  ) : (
                    <Zap className="size-4" />
                  )}
                </button>
              )}

              {/* 3. Open Jira */}
              <Link
                href={activeThread?.active_ticket?.jira_url || '/workos'}
                title="View in Jira"
                className="flex size-9 items-center justify-center rounded-full bg-dark-3/80 border border-white/[0.08] text-white/70 hover:text-sky-400 hover:border-white/[0.2] transition"
              >
                <Ticket className="size-4" />
              </Link>
            </div>
          </div>

          {/* Structured Info Sections */}
          <div className="px-4 py-4 space-y-4">
            {/* Section 1: Live Jira & Sprint Progress */}
            <div>
              {isAdmin ? (
                // Manager/Bot Overview: Team sprint progress rows
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-bold uppercase tracking-wider text-white/50">
                      Team Sprint Progress
                    </span>
                    <button
                      type="button"
                      disabled={pingingUser !== null}
                      onClick={handleCheckInTrigger}
                      className="flex items-center gap-1 rounded-md border border-blue-500/30 bg-blue-1/15 px-2 py-0.5 text-[10px] font-semibold text-blue-200 transition hover:bg-blue-1 hover:text-white disabled:opacity-40"
                    >
                      {pingingUser === 'all' ? (
                        <RefreshCw className="size-2.5 animate-spin" />
                      ) : (
                        <Zap className="size-2.5 text-blue-400" />
                      )}
                      <span>Check-In All</span>
                    </button>
                  </div>

                  <div className="space-y-2.5">
                    {dmThreads.map((t) => {
                      const isOnLeave = (t.hr_status || '').toLowerCase().includes('leave');
                      const ticket = t.active_ticket;
                      const isBlocked = ticket?.status === 'BLOCKED';
                      const isDone = ticket?.status === 'DONE' || ticket?.progress_pct === 100;
                      const isInProgress = ticket?.status === 'IN_PROGRESS' || (ticket && ticket.progress_pct > 0 && !isDone);

                      return (
                        <div
                          key={t.channel_key}
                          className="rounded-xl border border-white/[0.07] bg-dark-3/50 p-3 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-white">{t.title}</span>
                            <span
                              className={cn(
                                'rounded px-1.5 py-0.2 text-[9px] font-bold uppercase',
                                isOnLeave
                                  ? 'bg-amber-500/15 border border-amber-500/20 text-amber-300'
                                  : isDone
                                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                  : isBlocked
                                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                                  : isInProgress
                                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                  : ticket
                                  ? 'bg-sky-500/20 text-sky-300'
                                  : 'bg-white/[0.06] text-white/40 border border-white/[0.08]'
                              )}
                            >
                              {isOnLeave ? 'ON LEAVE' : (ticket?.status || t.status || 'IDLE').replace('_', ' ')}
                            </span>
                          </div>

                          <div className="mt-2 flex items-center justify-between text-[11px]">
                            <span
                              className={cn(
                                'font-bold',
                                ticket?.key ? 'font-mono text-sky-300' : 'text-white/40 font-normal text-[11px]'
                              )}
                            >
                              {ticket?.key || 'No active ticket'}
                            </span>
                            <span className="text-white/50">{ticket ? `${ticket.progress_pct}%` : '0%'}</span>
                          </div>

                          <div className="mt-1 h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                            <div
                              className={cn(
                                'h-full transition-all duration-300',
                                isOnLeave
                                  ? 'bg-amber-400'
                                  : isDone
                                  ? 'bg-emerald-400'
                                  : isBlocked
                                  ? 'bg-rose-500'
                                  : isInProgress
                                  ? 'bg-amber-400'
                                  : 'bg-blue-1'
                              )}
                              style={{ width: `${ticket ? ticket.progress_pct : 0}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                // Employee View: MY SPRINT TICKET
                <div>
                  <div className="mb-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-white/50">
                      My Sprint Ticket
                    </span>
                  </div>

                  {myEmployeeTicket ? (
                    <div className="rounded-xl border border-sky-400/30 bg-dark-3/50 p-3.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-bold text-sky-300">
                          {myEmployeeTicket.key}
                        </span>
                        <span
                          className={cn(
                            'rounded px-1.5 py-0.2 text-[9px] font-bold uppercase',
                            myEmployeeTicket.status === 'DONE' || myEmployeeTicket.progress_pct === 100
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                              : myEmployeeTicket.status === 'BLOCKED'
                              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                              : myEmployeeTicket.status === 'IN_PROGRESS' || myEmployeeTicket.progress_pct > 0
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              : 'bg-sky-500/20 text-sky-200'
                          )}
                        >
                          {myEmployeeTicket.status.replace('_', ' ')}
                        </span>
                      </div>
                      <h4 className="mt-2 text-xs font-semibold text-white">
                        {myEmployeeTicket.title}
                      </h4>

                      <div className="mt-3">
                        <div className="flex items-center justify-between text-[10px] text-white/50 mb-1">
                          <span>Progress</span>
                          <span className="font-mono">{myEmployeeTicket.progress_pct}%</span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                          <div
                            className="h-full bg-blue-1 transition-all duration-300"
                            style={{ width: `${myEmployeeTicket.progress_pct}%` }}
                          />
                        </div>
                      </div>

                      {myEmployeeTicket.jira_url && (
                        <a
                          href={myEmployeeTicket.jira_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-3.5 flex items-center justify-center gap-1.5 rounded-lg bg-blue-1 py-1.5 text-xs font-semibold text-white shadow transition hover:bg-blue-1/90"
                        >
                          <span>View in Jira</span>
                          <ExternalLink className="size-3" />
                        </a>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-white/[0.07] bg-dark-3/50 p-4 text-center">
                      <p className="text-xs text-white/60">
                        {activeIsOnLeave
                          ? 'You are currently on approved leave.'
                          : 'No active sprint ticket assigned. Waiting for sprint approval.'}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Section 2: Workspace & Slack Sync Info */}
            <div className="rounded-xl border border-white/[0.07] bg-dark-3/40 p-3 text-xs space-y-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-white/50">
                Workspace Status
              </span>
              <div className="flex items-center justify-between text-[11px] text-white/70">
                <span>Slack Sync</span>
                <span className="font-mono text-emerald-400 font-medium">Synced every 2.5s</span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-white/70">
                <span>Governance Engine</span>
                <span className="font-mono text-blue-300 font-medium">Active</span>
              </div>
              <div className="pt-1 border-t border-white/[0.06]">
                <Link
                  href="/workos"
                  className="flex items-center justify-between text-[11px] text-blue-300 hover:text-blue-200 transition"
                >
                  <span>Open WorkOS Hub</span>
                  <ChevronRight className="size-3" />
                </Link>
              </div>
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}
