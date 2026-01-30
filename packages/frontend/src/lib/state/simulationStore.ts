/**
 * Zustand store for simulation state.
 */

import { create } from "zustand";
import { SimulationEvent } from "../api/websocket";

// Agent state for visualization
export interface AgentState {
  id: string;
  name: string;
  type: "accountant" | "owner" | "customer" | "vendor";
  status: "idle" | "thinking" | "acting" | "speaking" | "moving";
  currentLocation: string;
  targetLocation: string | null;
  currentMessage: string | null;
  orgId: string | null;
}

// Organization state with financial metrics
export interface OrgState {
  id: string;
  name: string;
  industry: string;
  owner: string | null;
  // Financial metrics
  totalAR: number; // Accounts Receivable
  totalAP: number; // Accounts Payable
  cashBalance: number;
  invoiceCount: number;
  billCount: number;
}

// Financial summary across all organizations
export interface FinancialSummary {
  totalAR: number;
  totalAP: number;
  totalCash: number;
  dailyTransactionCount: number;
  byOrg: Map<string, OrgFinancials>;
}

export interface OrgFinancials {
  orgId: string;
  orgName: string;
  industry: string;
  ar: number;
  ap: number;
  cash: number;
  transactions: number;
}

// Phase state
export interface PhaseState {
  day: number;
  phase: string;
  description: string;
}

// Transaction for the feed
export interface Transaction {
  id: string;
  timestamp: string;
  type: string;
  orgName: string;
  amount: number;
  counterparty: string;
  description: string;
}

// Simulation store state
interface SimulationState {
  // Connection status
  isConnected: boolean;
  setConnected: (connected: boolean) => void;

  // Simulation status
  isRunning: boolean;
  isPaused: boolean;
  simulationSpeed: number; // 1, 2, 5, 10
  setSpeed: (speed: number) => void;

  // Time tracking
  currentDay: number;
  currentPhase: string;
  phaseDescription: string;

  // Agents
  agents: Map<string, AgentState>;
  updateAgent: (id: string, update: Partial<AgentState>) => void;
  setAgentLocation: (id: string, location: string) => void;
  setAgentStatus: (id: string, status: AgentState["status"]) => void;
  setAgentMessage: (id: string, message: string | null) => void;

  // Organizations
  organizations: Map<string, OrgState>;
  currentOrgId: string | null;

  // Transactions feed
  transactions: Transaction[];
  addTransaction: (tx: Transaction) => void;

  // Event history
  recentEvents: SimulationEvent[];
  addEvent: (event: SimulationEvent) => void;

  // Financial summary
  financialSummary: FinancialSummary;
  updateOrgFinancials: (orgId: string, updates: Partial<OrgFinancials>) => void;

  // Process incoming events
  processEvent: (event: SimulationEvent) => void;

  // Reset
  reset: () => void;
}

const MAX_TRANSACTIONS = 50;
const MAX_EVENTS = 100;

/**
 * Map agent names to their IDs.
 * Handles various name formats from backend events.
 */
const AGENT_NAME_TO_ID: Record<string, string> = {
  "Sarah Chen": "sarah",
  "sarah": "sarah",
  "Craig Miller": "craig",
  "craig": "craig",
  "Tony Russo": "tony",
  "tony": "tony",
  "Maya Patel": "maya",
  "maya": "maya",
  "Dr. Emily Chen": "chen",
  "Emily Chen": "chen",
  "chen": "chen",
  "Marcus Johnson": "marcus",
  "marcus": "marcus",
};

/**
 * Resolve agent ID from event data.
 * Tries movement.agent_id, agent.name, and agent.id.
 */
function resolveAgentId(event: SimulationEvent): string | null {
  // Try movement agent_id first (most reliable for movement events)
  if (event.movement?.agent_id) {
    const id = AGENT_NAME_TO_ID[event.movement.agent_id] || event.movement.agent_id;
    if (id) return id;
  }
  // Try movement agent_name
  if (event.movement?.agent_name) {
    const id = AGENT_NAME_TO_ID[event.movement.agent_name];
    if (id) return id;
  }
  // Try agent.name
  if (event.agent?.name) {
    const id = AGENT_NAME_TO_ID[event.agent.name];
    if (id) return id;
  }
  // Try agent.id directly
  if (event.agent?.id) {
    const id = AGENT_NAME_TO_ID[event.agent.id] || event.agent.id;
    if (id) return id;
  }
  return null;
}

