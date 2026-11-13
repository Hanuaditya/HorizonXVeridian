'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { OrgOnboardingGuard, useAppAuth } from '@/providers/AuthBridge';
import { useAgentStream } from '@/lib/sse';
import {
  AlertTriangle,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  MessageSquare,
  RefreshCw,
  Search,
  Send,
  Shield,
  ShieldAlert,
  Sparkles,
  User,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface MessageItem {
  id: string;
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

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // SSE Stream for live event push
  const { agentState, refreshState } = useAgentStream(activeThreadId);

  // 1. Load threads
  const loadThreads = async () => {
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
  };

  useEffect(() => {
    loadThreads();
    const interval = setInterval(loadThreads, 4000);
    return () => clearInterval(interval);
  }, []);

  // 2. Load messages for active channel
  const loadChannelMessages = async (chKey: string) => {
    setLoadingMessages(true);
    try {
      const qs = activeThreadId ? `?thread_id=${encodeURIComponent(activeThreadId)}` : '';
      const res = await fetch(`/api/workos/messages/${encodeURIComponent(chKey)}${qs}`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch {
      // Offline tolerance
    } finally {
      setLoadingMessages(false);
    }
  };

  useEffect(() => {
    if (activeChannelKey) {
      loadChannelMessages(activeChannelKey);
      const interval = setInterval(() => {
        loadChannelMessages(activeChannelKey);
      }, 3000);
      return () => clearInterval(interval);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChannelKey, activeThreadId]);

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

  const botThreads = useMemo(() => filteredThreads.filter((t) => t.role === 'bot'), [filteredThreads]);
  const dmThreads = useMemo(() => filteredThreads.filter((t) => t.role !== 'bot'), [filteredThreads]);

  // Handle Send
  const handleSendMessage = async (customText?: string) => {
    const textToSend = (customText ?? inputText).trim();
    if (!textToSend || sending) return;

    setSending(true);
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
        }),
      });

      if (res.ok) {
        await loadChannelMessages(activeChannelKey);
        await refreshState();
        await loadThreads();
      }
    } catch {
      // Ignore network errors
    } finally {
      setSending(false);
    }
  };

  // Handle Manager Ping Check-In for specific employee
  const handlePingEmployee = async (empName: string) => {
    setPingingUser(empName);
    try {
      if (activeThreadId) {
        await fetch(`/api/workos/threads/${encodeURIComponent(activeThreadId)}/checkin`, {
          method: 'POST',
        });
      }
      await loadChannelMessages('veridian-bot');
      await refreshState();
      await loadThreads();
    } catch {
      // Ignore
    } finally {
      setPingingUser(null);
    }
  };

  // Handle Check-In All
  const handleCheckInAll = async () => {
    setPingingUser('all');
    try {
      await handleSendMessage('Check in with team now');
    } finally {
      setPingingUser(null);
    }
  };

  const quickActions = useMemo(() => {
    if (isAdmin) {
      return [
        { label: 'Check-in now', command: 'Check in with team now' },
        { label: 'Sprint digest', command: 'Check sprint status digest' },
      ];
    }
    return [
      {
        label: 'Check-in now',
        command: 'Check-in update: on track with sprint deliverables',
      },
      {
        label: 'Sprint digest',
        command: 'Sprint digest: verifying completed tasks and Jira status',
      },
    ];
  }, [isAdmin]);

  return (
    <div className="flex h-[calc(100vh-100px)] w-full overflow-hidden rounded-2xl border border-white/[0.07] bg-dark-1 text-white shadow-2xl">
      {/* ======================================================== */}
      {/* COLUMN 1: LEFT RAIL (260px) - CONVERSATIONS & DMs       */}
      {/* ======================================================== */}
      <aside className="flex w-[260px] flex-col border-r border-white/[0.07] bg-dark-1">
        {/* Header & Filter */}
        <div className="p-3.5 border-b border-white/[0.07]">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="flex size-7 items-center justify-center rounded-lg bg-blue-1/20 text-blue-400">
                <MessageSquare className="size-4" />
              </div>
              <h2 className="text-sm font-semibold tracking-tight text-white">Messages</h2>
            </div>
            <span className="rounded bg-white/[0.06] px-2 py-0.5 text-[10px] font-mono text-white/50">
              {isAdmin ? 'Manager' : 'Employee'}
            </span>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-2 size-3.5 text-white/40" />
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-white/[0.07] bg-dark-3/70 py-1.5 pl-8 pr-2.5 text-xs text-white placeholder-white/30 focus:border-blue-1 focus:outline-none"
            />
          </div>
        </div>

        {/* Scrollable Channels List */}
        <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
          {/* Bots Section (Pinned Veridian Bot) */}
          <div>
            <div className="px-2 mb-1.5 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                Governance Bot
              </span>
              <Sparkles className="size-3 text-purple-400/60" />
            </div>
            {botThreads.map((t) => {
              const isSelected = activeChannelKey === t.channel_key;
              return (
                <button
                  key={t.channel_key}
                  type="button"
                  onClick={() => setActiveChannelKey(t.channel_key)}
                  className={cn(
                    'group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-all',
                    isSelected
                      ? 'bg-blue-1 text-white shadow-sm'
                      : 'text-white/80 hover:bg-white/[0.05] hover:text-white'
                  )}
                >
                  <div className="relative flex size-7 shrink-0 items-center justify-center rounded-lg bg-purple-500/20 text-purple-300">
                    <Bot className="size-4" />
                    <span className="absolute -bottom-0.5 -right-0.5 size-2 rounded-full bg-emerald-400 ring-2 ring-dark-1" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="truncate text-xs font-semibold">{t.title}</p>
                      {t.unread_count && t.unread_count > 0 ? (
                        <span className="rounded-full bg-emerald-500 px-1.5 py-0.2 text-[10px] font-bold text-black tabular-nums">
                          {t.unread_count}
                        </span>
                      ) : null}
                    </div>
                    <p className={cn('truncate text-[10px]', isSelected ? 'text-white/80' : 'text-white/45')}>
                      {t.subtitle}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Direct Messages Section */}
          <div>
            <div className="px-2 mb-1.5 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                Direct Messages
              </span>
              <span className="text-[10px] font-mono text-white/30">{dmThreads.length}</span>
            </div>
            <div className="space-y-1">
              {dmThreads.length === 0 ? (
                <p className="px-2 text-[11px] text-white/30 italic">No team DMs active</p>
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
                        'group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-all',
                        isSelected
                          ? 'bg-white/[0.12] text-white'
                          : 'text-white/70 hover:bg-white/[0.05] hover:text-white'
                      )}
                    >
                      <div className="relative flex size-7 shrink-0 items-center justify-center rounded-lg bg-white/[0.08] text-xs font-bold text-white/90">
                        {initials}
                        <span
                          className={cn(
                            'absolute -bottom-0.5 -right-0.5 size-2 rounded-full ring-2 ring-dark-1',
                            isOnLeave ? 'bg-amber-400' : 'bg-emerald-400'
                          )}
                          title={isOnLeave ? 'On Paternity/Medical Leave' : 'Active'}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <p className="truncate text-xs font-medium">{t.title}</p>
                          {t.unread_count && t.unread_count > 0 ? (
                            <span className="rounded-full bg-emerald-500 px-1.5 py-0.2 text-[10px] font-bold text-black tabular-nums">
                              {t.unread_count}
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-1.5">
                          {t.active_ticket ? (
                            <span className="rounded bg-sky-500/15 px-1 py-0.2 font-mono text-[9px] font-semibold text-sky-300">
                              {t.active_ticket.key}
                            </span>
                          ) : (
                            <span className="truncate text-[10px] text-white/40">{t.subtitle}</span>
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
        <div className="p-3 border-t border-white/[0.07] bg-dark-2 flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-blue-1/20 text-[10px] font-bold text-blue-300">
              {(user?.fullName || user?.username || 'U')[0].toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-white/90">
                {user?.fullName || user?.username || 'Current User'}
              </p>
              <p className="truncate text-[10px] font-mono text-white/40">{orgRole || 'org:member'}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={loadThreads}
            title="Refresh Threads"
            className="rounded p-1 text-white/40 hover:bg-white/[0.08] hover:text-white"
          >
            <RefreshCw className="size-3.5" />
          </button>
        </div>
      </aside>

      {/* ======================================================== */}
      {/* COLUMN 2: CENTER CANVAS - MAIN THREAD & CHAT VIEW        */}
      {/* ======================================================== */}
      <main className="flex flex-1 flex-col min-w-0 bg-dark-2">
        {/* Thread Header */}
        <header className="flex h-14 items-center justify-between border-b border-white/[0.07] px-5 bg-dark-1">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-blue-1/20 text-blue-300">
              {activeThread?.role === 'bot' ? <Bot className="size-4" /> : <User className="size-4" />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="truncate text-sm font-bold text-white">{activeThread?.title}</h3>
                <span
                  className={cn(
                    'rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                    activeThread?.role === 'bot'
                      ? 'bg-purple-500/20 text-purple-300'
                      : (activeThread?.hr_status || '').toLowerCase().includes('leave')
                      ? 'bg-amber-500/15 border border-amber-500/20 text-amber-300/90'
                      : 'bg-emerald-500/20 text-emerald-300'
                  )}
                >
                  {activeThread?.role === 'bot'
                    ? 'Governance Bot'
                    : (activeThread?.hr_status || '').toLowerCase().includes('leave')
                    ? 'On Leave'
                    : 'Active'}
                </span>
              </div>
              <p className="truncate text-[11px] text-white/45">
                {activeThread?.subtitle || 'Direct Conversation'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeThread?.active_ticket && (
              <a
                href={activeThread.active_ticket.jira_url || '#'}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 rounded-lg border border-sky-400/20 bg-sky-500/10 px-2.5 py-1 text-xs font-mono font-medium text-sky-300 transition hover:bg-sky-500/20"
              >
                <span>{activeThread.active_ticket.key}</span>
                <span className="rounded bg-sky-500/20 px-1 py-0.2 text-[9px]">
                  {activeThread.active_ticket.status}
                </span>
                <ExternalLink className="size-3" />
              </a>
            )}

            <a
              href={activeThread?.slack_deep_link || 'https://app.slack.com/client'}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg border border-white/[0.12] bg-white/[0.05] px-3 py-1.5 text-xs font-medium text-white/80 transition hover:bg-white/[0.1] hover:text-white"
            >
              <span>Open in Slack</span>
              <ExternalLink className="size-3 text-white/50" />
            </a>
          </div>
        </header>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center p-8">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-white/[0.05] text-white/40 mb-3">
                <MessageSquare className="size-6" />
              </div>
              <h4 className="text-sm font-semibold text-white">No messages yet</h4>
              <p className="mt-1 max-w-sm text-xs text-white/50">
                No messages yet — send a message or trigger a sprint check-in below.
              </p>
              {loadingMessages && (
                <span className="mt-2 flex items-center gap-1 text-[10px] text-white/30">
                  <RefreshCw className="size-2.5 animate-spin" /> Checking stream...
                </span>
              )}
            </div>
          ) : (
            messages.map((m) => {
              const isBot = m.role === 'bot' || m.sender === 'Veridian Bot';
              const isCurrentUser =
                m.sender_id === userId ||
                (user?.fullName && m.sender === user.fullName);
              const isAlert = m.kind === 'alert' || m.kind === 'compliance_alert';
              const isReviewMenu = m.kind === 'review_menu';
              const isDigest = m.kind === 'progress_digest' || m.kind === 'closure_confirmation';

              return (
                <div
                  key={m.id || `${m.created_at}-${m.text.slice(0, 10)}`}
                  className={cn('flex gap-3', isCurrentUser ? 'justify-end' : 'justify-start')}
                >
                  {!isCurrentUser && (
                    <div
                      className={cn(
                        'flex size-8 shrink-0 items-center justify-center rounded-xl text-xs font-bold shadow-sm',
                        isBot
                          ? 'bg-purple-600/30 text-purple-200 border border-purple-500/30'
                          : 'bg-white/[0.08] text-white/80 border border-white/[0.1]'
                      )}
                    >
                      {isBot ? <Bot className="size-4" /> : (m.sender || 'U')[0].toUpperCase()}
                    </div>
                  )}

                  <div className={cn('flex max-w-[82%] flex-col', isCurrentUser ? 'items-end' : 'items-start')}>
                    <div className="mb-1 flex items-center gap-2 text-[10px] text-white/40">
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

                    {/* Message Bubble or Structured Card */}
                    {isAlert ? (
                      <div className="rounded-xl border border-rose-500/30 bg-rose-500/[0.08] p-3.5 text-xs text-rose-200 shadow-md">
                        <div className="flex items-center gap-2 font-semibold text-rose-300 mb-1.5">
                          <ShieldAlert className="size-4" />
                          <span>Immediate Compliance Alert</span>
                        </div>
                        <div className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-white/90">
                          {m.text}
                        </div>
                      </div>
                    ) : isReviewMenu ? (
                      <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.08] p-3.5 text-xs text-amber-200 shadow-md">
                        <div className="flex items-center gap-2 font-semibold text-amber-300 mb-1.5">
                          <Shield className="size-4" />
                          <span>Manager Review & Governance Gate</span>
                        </div>
                        <div className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-white/90">
                          {m.text}
                        </div>
                      </div>
                    ) : isDigest ? (
                      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/[0.08] p-3.5 text-xs text-emerald-200 shadow-md">
                        <div className="flex items-center gap-2 font-semibold text-emerald-300 mb-1.5">
                          <CheckCircle2 className="size-4" />
                          <span>Sprint Progress & Jira Status Digest</span>
                        </div>
                        <div className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-white/90">
                          {m.text}
                        </div>
                      </div>
                    ) : (
                      <div
                        className={cn(
                          'rounded-2xl px-4 py-2.5 text-xs leading-relaxed shadow-sm whitespace-pre-wrap',
                          isCurrentUser
                            ? 'bg-blue-1 text-white rounded-tr-sm'
                            : 'bg-dark-3/70 border border-white/[0.07] text-white/90 rounded-tl-sm'
                        )}
                      >
                        {m.text}
                      </div>
                    )}
                  </div>

                  {isCurrentUser && (
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-blue-1 text-xs font-bold text-white shadow-sm">
                      {(user?.fullName || user?.username || 'Me')[0].toUpperCase()}
                    </div>
                  )}
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Composer & Quick Actions */}
        <div className="border-t border-white/[0.07] bg-dark-1 p-4">
          {/* Quick Action Pills: 2 Native Pills */}
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
            className="flex items-end gap-2"
          >
            <div className="flex-1 rounded-xl border border-white/[0.07] bg-dark-3/70 px-3.5 py-2.5 focus-within:border-blue-1">
              <textarea
                rows={2}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder={
                  activeThread?.role === 'bot'
                    ? isAdmin
                      ? "Message Veridian Bot or enter command (e.g. 'Check in with team now')..."
                      : "Reply to Veridian Bot with your progress or completion evidence..."
                    : `Message ${activeThread?.title} directly (synced to Slack)...`
                }
                className="w-full resize-none bg-transparent text-xs text-white placeholder-white/35 focus:outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={sending || !inputText.trim()}
              className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-blue-1 text-white shadow-lg transition hover:bg-blue-1/90 disabled:opacity-40"
            >
              {sending ? <RefreshCw className="size-4 animate-spin" /> : <Send className="size-4" />}
            </button>
          </form>
        </div>
      </main>

      {/* ======================================================== */}
      {/* COLUMN 3: RIGHT CONTEXT DRAWER (280px)                   */}
      {/* ======================================================== */}
      <aside className="hidden w-[280px] flex-col border-l border-white/[0.07] bg-dark-1 xl:flex">
        {isAdmin ? (
          // Manager Right Panel: Live Team Sprint Status
          <div className="flex h-full flex-col">
            <div className="border-b border-white/[0.07] p-4 flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">
                  Team Sprint Status
                </h3>
                <p className="mt-0.5 text-[11px] text-white/40">
                  Live capacity, leave checks & Jira progress
                </p>
              </div>
              <button
                type="button"
                disabled={pingingUser !== null}
                onClick={handleCheckInAll}
                className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-1/15 px-2.5 py-1 text-[11px] font-semibold text-blue-200 transition hover:bg-blue-1 hover:text-white disabled:opacity-40"
                title="Dispatch 1-on-1 sprint check-in DMs to all active team members"
              >
                {pingingUser === 'all' ? (
                  <RefreshCw className="size-3 animate-spin" />
                ) : (
                  <Zap className="size-3 text-blue-400" />
                )}
                <span>Check-In All</span>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {threads
                .filter((t) => t.role !== 'bot')
                .map((t) => {
                  const isOnLeave = (t.hr_status || '').toLowerCase().includes('leave');
                  const ticket = t.active_ticket;

                  return (
                    <div
                      key={t.channel_key}
                      className="group rounded-xl border border-white/[0.07] bg-dark-3/50 p-3 text-xs transition hover:border-white/[0.12]"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">{t.title}</span>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={cn(
                              'rounded px-1.5 py-0.2 text-[9px] font-bold uppercase',
                              isOnLeave
                                ? 'bg-amber-500/15 border border-amber-500/20 text-amber-300/90'
                                : 'bg-emerald-500/20 text-emerald-300'
                            )}
                          >
                            {isOnLeave ? 'On Leave' : 'Active'}
                          </span>
                          {!isOnLeave && (
                            <button
                              type="button"
                              disabled={pingingUser === t.title}
                              onClick={() => handlePingEmployee(t.title)}
                              title={`Send check-in ping to ${t.title}`}
                              className="rounded p-1 text-white/40 opacity-60 transition hover:bg-white/[0.08] hover:text-blue-300 hover:opacity-100 disabled:opacity-40"
                            >
                              {pingingUser === t.title ? (
                                <RefreshCw className="size-3 animate-spin text-blue-400" />
                              ) : (
                                <Zap className="size-3" />
                              )}
                            </button>
                          )}
                        </div>
                      </div>
                      <p className="mt-0.5 text-[10px] text-white/45">{t.subtitle}</p>

                      {ticket ? (
                        <div className="mt-2.5 rounded-lg border border-white/[0.07] bg-dark-2 p-2">
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="font-mono font-bold text-sky-300">{ticket.key}</span>
                            <span className="text-white/60">{ticket.status}</span>
                          </div>
                          <p className="mt-1 truncate text-[11px] text-white/80">{ticket.title}</p>
                          <div className="mt-2 flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-white/10 overflow-hidden">
                              <div
                                className="h-full bg-blue-1 transition-all duration-300"
                                style={{ width: `${ticket.progress_pct}%` }}
                              />
                            </div>
                            <span className="font-mono text-[9px] text-white/60">
                              {ticket.progress_pct}%
                            </span>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 text-[11px] text-white/30 italic">
                          No Jira ticket active
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          </div>
        ) : (
          // Employee Right Panel: My Assigned Tickets
          <div className="flex h-full flex-col">
            <div className="border-b border-white/[0.07] p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">
                My Assigned Tickets
              </h3>
              <p className="mt-0.5 text-[11px] text-white/40">
                Jira tasks assigned to you this sprint
              </p>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {activeThread?.active_ticket ? (
                <div className="rounded-xl border border-sky-400/30 bg-dark-3/50 p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-sky-300">
                      {activeThread.active_ticket.key}
                    </span>
                    <span className="rounded bg-sky-500/20 px-1.5 py-0.2 text-[9px] font-bold text-sky-200">
                      {activeThread.active_ticket.status}
                    </span>
                  </div>
                  <h4 className="mt-1.5 text-xs font-semibold text-white">
                    {activeThread.active_ticket.title}
                  </h4>
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[10px] text-white/50 mb-1">
                      <span>Progress</span>
                      <span className="font-mono">{activeThread.active_ticket.progress_pct}%</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 transition-all duration-300"
                        style={{ width: `${activeThread.active_ticket.progress_pct}%` }}
                      />
                    </div>
                  </div>

                  {activeThread.active_ticket.jira_url && (
                    <a
                      href={activeThread.active_ticket.jira_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-3 flex items-center justify-center gap-1.5 rounded-lg bg-blue-1 py-1.5 text-[11px] font-semibold text-white shadow transition hover:bg-blue-1/90"
                    >
                      <span>View in Jira</span>
                      <ExternalLink className="size-3" />
                    </a>
                  )}
                </div>
              ) : (
                <div className="rounded-xl border border-white/[0.07] bg-dark-3/50 p-4 text-center">
                  <p className="text-xs text-white/50">No tickets assigned to you currently.</p>
                  <p className="mt-1 text-[10px] text-white/30">
                    Once the Manager approves the sprint review gate, assigned tickets will appear here.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
