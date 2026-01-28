"use client";

import { useEffect } from "react";
import { TownCanvas } from "@/components/town/TownCanvas";
import { SimulationControls } from "@/components/dashboard/SimulationControls";
import { TransactionFeed } from "@/components/dashboard/TransactionFeed";
import { AgentPanel } from "@/components/dashboard/AgentPanel";
import { FinancialOverlay } from "@/components/dashboard/FinancialOverlay";
import { AgentThoughts } from "@/components/dashboard/AgentThoughts";
import { getWebSocket } from "@/lib/api/websocket";
import { useSimulationStore } from "@/lib/state/simulationStore";

export default function Home() {
  const setConnected = useSimulationStore((state) => state.setConnected);
  const processEvent = useSimulationStore((state) => state.processEvent);

  // Connect to WebSocket on mount
  useEffect(() => {
    const ws = getWebSocket();

    const unsubConnect = ws.onConnect(() => {
      setConnected(true);
      console.log("Connected to simulation");
    });

    const unsubDisconnect = ws.onDisconnect(() => {
      setConnected(false);
      console.log("Disconnected from simulation");
    });

    const unsubEvents = ws.onAny((event) => {
      processEvent(event);
    });

    // Connect
    ws.connect();

    return () => {
      unsubConnect();
      unsubDisconnect();
      unsubEvents();
      ws.disconnect();
    };
  }, [setConnected, processEvent]);

  return (
    <main className="h-screen flex flex-col bg-slate-900 p-4">
      {/* Header */}
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">
            🏘️ Atlas Town
          </h1>
          <p className="text-slate-400 text-sm">
            AI-powered business simulation generating realistic accounting data
          </p>
        </div>
        <div className="text-right text-xs text-slate-500">
          <p>Powered by Claude, GPT, and Gemini</p>
          <p className="text-slate-600">5 businesses • 1 accountant</p>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex gap-4 min-h-0 overflow-x-auto">
        {/* Left Panel - Controls & Financial Overview */}
        <div className="w-72 flex-shrink-0 flex flex-col gap-4 overflow-y-auto custom-scrollbar">
          <SimulationControls />
          <FinancialOverlay />
        </div>

        {/* Center - Town Canvas and Agent Panel */}
        <div className="flex-1 flex flex-col gap-4 min-h-0 min-w-0">
          {/* Town Canvas */}
          <div className="flex-1 flex items-center justify-center min-h-0 overflow-auto">
            <TownCanvas />
          </div>
          {/* Agent Panel - Horizontal below canvas */}
          <div className="h-32 flex-shrink-0">
            <AgentPanel />
          </div>
        </div>

        {/* Right Panel - Transactions & Thoughts */}
        <div className="w-80 flex-shrink-0 flex flex-col gap-4 min-h-0">
          <div className="flex-1 min-h-0">
            <TransactionFeed />
          </div>
          <div className="h-64 flex-shrink-0">
            <AgentThoughts />
          </div>
        </div>
      </div>
    </main>
  );
}