export const useSimulationStore = create<SimulationState>((set, get) => ({
  // Connection
  isConnected: false,
  setConnected: (connected) => set({ isConnected: connected }),

  // Simulation status
  isRunning: false,
  isPaused: false,
  simulationSpeed: 1,
  setSpeed: (speed) => set({ simulationSpeed: speed }),

  // Time
  currentDay: 1,
  currentPhase: "early_morning",
  phaseDescription: "",

  // Agents - initialize all 6 agents
  agents: new Map([
    [
      "sarah",
      {
        id: "sarah",
        name: "Sarah Chen",
        type: "accountant",
        status: "idle",
        currentLocation: "office",
        targetLocation: null,
        currentMessage: null,
        orgId: null,
      },
    ],
    [
      "craig",
      {
        id: "craig",
        name: "Craig Miller",
        type: "owner",
        status: "idle",
        currentLocation: "craigs_landscaping",
        targetLocation: null,
        currentMessage: null,
        orgId: null,
      },
    ],
    [
      "tony",
      {
        id: "tony",
        name: "Tony Russo",
        type: "owner",
        status: "idle",
        currentLocation: "tonys_pizzeria",
        targetLocation: null,
        currentMessage: null,
        orgId: null,
      },
    ],
    [
      "maya",
      {
        id: "maya",
        name: "Maya Patel",
        type: "owner",
        status: "idle",
        currentLocation: "nexus_tech",
        targetLocation: null,
        currentMessage: null,
        orgId: null,
      },
    ],
    [
      "chen",
      {
        id: "chen",
        name: "Dr. Emily Chen",
        type: "owner",
        status: "idle",
        currentLocation: "main_street_dental",
        targetLocation: null,
        currentMessage: null,
        orgId: null,
      },
    ],
    [
      "marcus",
      {
        id: "marcus",
        name: "Marcus Johnson",
        type: "owner",
        status: "idle",
        currentLocation: "harbor_realty",
        targetLocation: null,
        currentMessage: null,
        orgId: null,
      },
    ],
  ]),

  updateAgent: (id, update) =>
    set((state) => {
      const agents = new Map(state.agents);
      const agent = agents.get(id);
      if (agent) {
        agents.set(id, { ...agent, ...update });
      }
      return { agents };
    }),

  setAgentLocation: (id, location) =>
    set((state) => {
      const agents = new Map(state.agents);
      const agent = agents.get(id);
      if (agent) {
        agents.set(id, { ...agent, currentLocation: location, targetLocation: null });
      }
      return { agents };
    }),

  setAgentStatus: (id, status) =>
    set((state) => {
      const agents = new Map(state.agents);
      const agent = agents.get(id);
      if (agent) {
        agents.set(id, { ...agent, status });
      }
      return { agents };
    }),

  setAgentMessage: (id, message) =>
    set((state) => {
      const agents = new Map(state.agents);
      const agent = agents.get(id);
      if (agent) {
        agents.set(id, { ...agent, currentMessage: message });
      }
      return { agents };
    }),

  // Organizations
  organizations: new Map(),
  currentOrgId: null,

  // Financial summary
  financialSummary: {
    totalAR: 0,
    totalAP: 0,
    totalCash: 0,
    dailyTransactionCount: 0,
    byOrg: new Map(),
  },

  updateOrgFinancials: (orgId, updates) =>
    set((state) => {
      const byOrg = new Map(state.financialSummary.byOrg);
      const existing = byOrg.get(orgId) || {
        orgId,
        orgName: "",
        industry: "",
        ar: 0,
        ap: 0,
        cash: 0,
        transactions: 0,
      };
      byOrg.set(orgId, { ...existing, ...updates });

      // Recalculate totals
      let totalAR = 0;
      let totalAP = 0;
      let totalCash = 0;
      let dailyTransactionCount = 0;
      byOrg.forEach((org) => {
        totalAR += org.ar;
        totalAP += org.ap;
        totalCash += org.cash;
        dailyTransactionCount += org.transactions;
      });

      return {
        financialSummary: {
          ...state.financialSummary,
          totalAR,
          totalAP,
          totalCash,
          dailyTransactionCount,
          byOrg,
        },
      };
    }),

  // Transactions
  transactions: [],
  addTransaction: (tx) =>
    set((state) => ({
      transactions: [tx, ...state.transactions].slice(0, MAX_TRANSACTIONS),
    })),

  // Events
  recentEvents: [],
  addEvent: (event) =>
    set((state) => ({
      recentEvents: [event, ...state.recentEvents].slice(0, MAX_EVENTS),
    })),

  // Process events from WebSocket
  processEvent: (event) => {
    const state = get();

    // Add to event history
    state.addEvent(event);

    switch (event.type) {
      case "simulation.started":
        set({ isRunning: true, isPaused: false });
        break;

      case "simulation.stopped":
        set({ isRunning: false, isPaused: false });
        break;

      case "simulation.paused":
        set({ isPaused: true });
        break;

      case "simulation.resumed":
        set({ isPaused: false });
        break;

      case "day.started":
        if (event.phase) {
          set({ currentDay: event.phase.day });
        }
        break;

      case "phase.started":
        if (event.phase) {
          set({
            currentPhase: event.phase.name,
            phaseDescription: event.phase.description,
          });
        }
        break;

      case "agent.thinking": {
        const agentId = resolveAgentId(event);
        if (agentId) {
          state.setAgentStatus(agentId, "thinking");
          state.setAgentMessage(agentId, "Thinking...");
        }
        break;
      }

      case "agent.speaking": {
        const agentId = resolveAgentId(event);
        if (agentId && event.data?.message) {
          state.setAgentStatus(agentId, "speaking");
          state.setAgentMessage(agentId, event.data.message as string);
          // Clear message after a delay
          setTimeout(() => {
            state.setAgentMessage(agentId, null);
            state.setAgentStatus(agentId, "idle");
          }, 5000);
        }
        break;
      }

      case "agent.moving": {
        const agentId = resolveAgentId(event);
        if (agentId && event.movement) {
          state.updateAgent(agentId, {
            status: "moving",
            targetLocation: event.movement.to,
            currentMessage: `Walking to ${event.movement.to}`,
          });
          // Simulate arrival after animation
          setTimeout(() => {
            state.setAgentLocation(agentId, event.movement!.to);
            state.setAgentStatus(agentId, "idle");
            state.setAgentMessage(agentId, null);
          }, 2000);
        }
        break;
      }

      case "agent.idle": {
        const agentId = resolveAgentId(event);
        if (agentId) {
          state.setAgentStatus(agentId, "idle");
          state.setAgentMessage(agentId, null);
        }
        break;
      }

      case "org.visited": {
        const agentId = resolveAgentId(event);
        if (agentId && event.agent?.org_id) {
          set({ currentOrgId: event.agent.org_id });
          state.updateAgent(agentId, {
            orgId: event.agent.org_id,
          });
        }
        break;
      }

      case "invoice.created":
      case "bill.created":
      case "payment.received":
      case "payment.sent":
      case "transaction.created":
        if (event.transaction && event.org) {
          const orgId = event.org.id || "unknown";
          const amount = event.transaction.amount;
          const txType = event.transaction.type;

          state.addTransaction({
            id: event.id,
            timestamp: event.timestamp,
            type: txType,
            orgName: event.org.name,
            amount: amount,
            counterparty: event.transaction.counterparty,
            description: event.transaction.description,
          });

          // Update financial metrics for the organization
          const currentOrg = state.financialSummary.byOrg.get(orgId) || {
            orgId,
            orgName: event.org.name,
            industry: "",
            ar: 0,
            ap: 0,
            cash: 0,
            transactions: 0,
          };

          const updates: Partial<OrgFinancials> = {
            orgName: event.org.name,
            transactions: currentOrg.transactions + 1,
          };

          // Update AR/AP/Cash based on transaction type
          if (txType === "invoice" || txType === "invoice_created") {
            updates.ar = currentOrg.ar + amount;
          } else if (txType === "bill" || txType === "bill_created") {
            updates.ap = currentOrg.ap + amount;
          } else if (txType === "payment_received") {
            updates.ar = Math.max(0, currentOrg.ar - amount);
            updates.cash = currentOrg.cash + amount;
          } else if (txType === "payment_sent") {
            updates.ap = Math.max(0, currentOrg.ap - amount);
            updates.cash = currentOrg.cash - amount;
          }

          state.updateOrgFinancials(orgId, updates);
        }
        break;

      case "error":
        console.error("[Simulation Error]", event.data);
        break;
    }
  },

  // Reset
  reset: () =>
    set({
      isRunning: false,
      isPaused: false,
      simulationSpeed: 1,
      currentDay: 1,
      currentPhase: "early_morning",
      phaseDescription: "",
      currentOrgId: null,
      transactions: [],
      recentEvents: [],
      financialSummary: {
        totalAR: 0,
        totalAP: 0,
        totalCash: 0,
        dailyTransactionCount: 0,
        byOrg: new Map(),
      },
      agents: new Map([
        [
          "sarah",
          {
            id: "sarah",
            name: "Sarah Chen",
            type: "accountant",
            status: "idle",
            currentLocation: "office",
            targetLocation: null,
            currentMessage: null,
            orgId: null,
          },
        ],
      ]),
    }),
}));
