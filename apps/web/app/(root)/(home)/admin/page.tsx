'use client';

import React, { useCallback, useEffect, useState } from 'react';
import type { WorkOSEmployee } from '@/lib/workos-types';

interface WorkOSConfigView {
  evon_model_name?: string;
  llm_extraction_model?: string;
  embedding_model?: string;
  embedding_dim?: number;
  security_threshold?: number;
  finance_threshold?: number;
  capacity_limit?: number;
  capacity_new_hire_limit?: number;
  demo_mode?: boolean;
}

export default function AdminMappingsPage() {
  const [employees, setEmployees] = useState<WorkOSEmployee[]>([]);
  const [config, setConfig] = useState<WorkOSConfigView>({});
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [fullName, setFullName] = useState('');
  const [clerkId, setClerkId] = useState('');
  const [slackId, setSlackId] = useState('');
  const [jiraId, setJiraId] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/workos/admin/employees');
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
      setEmployees(data.employees || []);
      setConfig(data.config || {});
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to reach WorkOS admin API');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSync = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const res = await fetch('/api/workos/admin/sync', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'Sync failed');
      setMessage(
        `Synced HR=${data.hr_employees}, Finance CSV=${data.finance_budgets}, Security=${data.security_policies}`
      );
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const handleSaveMapping = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName.trim()) return;
    setMessage(null);
    setError(null);
    try {
      const res = await fetch('/api/workos/admin/employees', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: fullName.trim(),
          clerk_user_id: clerkId.trim() || undefined,
          slack_id: slackId.trim() || undefined,
          jira_account_id: jiraId.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'Update failed');
      setMessage(`Updated identity mapping for ${fullName}`);
      setFullName('');
      setClerkId('');
      setSlackId('');
      setJiraId('');
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save mapping');
    }
  };

  return (
    <section className="flex flex-col gap-6 text-white">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Admin · Identity Mappings & Connectors</h1>
          <p className="mt-1 text-sm text-white/60">
            Map Clerk identities to Slack & Jira accounts, inspect compliance thresholds, and trigger
            HR / Finance CSV / Security connector syncs.
          </p>
        </div>
        <button
          type="button"
          disabled={syncing}
          onClick={handleSync}
          className="rounded-lg bg-blue-1 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600 disabled:opacity-50"
        >
          {syncing ? 'Syncing Connectors...' : 'Sync All Connectors Now'}
        </button>
      </div>

      {message && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
          {message}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="rounded-xl border border-white/10 bg-dark-1 p-5 lg:col-span-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
            Employee Identity Directory
          </h2>
          {loading ? (
            <div className="mt-4 space-y-2">
              <div className="h-8 animate-pulse rounded bg-white/10" />
              <div className="h-8 animate-pulse rounded bg-white/10" />
            </div>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-white/10 text-white/55">
                  <tr>
                    <th className="pb-2">Name</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2">Tickets</th>
                    <th className="pb-2">Clerk ID</th>
                    <th className="pb-2">Slack ID</th>
                    <th className="pb-2">Jira Account</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {employees.map((emp) => (
                    <tr key={emp.id}>
                      <td className="py-2.5 font-medium text-white">{emp.full_name}</td>
                      <td className="py-2.5">
                        <span className="rounded bg-dark-3 px-2 py-0.5 text-[10px] text-sky-1">
                          {emp.status}
                        </span>
                      </td>
                      <td className="py-2.5 font-mono">{emp.capacity_cache}</td>
                      <td className="py-2.5 font-mono text-white/60">{emp.clerk_user_id || '—'}</td>
                      <td className="py-2.5 font-mono text-white/60">{emp.slack_id || '—'}</td>
                      <td className="py-2.5 font-mono text-white/60">{emp.jira_account_id || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-5">
          <form
            onSubmit={handleSaveMapping}
            className="rounded-xl border border-white/10 bg-dark-1 p-5"
          >
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Update Employee Mapping
            </h2>
            <div className="mt-3 space-y-2.5 text-xs">
              <input
                type="text"
                placeholder="Full Name (e.g. Josh Lambert)"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full rounded border border-white/15 bg-dark-2 px-3 py-2 text-white"
              />
              <input
                type="text"
                placeholder="Clerk User ID (user_...)"
                value={clerkId}
                onChange={(e) => setClerkId(e.target.value)}
                className="w-full rounded border border-white/15 bg-dark-2 px-3 py-2 text-white"
              />
              <input
                type="text"
                placeholder="Slack Member ID (U...)"
                value={slackId}
                onChange={(e) => setSlackId(e.target.value)}
                className="w-full rounded border border-white/15 bg-dark-2 px-3 py-2 text-white"
              />
              <input
                type="text"
                placeholder="Jira Account ID"
                value={jiraId}
                onChange={(e) => setJiraId(e.target.value)}
                className="w-full rounded border border-white/15 bg-dark-2 px-3 py-2 text-white"
              />
              <button
                type="submit"
                className="w-full rounded bg-purple-600 py-2 font-semibold text-white hover:bg-purple-500"
              >
                Save Mapping
              </button>
            </div>
          </form>

          <div className="rounded-xl border border-white/10 bg-dark-1 p-5 text-xs">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Runtime Config & Thresholds
            </h2>
            <dl className="mt-3 space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between">
                <dt className="text-white/50">Evon Model</dt>
                <dd className="text-purple-300">{config.evon_model_name || 'gnani-ai/evon-30b'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-white/50">Embedding Dim</dt>
                <dd className="text-emerald-300">{config.embedding_dim ?? 1024}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-white/50">Security Threshold</dt>
                <dd>{config.security_threshold ?? 0.5}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-white/50">Finance Threshold</dt>
                <dd>{config.finance_threshold ?? 0.5}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-white/50">Capacity Limit</dt>
                <dd>
                  {config.capacity_limit ?? 10} (New Hire: {config.capacity_new_hire_limit ?? 2})
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}
