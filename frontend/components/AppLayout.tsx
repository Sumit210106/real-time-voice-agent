"use client";

import React, { useState } from "react";
import VoiceMic from "./Mic";
import AdminDashboard from "./AdminDashboard";

export default function AppLayout() {
  const [activeView, setActiveView] = useState<"agent" | "admin">("agent");

  return (
    <div className="h-screen flex flex-col bg-black">
      {/* Navbar */}
      <nav className="h-14 bg-zinc-900 border-b border-zinc-800 flex items-center px-6 gap-4">
        <button
          onClick={() => setActiveView("agent")}
          className={`px-4 py-2 rounded text-sm transition-all ${
            activeView === "agent"
              ? "bg-white text-black font-medium"
              : "bg-transparent text-zinc-400 hover:text-white"
          }`}
        >
          Agent
        </button>
        <button
          onClick={() => setActiveView("admin")}
          className={`px-4 py-2 rounded text-sm transition-all ${
            activeView === "admin"
              ? "bg-white text-black font-medium"
              : "bg-transparent text-zinc-400 hover:text-white"
          }`}
        >
          Admin
        </button>
      </nav>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeView === "agent" ? <VoiceMic /> : <AdminDashboard />}
      </div>
    </div>
  );
}