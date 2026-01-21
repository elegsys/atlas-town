"use client";

import { useEffect } from "react";
import { TownCanvas } from "@/components/town/TownCanvas";
import { SimulationControls } from "@/components/dashboard/SimulationControls";
import { TransactionFeed } from "@/components/dashboard/TransactionFeed";
import { AgentPanel } from "@/components/dashboard/AgentPanel";
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
      <header className="mb-4">
        <h1 className="text-3xl font-bold text-white">
          🏘️ Atlas Town
        </h1>
        <p className="text-slate-400 text-sm">
          AI-powered business simulation generating realistic accounting data
        </p>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left Panel - Controls & Agent */}
        <div className="w-72 flex flex-col gap-4">
          <SimulationControls />
          <AgentPanel />
        </div>

        {/* Center - Town Canvas */}
        <div className="flex-1 flex items-center justify-center">
          <TownCanvas />
        </div>

        {/* Right Panel - Transaction Feed */}
        <div className="w-80">
          <TransactionFeed />
        </div>
      </div>

      {/* Footer */}
      <footer className="mt-4 text-center text-slate-500 text-xs">
        Atlas Town Simulation • Powered by Claude, GPT, and Gemini
      </footer>
    </main>
  );
}
