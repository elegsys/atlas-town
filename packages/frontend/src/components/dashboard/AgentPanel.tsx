"use client";

import { useSimulationStore, AgentState } from "@/lib/state/simulationStore";
import { INDUSTRY_ICONS } from "@/lib/pixi/townConfig";

const STATUS_COLORS: Record<AgentState["status"], string> = {
  idle: "bg-slate-500",
  thinking: "bg-yellow-500 animate-pulse",
  acting: "bg-blue-500 animate-pulse",
  speaking: "bg-green-500 animate-pulse",
  moving: "bg-purple-500 animate-pulse",
};

const STATUS_LABELS: Record<AgentState["status"], string> = {
  idle: "Idle",
  thinking: "Thinking...",
  acting: "Working...",
  speaking: "Speaking",
  moving: "Walking",
};

export function AgentPanel() {
  const agents = useSimulationStore((state) => state.agents);
  const sarahAgent = agents.get("sarah");

  if (!sarahAgent) {
    return null;
  }

  return (
    <div className="bg-slate-800 rounded-lg p-4 shadow-lg">
      <h2 className="text-lg font-bold mb-3 text-slate-100">
        Active Agent
      </h2>

      <div className="space-y-3">
        {/* Sarah's card */}
        <AgentCard agent={sarahAgent} />

        {/* Current location */}
        <div className="bg-slate-700/50 rounded-lg p-3">
          <p className="text-xs text-slate-400 mb-1">Current Location</p>
          <p className="text-sm text-white font-medium flex items-center gap-2">
            <span className="text-lg">
              {getLocationIcon(sarahAgent.currentLocation)}
            </span>
            {formatLocation(sarahAgent.currentLocation)}
          </p>
          {sarahAgent.targetLocation && (
            <p className="text-xs text-slate-400 mt-1">
              → Walking to {formatLocation(sarahAgent.targetLocation)}
            </p>
          )}
        </div>

        {/* Thought bubble */}
        {sarahAgent.currentMessage && (
          <div className="bg-slate-700 rounded-lg p-3 border-l-4 border-purple-500">
            <p className="text-xs text-slate-400 mb-1">💭 Thinking</p>
            <p className="text-sm text-slate-200 leading-relaxed">
              {sarahAgent.currentMessage}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function AgentCard({ agent }: { agent: AgentState }) {
  const statusColor = STATUS_COLORS[agent.status];
  const statusLabel = STATUS_LABELS[agent.status];

  return (
    <div className="flex items-center gap-3 p-3 bg-slate-700/50 rounded-lg">
      {/* Avatar */}
      <div className="w-12 h-12 rounded-full bg-purple-500 flex items-center justify-center text-2xl">
        👩‍💼
      </div>

      {/* Info */}
      <div className="flex-1">
        <p className="text-white font-medium">{agent.name}</p>
        <p className="text-xs text-slate-400">
          {agent.type.charAt(0).toUpperCase() + agent.type.slice(1)}
        </p>
      </div>

      {/* Status */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${statusColor}`} />
        <span className="text-xs text-slate-400">{statusLabel}</span>
      </div>
    </div>
  );
}

function getLocationIcon(location: string): string {
  const locationIcons: Record<string, string> = {
    office: "🏢",
    craigs_landscaping: INDUSTRY_ICONS.landscaping,
    tonys_pizzeria: INDUSTRY_ICONS.restaurant,
    nexus_tech: INDUSTRY_ICONS.technology,
    main_street_dental: INDUSTRY_ICONS.healthcare,
    harbor_realty: INDUSTRY_ICONS.real_estate,
  };

  return locationIcons[location] || "📍";
}

function formatLocation(location: string): string {
  const names: Record<string, string> = {
    office: "Accounting Office",
    craigs_landscaping: "Craig's Landscaping",
    tonys_pizzeria: "Tony's Pizzeria",
    nexus_tech: "Nexus Tech",
    main_street_dental: "Main Street Dental",
    harbor_realty: "Harbor Realty",
  };

  return names[location] || location;
}
