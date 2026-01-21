"use client";

import { useSimulationStore } from "@/lib/state/simulationStore";
import { PHASE_COLORS } from "@/lib/pixi/townConfig";

const PHASE_LABELS: Record<string, string> = {
  early_morning: "Early Morning",
  morning: "Morning",
  lunch: "Lunch",
  afternoon: "Afternoon",
  evening: "Evening",
  night: "Night",
};

export function SimulationControls() {
  const isConnected = useSimulationStore((state) => state.isConnected);
  const isRunning = useSimulationStore((state) => state.isRunning);
  const isPaused = useSimulationStore((state) => state.isPaused);
  const currentDay = useSimulationStore((state) => state.currentDay);
  const currentPhase = useSimulationStore((state) => state.currentPhase);
  const phaseDescription = useSimulationStore((state) => state.phaseDescription);

  const phaseColor = PHASE_COLORS[currentPhase] || 0x87ceeb;
  const phaseColorHex = `#${phaseColor.toString(16).padStart(6, "0")}`;

  return (
    <div className="bg-slate-800 rounded-lg p-4 shadow-lg">
      <h2 className="text-lg font-bold mb-3 text-slate-100">Simulation Status</h2>

      {/* Connection Status */}
      <div className="flex items-center gap-2 mb-4">
        <div
          className={`w-3 h-3 rounded-full ${
            isConnected ? "bg-green-500" : "bg-red-500"
          } animate-pulse`}
        />
        <span className="text-sm text-slate-300">
          {isConnected ? "Connected" : "Disconnected"}
        </span>
      </div>

      {/* Day & Phase */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-slate-400 text-sm">Day</span>
          <span className="text-2xl font-bold text-white">{currentDay}</span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-slate-400 text-sm">Phase</span>
          <div className="flex items-center gap-2">
            <div
              className="w-4 h-4 rounded-full"
              style={{ backgroundColor: phaseColorHex }}
            />
            <span className="text-white font-medium">
              {PHASE_LABELS[currentPhase] || currentPhase}
            </span>
          </div>
        </div>

        {phaseDescription && (
          <p className="text-xs text-slate-500 italic">{phaseDescription}</p>
        )}
      </div>

      {/* Status Indicators */}
      <div className="mt-4 pt-4 border-t border-slate-700">
        <div className="flex items-center gap-4">
          <StatusBadge
            label="Running"
            active={isRunning}
            activeColor="bg-green-500"
          />
          <StatusBadge
            label="Paused"
            active={isPaused}
            activeColor="bg-yellow-500"
          />
        </div>
      </div>
    </div>
  );
}

function StatusBadge({
  label,
  active,
  activeColor,
}: {
  label: string;
  active: boolean;
  activeColor: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`w-2 h-2 rounded-full ${
          active ? activeColor : "bg-slate-600"
        }`}
      />
      <span className={`text-xs ${active ? "text-white" : "text-slate-500"}`}>
        {label}
      </span>
    </div>
  );
}
