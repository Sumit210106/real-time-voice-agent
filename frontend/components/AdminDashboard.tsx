"use client";

import React, { useEffect, useState } from 'react';

interface Session {
  id: string;
  user_id: string;
  turns: number;
  avg_ttft: number;
  last_active: string;
  is_playing: boolean;
  last_transcript?: string;
  last_response?: string;
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
        // const res = await fetch('http://localhost:8000/api/admin/stats');
        const res = await fetch('https://real-time-voice-agent.onrender.com/api/admin/stats');
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
      // const res = await fetch(`http://localhost:8000/api/admin/update-context`, {
      const res = await fetch(`https://real-time-voice-agent.onrender.com/api/admin/update-context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: targetSession, context: newContext }),
      });
      
      if (res.ok) {
        setUpdateStatus('✓ Updated!');
        setNewContext('');
        setTimeout(() => setUpdateStatus(''), 3000);
      } else {
        setUpdateStatus('❌ Failed');
      }
    } catch (err) {
      setUpdateStatus('❌ Error');
    }
  };

  if (!stats) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <p className="text-gray-500">loading...</p>
      </div>
    );
  }

  return (
    <div className="h-screen bg-black text-white overflow-y-auto">
      <div className="max-w-7xl mx-auto p-6 sm:p-8">
        
        {/* Header */}
        <div className="mb-10">
          <h1 className="text-2xl sm:text-3xl mb-2 font-medium">Admin Dashboard</h1>
          <p className="text-gray-500 text-sm">
            Last updated: {new Date(stats.timestamp).toLocaleString()}
          </p>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
          <div className="bg-zinc-900 p-5 rounded-lg border border-zinc-800">
            <div className="text-gray-500 text-xs mb-2 uppercase tracking-wide">Total Sessions</div>
            <div className="text-3xl font-semibold">{stats.sessions.total_created}</div>
          </div>
          <div className="bg-zinc-900 p-5 rounded-lg border border-zinc-800">
            <div className="text-gray-500 text-xs mb-2 uppercase tracking-wide">Avg Latency</div>
            <div className="text-3xl font-semibold text-yellow-400">{stats.performance.avg_ttft_seconds}s</div>
          </div>
          <div className="bg-zinc-900 p-5 rounded-lg border border-zinc-800">
            <div className="text-gray-500 text-xs mb-2 uppercase tracking-wide">Active Voices</div>
            <div className="text-3xl font-semibold text-green-400">{stats.sessions.currently_speaking}</div>
          </div>
          <div className="bg-zinc-900 p-5 rounded-lg border border-zinc-800">
            <div className="text-gray-500 text-xs mb-2 uppercase tracking-wide">Web Searches</div>
            <div className="text-3xl font-semibold">{stats.performance.total_web_searches}</div>
          </div>
        </div>

        {/* Sessions List */}
        <div className="mb-10">
          <h2 className="text-xl mb-4 font-medium">Active Sessions</h2>
          
          {/* Desktop view */}
          <div className="hidden md:block bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/50">
                  <th className="text-left p-4 text-gray-400 font-medium text-xs uppercase tracking-wider">Session ID</th>
                  <th className="text-left p-4 text-gray-400 font-medium text-xs uppercase tracking-wider">User</th>
                  <th className="text-left p-4 text-gray-400 font-medium text-xs uppercase tracking-wider">Turns</th>
                  <th className="text-left p-4 text-gray-400 font-medium text-xs uppercase tracking-wider">TTFT</th>
                  <th className="text-left p-4 text-gray-400 font-medium text-xs uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody>
                {stats.active_users.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-12 text-center text-gray-500">
                      no active sessions yet
                    </td>
                  </tr>
                ) : (
                  stats.active_users.map((s) => (
                    <tr 
                      key={s.id}
                      onClick={() => setTargetSession(s.id)}
                      className="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer transition-colors"
                    >
                      <td className="p-4 font-mono text-gray-400 text-xs">...{s.id.slice(-8)}</td>
                      <td className="p-4 text-white">{s.user_id}</td>
                      <td className="p-4 text-gray-300">{s.turns}</td>
                      <td className="p-4 text-yellow-400 font-medium">{s.avg_ttft}s</td>
                      <td className="p-4">
                        {s.is_playing ? (
                          <span className="text-green-400 flex items-center gap-2">
                            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                            live
                          </span>
                        ) : (
                          <span className="text-gray-600 flex items-center gap-2">
                            <span className="w-2 h-2 bg-gray-600 rounded-full"></span>
                            idle
                          </span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile view */}
          <div className="md:hidden space-y-3">
            {stats.active_users.length === 0 ? (
              <div className="bg-zinc-900 rounded-lg p-8 text-center text-gray-500 border border-zinc-800">
                no active sessions yet
              </div>
            ) : (
              stats.active_users.map((s) => (
                <div
                  key={s.id}
                  onClick={() => setTargetSession(s.id)}
                  className="bg-zinc-900 rounded-lg p-4 border border-zinc-800 hover:border-zinc-700 transition-colors cursor-pointer"
                >
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <div className="font-medium text-white">{s.user_id}</div>
                      <div className="text-xs text-gray-500 font-mono mt-1">
                        ...{s.id.slice(-8)}
                      </div>
                    </div>
                    {s.is_playing ? (
                      <span className="text-green-400 text-sm flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></span>
                        live
                      </span>
                    ) : (
                      <span className="text-gray-600 text-sm flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 bg-gray-600 rounded-full"></span>
                        idle
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-400">
                    {s.turns} turns • {s.avg_ttft}s ttft
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Update form */}
        <div className="max-w-2xl mb-10">
          <h2 className="text-xl mb-4 font-medium">Update System Context</h2>
          <div className="bg-zinc-900 rounded-lg p-6 border border-zinc-800">
            <form onSubmit={handleUpdateContext} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                  Session ID
                </label>
                <input 
                  type="text" 
                  placeholder="click session above or paste id here" 
                  value={targetSession} 
                  onChange={(e) => setTargetSession(e.target.value)}
                  className="w-full bg-black border border-zinc-700 rounded-lg px-4 py-2.5 text-sm focus:border-white focus:outline-none transition-colors"
                />
              </div>
              
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                  New Context
                </label>
                <textarea 
                  placeholder="type new system prompt here..." 
                  value={newContext}
                  onChange={(e) => setNewContext(e.target.value)}
                  rows={4}
                  className="w-full bg-black border border-zinc-700 rounded-lg px-4 py-2.5 text-sm focus:border-white focus:outline-none resize-none transition-colors"
                />
              </div>
              
              <div className="flex items-center gap-3 pt-2">
                <button 
                  type="submit"
                  disabled={!targetSession || !newContext}
                  className="bg-white text-black px-5 py-2.5 rounded-lg text-sm font-medium disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed hover:bg-gray-200 transition-colors"
                >
                  Update
                </button>
                {updateStatus && (
                  <span className="text-sm text-gray-400">{updateStatus}</span>
                )}
              </div>
            </form>
          </div>
        </div>

        {/* Live Monitoring Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-zinc-900 p-6 rounded-lg border border-zinc-800">
            <h3 className="text-gray-400 text-xs uppercase tracking-widest mb-5 font-medium">Live Transcripts</h3>
            <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-zinc-900">
              {stats.active_users.length === 0 ? (
                <p className="text-gray-600 italic text-sm">waiting for live traffic...</p>
              ) : (
                stats.active_users.map((s) => (
                  <div key={s.id} className="border-l-2 border-zinc-700 pl-4 py-2">
                    <div className="text-[10px] text-zinc-500 mb-2 font-mono uppercase tracking-wider">
                      Session: ...{s.id.slice(-6)}
                    </div>
                    <p className="text-sm text-zinc-300 mb-2">
                      <span className="text-blue-400 mr-2 font-medium">User:</span> 
                      {s.last_transcript || "..."}
                    </p>
                    <p className="text-sm text-zinc-100">
                      <span className="text-green-400 mr-2 font-medium">Agent:</span> 
                      {s.last_response || "..."}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
          
          <div className="bg-zinc-900 p-6 rounded-lg border border-zinc-800">
            <h3 className="text-gray-400 text-xs uppercase tracking-widest mb-5 font-medium">Pipeline Health</h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-zinc-800/30 rounded">
                <span className="text-sm text-gray-400">Sync Status</span>
                <span className="text-green-400 text-xs font-mono flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></span>
                  CONNECTED
                </span>
              </div>
              <div className="flex items-center justify-between p-3 bg-zinc-800/30 rounded">
                <span className="text-sm text-gray-400">Last Snapshot</span>
                <span className="text-zinc-300 text-xs font-mono">{new Date().toLocaleTimeString()}</span>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}