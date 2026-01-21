"use client";

import { useCallback } from "react";
import { useSimulationStore } from "@/lib/state/simulationStore";
import { PHASE_COLORS } from "@/lib/pixi/townConfig";
import { getWebSocket } from "@/lib/api/websocket";

const PHASE_LABELS: Record<string, string> = {
  early_morning: "Early Morning",
  morning: "Morning",
  lunch: "Lunch",
  afternoon: "Afternoon",
  evening: "Evening",
  night: "Night",
};

const SPEED_OPTIONS = [1, 2, 5, 10];

export function SimulationControls() {
  const isConnected = useSimulationStore((state) => state.isConnected);
  const isRunning = useSimulationStore((state) => state.isRunning);
  const isPaused = useSimulationStore((state) => state.isPaused);
  const currentDay = useSimulationStore((state) => state.currentDay);
  const currentPhase = useSimulationStore((state) => state.currentPhase);
  const phaseDescription = useSimulationStore((state) => state.phaseDescription);
  const simulationSpeed = useSimulationStore((state) => state.simulationSpeed);
  const setSpeed = useSimulationStore((state) => state.setSpeed);
  const reset = useSimulationStore((state) => state.reset);

  const phaseColor = PHASE_COLORS[currentPhase] || 0x87ceeb;
  const phaseColorHex = `#${phaseColor.toString(16).padStart(6, "0")}`;

  const handlePlay = useCallback(() => {
    const ws = getWebSocket();
    ws.play();
  }, []);

  const handlePause = useCallback(() => {
    const ws = getWebSocket();
    ws.pause();
  }, []);

  const handleSpeedChange = useCallback(
    (speed: number) => {
      setSpeed(speed);
      const ws = getWebSocket();
      ws.setSpeed(speed);
    },
    [setSpeed]
  );

  const handleReset = useCallback(() => {
    reset();
    const ws = getWebSocket();
    ws.resetSimulation();
  }, [reset]);

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

      {/* Playback Controls */}
      <div className="mt-4 pt-4 border-t border-slate-700">
        <p className="text-xs text-slate-400 mb-2">Playback</p>
        <div className="flex items-center gap-2 mb-3">
          {/* Play/Pause Button */}
          <button
            onClick={isPaused || !isRunning ? handlePlay : handlePause}
            disabled={!isConnected}
            className={`flex-1 py-2 px-4 rounded-lg font-medium text-sm transition-colors ${
              !isConnected
                ? "bg-slate-700 text-slate-500 cursor-not-allowed"
                : isPaused || !isRunning
                ? "bg-green-600 hover:bg-green-500 text-white"
                : "bg-yellow-600 hover:bg-yellow-500 text-white"
            }`}
          >
            {isPaused || !isRunning ? "▶ Play" : "⏸ Pause"}
          </button>

          {/* Reset Button */}
          <button
            onClick={handleReset}
            disabled={!isConnected}
            className={`py-2 px-4 rounded-lg font-medium text-sm transition-colors ${
              !isConnected
                ? "bg-slate-700 text-slate-500 cursor-not-allowed"
                : "bg-slate-600 hover:bg-slate-500 text-white"
            }`}
            title="Reset simulation"
          >
            ↺
          </button>
        </div>

        {/* Speed Control */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Speed:</span>
          <div className="flex gap-1 flex-1">
            {SPEED_OPTIONS.map((speed) => (
              <button
                key={speed}
                onClick={() => handleSpeedChange(speed)}
                disabled={!isConnected}
                className={`flex-1 py-1 px-2 rounded text-xs font-medium transition-colors ${
                  simulationSpeed === speed
                    ? "bg-blue-600 text-white"
                    : isConnected
                    ? "bg-slate-700 text-slate-300 hover:bg-slate-600"
                    : "bg-slate-700 text-slate-500 cursor-not-allowed"
                }`}
              >
                {speed}x
              </button>
            ))}
          </div>
        </div>
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
