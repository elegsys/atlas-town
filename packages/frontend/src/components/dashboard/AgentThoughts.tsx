"use client";

import { useSimulationStore, AgentState } from "@/lib/state/simulationStore";
import { SimulationEvent } from "@/lib/api/websocket";

const STATUS_ICONS: Record<AgentState["status"], string> = {
  idle: "💤",
  thinking: "🤔",
  acting: "⚡",
  speaking: "💬",
  moving: "🚶",
};

const TOOL_ICONS: Record<string, string> = {
  create_invoice: "📄",
  create_bill: "📋",
  record_payment: "💰",
  create_journal_entry: "📝",
  get_invoices: "🔍",
  get_bills: "🔍",
  get_balance: "💵",
  get_chart_of_accounts: "📊",
  default: "🔧",
};

export function AgentThoughts() {
  const recentEvents = useSimulationStore((state) => state.recentEvents);
  const agents = useSimulationStore((state) => state.agents);
  const sarahAgent = agents.get("sarah");

  // Get recent thinking/acting events (last 10)
  const thoughtEvents = recentEvents
    .filter(
      (e) =>
        e.type === "agent.thinking" ||
        e.type === "agent.speaking" ||
        e.type === "tool.called" ||
        e.type === "tool.completed" ||
        e.type === "tool.failed"
    )
    .slice(0, 10);

  return (
    <div className="bg-slate-800 rounded-lg p-4 shadow-lg h-full flex flex-col">
      <h2 className="text-lg font-bold mb-3 text-slate-100 flex items-center gap-2">
        <span>🧠</span>
        Agent Thoughts
      </h2>

      {/* Current Status */}
      {sarahAgent && (
        <div className="bg-slate-700/50 rounded-lg p-3 mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-xl">
              👩‍💼
            </div>
            <div className="flex-1">
              <p className="text-white font-medium">{sarahAgent.name}</p>
              <p className="text-xs text-slate-400 flex items-center gap-1">
                <span>{STATUS_ICONS[sarahAgent.status]}</span>
                <span className="capitalize">{sarahAgent.status}</span>
              </p>
            </div>
          </div>

          {/* Current thought bubble */}
          {sarahAgent.currentMessage && (
            <div className="mt-3 relative">
              <div className="bg-slate-600 rounded-lg p-3 text-sm text-slate-200 leading-relaxed">
                {sarahAgent.currentMessage}
              </div>
              <div className="absolute -bottom-2 left-4 w-3 h-3 bg-slate-600 rotate-45" />
            </div>
          )}
        </div>
      )}

      {/* Event Stream */}
      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2">
        {thoughtEvents.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-8">
            No agent activity yet.
            <br />
            <span className="text-xs">Thoughts will appear as the simulation runs.</span>
          </p>
        ) : (
          thoughtEvents.map((event) => (
            <ThoughtEvent key={event.id} event={event} />
          ))
        )}
      </div>
    </div>
  );
}

function ThoughtEvent({ event }: { event: SimulationEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  switch (event.type) {
    case "agent.thinking":
      return (
        <div className="bg-yellow-900/30 border border-yellow-800/50 rounded-lg p-2">
          <div className="flex items-center gap-2 text-xs text-yellow-400">
            <span>🤔</span>
            <span className="font-medium">Thinking</span>
            <span className="text-yellow-600 ml-auto">{time}</span>
          </div>
        </div>
      );

    case "agent.speaking":
      return (
        <div className="bg-green-900/30 border border-green-800/50 rounded-lg p-2">
          <div className="flex items-center gap-2 text-xs text-green-400 mb-1">
            <span>💬</span>
            <span className="font-medium">Speaking</span>
            <span className="text-green-600 ml-auto">{time}</span>
          </div>
          {typeof event.data?.message === "string" && event.data.message && (
            <p className="text-xs text-green-200 pl-5 leading-relaxed">
              {event.data.message}
            </p>
          )}
        </div>
      );

    case "tool.called":
      const toolName = event.tool?.name || "unknown";
      const toolIcon = TOOL_ICONS[toolName] || TOOL_ICONS.default;
      return (
        <div className="bg-blue-900/30 border border-blue-800/50 rounded-lg p-2">
          <div className="flex items-center gap-2 text-xs text-blue-400 mb-1">
            <span>{toolIcon}</span>
            <span className="font-medium font-mono">{toolName}</span>
            <span className="text-blue-600 ml-auto">{time}</span>
          </div>
          {event.tool?.args && Object.keys(event.tool.args).length > 0 && (
            <div className="text-xs text-blue-200 pl-5 font-mono">
              {formatToolArgs(event.tool.args)}
            </div>
          )}
        </div>
      );

    case "tool.completed":
      return (
        <div className="bg-emerald-900/30 border border-emerald-800/50 rounded-lg p-2">
          <div className="flex items-center gap-2 text-xs text-emerald-400">
            <span>✅</span>
            <span className="font-medium font-mono">{event.tool?.name}</span>
            {event.tool?.duration_ms && (
              <span className="text-emerald-600">({event.tool.duration_ms}ms)</span>
            )}
            <span className="text-emerald-600 ml-auto">{time}</span>
          </div>
        </div>
      );

    case "tool.failed":
      return (
        <div className="bg-red-900/30 border border-red-800/50 rounded-lg p-2">
          <div className="flex items-center gap-2 text-xs text-red-400 mb-1">
            <span>❌</span>
            <span className="font-medium font-mono">{event.tool?.name}</span>
            <span className="text-red-600 ml-auto">{time}</span>
          </div>
          {event.tool?.error && (
            <p className="text-xs text-red-200 pl-5">{event.tool.error}</p>
          )}
        </div>
      );

    default:
      return null;
  }
}

function formatToolArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args)
    .filter(([, v]) => v !== undefined && v !== null)
    .slice(0, 3); // Show max 3 args

  if (entries.length === 0) return "";

  return entries
    .map(([k, v]) => {
      const value = typeof v === "object" ? JSON.stringify(v) : String(v);
      const truncated = value.length > 20 ? value.slice(0, 20) + "..." : value;
      return `${k}: ${truncated}`;
    })
    .join(", ");
}
