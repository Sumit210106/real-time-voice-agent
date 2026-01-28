"use client";

import React, { useEffect, useState } from 'react';

interface Session {
  id: string;
  user_id: string;
  turns: number;
  avg_ttft: number;
  last_active: string;
  is_playing: boolean;
}

interface Stats {
  timestamp: string;
  sessions: { total_created: number; currently_speaking: number };
  performance: { avg_ttft_seconds: number; total_web_searches: number };
  active_users: Session[];
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [targetSession, setTargetSession] = useState('');
  const [newContext, setNewContext] = useState('');
  const [updateStatus, setUpdateStatus] = useState('');

  // Fetch metrics every 2 seconds
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/admin/stats');
        const data = await res.json();
        setStats(data);
      } catch (err) {
        console.error("Dashboard sync error:", err);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 2000);
    return () => clearInterval(interval);
  }, []);

  // Update Context Function
  const handleUpdateContext = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetSession || !newContext) return;

    try {
      const res = await fetch(`http://localhost:8000/api/admin/update-context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: targetSession, context: newContext }),
      });
      
      if (res.ok) {
        setUpdateStatus('Context updated successfully!');
        setNewContext('');
        setTimeout(() => setUpdateStatus(''), 3000);
      }
    } catch (err) {
      setUpdateStatus('Failed to update context.');
    }
  };

  if (!stats) return <div className="p-10 bg-black min-h-screen text-gray-500 font-mono">Connecting to agent...</div>;

  return (
    <div className="p-8 bg-black min-h-screen text-white font-mono selection:bg-white selection:text-black">
      <header className="mb-12 border-b border-gray-800 pb-6">
        <h1 className="text-xl tracking-tighter uppercase font-bold text-gray-200">System Monitoring // Admin</h1>
        <p className="text-xs text-gray-500 mt-1">Status: Operational — {stats.timestamp}</p>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-12">
        <StatGroup label="Total Sessions" value={stats.sessions.total_created} />
        <StatGroup label="Latency (Avg)" value={`${stats.performance.avg_ttft_seconds}s`} color="text-yellow-500" />
        <StatGroup label="Live Voices" value={stats.sessions.currently_speaking} color="text-green-500" />
        <StatGroup label="Tool Usage" value={stats.performance.total_web_searches} />
      </div>

      {/* User Table */}
      <section className="mb-12">
        <h2 className="text-xs uppercase text-gray-500 mb-4 tracking-widest">Active Connections</h2>
        <div className="border border-gray-800 rounded-sm">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500">
                <th className="p-4 font-normal">Session Short-ID</th>
                <th className="p-4 font-normal">Identity</th>
                <th className="p-4 font-normal text-right">Turns</th>
                <th className="p-4 font-normal text-right">TTFT</th>
                <th className="p-4 font-normal text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-900">
              {stats.active_users.map((s) => (
                <tr key={s.id} className="hover:bg-gray-950 transition-all cursor-crosshair" onClick={() => setTargetSession(s.id)}>
                  <td className="p-4 text-gray-400">...{s.id}</td>
                  <td className="p-4 text-gray-100">{s.user_id}</td>
                  <td className="p-4 text-right">{s.turns}</td>
                  <td className="p-4 text-right text-yellow-600">{s.avg_ttft}s</td>
                  <td className="p-4 text-center">
                    {s.is_playing ? <span className="text-green-500">● Live</span> : <span className="text-gray-700">○ Idle</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Update Context Section */}
      <section className="max-w-2xl border border-gray-800 p-6 rounded-sm bg-[#050505]">
        <h2 className="text-xs uppercase text-gray-500 mb-4 tracking-widest">Inject System Context</h2>
        <form onSubmit={handleUpdateContext} className="space-y-4">
          <input 
            type="text" 
            placeholder="Click a session above or paste full ID" 
            value={targetSession} 
            onChange={(e) => setTargetSession(e.target.value)}
            className="w-full bg-black border border-gray-800 p-3 text-xs outline-none focus:border-white transition-colors"
          />
          <textarea 
            placeholder="Enter new system prompt (e.g. 'You are now a sarcastic chef')" 
            value={newContext}
            onChange={(e) => setNewContext(e.target.value)}
            className="w-full bg-black border border-gray-800 p-3 text-xs h-24 outline-none focus:border-white transition-colors"
          />
          <div className="flex items-center justify-between">
            <button className="bg-white text-black text-xs font-bold px-6 py-2 hover:bg-gray-200 transition-colors uppercase">
              Update Agent Personality
            </button>
            {updateStatus && <span className="text-[10px] uppercase text-gray-400">{updateStatus}</span>}
          </div>
        </form>
      </section>
    </div>
  );
}

function StatGroup({ label, value, color = "text-white" }: { label: string; value: any; color?: string }) {
  return (
    <div className="border-l border-gray-800 pl-4">
      <p className="text-[10px] uppercase text-gray-500 tracking-widest mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
    </div>
  );
}