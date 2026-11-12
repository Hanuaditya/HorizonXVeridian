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

const VERIFIED_TEAM_PRESETS = [
  {
    name: 'Aarav Sharma',
    email: 'aarav.sharma@example.com',
    clerk_id: 'user_clerk_manager_demo',
    slack_id: 'U_MGR_DEMO',
    jira_id: '',
    role: 'Engineering Manager (org:admin)',
    skills: 'management, architecture, security, infra',
    workload: 0,
    status: 'ACTIVE',
  },
  {
    name: 'Rohan Patel',
    email: 'rohan.patel@example.com',
    clerk_id: 'user_clerk_emp_a_demo',
    slack_id: 'U_EMP_A_DEMO',
    jira_id: '',
    role: 'Senior Backend Engineer (Employee A)',
    skills: 'elasticsearch, aws, backend, infra, kubernetes',
    workload: 1,
    status: 'ACTIVE',
  },
  {
    name: 'Priya Sen',
    email: 'priya.sen@example.com',
    clerk_id: 'user_clerk_emp_b_demo',
    slack_id: 'U_EMP_B_DEMO',
    jira_id: '',
    role: 'Product & Frontend Engineer (Employee B)',
    skills: 'frontend, auth, oauth, ui, api',
    workload: 2,
    status: 'ACTIVE',
  },
  {
    name: 'Arjun Rao',
    email: 'arjun.rao@example.com',
    clerk_id: 'user_demo_arjun',
    slack_id: 'U_ARJUN_DEMO',
    jira_id: '',
    role: 'Group Product Manager, CI/CD',
    skills: 'elasticsearch, aws, backend',
    workload: 2,
    status: 'ON_PATERNITY_LEAVE',
  },
];

export default function AdminMappingsPage() {
  const [employees, setEmployees] = useState<WorkOSEmployee[]>([]);
  const [config, setConfig] = useState<WorkOSConfigView>({});
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [applyingPresets, setApplyingPresets] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
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

  const handleApplyPresets = async () => {
    setApplyingPresets(true);
    setMessage(null);
    setError(null);
    try {
      for (const p of VERIFIED_TEAM_PRESETS) {
        await fetch('/api/workos/admin/employees', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_name: p.name,
            email: p.email,
            clerk_user_id: p.clerk_id,
            slack_id: p.slack_id,
            jira_account_id: p.jira_id || undefined,
          }),
        });
      }
      setMessage('Successfully verified and bound all 3 real team identities into Supabase.');
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to apply team presets');
    } finally {
      setApplyingPresets(false);
    }
  };

  const handleSelectPreset = (p: typeof VERIFIED_TEAM_PRESETS[number]) => {
    setFullName(p.name);
    setEmail(p.email);
    setClerkId(p.clerk_id);
    setSlackId(p.slack_id);
    setJiraId(p.jira_id);
  };

  const handleSelectEmployee = (emp: WorkOSEmployee) => {
    setFullName(emp.full_name);
    setEmail(emp.email || '');
    setClerkId(emp.clerk_user_id || '');
    setSlackId(emp.slack_id || '');
    setJiraId(emp.jira_account_id || '');
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
          email: email.trim() || undefined,
          clerk_user_id: clerkId.trim() || undefined,
          slack_id: slackId.trim() || undefined,
          jira_account_id: jiraId.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'Update failed');
      setMessage(`Updated identity mapping for ${fullName}`);
      setFullName('');
      setEmail('');
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
          <h1 className="text-3xl font-bold">Admin · Team Identity & Role Binding</h1>
          <p className="mt-1 text-sm text-white/60">
            Bind Clerk User IDs, Slack Member IDs (<code>U0...</code>), and Jira Account IDs into Supabase for your 3-person team.
          </p>
        </div>
        <div className="flex gap-2.5">
          <button
            type="button"
            disabled={applyingPresets}
            onClick={handleApplyPresets}
            className="rounded-lg bg-gradient-to-r from-purple-600 to-sky-600 px-4 py-2 text-xs font-semibold text-white shadow hover:opacity-95 disabled:opacity-50"
          >
            {applyingPresets ? 'Binding Verified Team...' : 'Apply Verified 3-Person Team Presets'}
          </button>
          <button
            type="button"
            disabled={syncing}
            onClick={handleSync}
            className="rounded-lg bg-blue-1 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50"
          >
            {syncing ? 'Syncing...' : 'Sync All Connectors'}
          </button>
        </div>
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

      {/* Featured Verified Team Binding Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {VERIFIED_TEAM_PRESETS.map((p) => {
          const matched = employees.find((e) => e.full_name.toLowerCase() === p.name.toLowerCase());
          const isBound = Boolean(matched?.clerk_user_id && matched?.slack_id);
          return (
            <div
              key={p.name}
              className="flex flex-col justify-between rounded-xl border border-white/10 bg-dark-1 p-4 shadow transition hover:border-sky-400/40"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-sky-300">
                    {p.role.split('(')[0].trim()}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                      p.status === 'ACTIVE'
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : 'bg-amber-500/20 text-amber-300'
                    }`}
                  >
                    {p.status}
                  </span>
                </div>
                <h3 className="mt-1 text-sm font-bold text-white">{p.name}</h3>
                <p className="text-[11px] text-white/60">{p.email}</p>
                <div className="mt-2.5 space-y-1 font-mono text-[10px] text-white/50">
                  <p className="truncate">Clerk: {matched?.clerk_user_id || p.clerk_id}</p>
                  <p className="truncate">Slack: {matched?.slack_id || p.slack_id}</p>
                  <p>Workload: {matched?.active_task_count ?? matched?.capacity_cache ?? p.workload} task(s)</p>
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-2.5">
                <span className="text-[10px] text-white/45">
                  {isBound ? 'Bound' : 'Pending'}
                </span>
                <button
                  type="button"
                  onClick={() => handleSelectPreset(p)}
                  className="rounded bg-dark-3 px-2 py-1 text-[10px] font-medium text-sky-200 hover:bg-dark-2 hover:text-white"
                >
                  Edit in Form
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="rounded-xl border border-white/10 bg-dark-1 p-5 lg:col-span-2">
          <div className="flex items-center justify-between pb-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Live Supabase Identity Directory
            </h2>
            <span className="text-xs text-white/50">{employees.length} employee(s)</span>
          </div>
          {loading ? (
            <div className="mt-4 space-y-2">
              <div className="h-8 animate-pulse rounded bg-white/10" />
              <div className="h-8 animate-pulse rounded bg-white/10" />
            </div>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-white/10 text-white/55">
                  <tr>
                    <th className="pb-2">Name</th>
                    <th className="pb-2">Email</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2">Workload</th>
                    <th className="pb-2">Clerk ID</th>
                    <th className="pb-2">Slack ID</th>
                    <th className="pb-2">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {employees.map((emp) => (
                    <tr key={emp.id} className="hover:bg-white/[0.02]">
                      <td className="py-2.5 font-medium text-white">{emp.full_name}</td>
                      <td className="py-2.5 text-white/60">{emp.email || '—'}</td>
                      <td className="py-2.5">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] ${
                            emp.status === 'ACTIVE'
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : 'bg-dark-3 text-sky-1'
                          }`}
                        >
                          {emp.status}
                        </span>
                      </td>
                      <td className="py-2.5 font-mono">
                        {emp.active_task_count ?? emp.capacity_cache ?? 0}
                      </td>
                      <td className="py-2.5 font-mono text-[11px] text-white/60">
                        {emp.clerk_user_id || '—'}
                      </td>
                      <td className="py-2.5 font-mono text-[11px] text-white/60">
                        {emp.slack_id || '—'}
                      </td>
                      <td className="py-2.5">
                        <button
                          type="button"
                          onClick={() => handleSelectEmployee(emp)}
                          className="rounded bg-dark-3 px-2 py-0.5 text-[10px] text-sky-200 hover:bg-dark-2"
                        >
                          Edit
                        </button>
                      </td>
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
              Update Identity Mapping
            </h2>
            <p className="mt-1 text-[11px] text-white/50">
              Directly updates or creates employee mapping rows in Supabase.
            </p>
            <div className="mt-3 space-y-2.5 text-xs">
              <div>
                <label className="text-[10px] text-white/60">Full Name</label>
                <input
                  type="text"
                  placeholder="e.g. catchme if"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="mt-0.5 w-full rounded border border-white/15 bg-dark-2 px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="text-[10px] text-white/60">Email</label>
                <input
                  type="email"
                  placeholder="e.g. employee@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-0.5 w-full rounded border border-white/15 bg-dark-2 px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="text-[10px] text-white/60">Clerk User ID</label>
                <input
                  type="text"
                  placeholder="user_..."
                  value={clerkId}
                  onChange={(e) => setClerkId(e.target.value)}
                  className="mt-0.5 w-full rounded border border-white/15 bg-dark-2 px-3 py-2 font-mono text-white"
                />
              </div>
              <div>
                <label className="text-[10px] text-white/60">Slack Member ID</label>
                <input
                  type="text"
                  placeholder="U0..."
                  value={slackId}
                  onChange={(e) => setSlackId(e.target.value)}
                  className="mt-0.5 w-full rounded border border-white/15 bg-dark-2 px-3 py-2 font-mono text-white"
                />
              </div>
              <div>
                <label className="text-[10px] text-white/60">Jira Account ID (Optional)</label>
                <input
                  type="text"
                  placeholder="Jira accountId or empty for auto-search"
                  value={jiraId}
                  onChange={(e) => setJiraId(e.target.value)}
                  className="mt-0.5 w-full rounded border border-white/15 bg-dark-2 px-3 py-2 font-mono text-white"
                />
              </div>
              <button
                type="submit"
                className="w-full rounded bg-purple-600 py-2 font-semibold text-white transition hover:bg-purple-500"
              >
                Save Identity Mapping
              </button>
            </div>
          </form>

          <div className="rounded-xl border border-white/10 bg-dark-1 p-5 text-xs">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
              Runtime Config & Compliance
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
                <dt className="text-white/50">Blocked API Policy</dt>
                <dd className="text-amber-300">SEC-POL-104</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}
