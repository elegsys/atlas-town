/**
 * WebSocket client for connecting to the Atlas Town simulation.
 */

export type EventType =
  | "simulation.started"
  | "simulation.stopped"
  | "simulation.paused"
  | "simulation.resumed"
  | "day.started"
  | "day.completed"
  | "phase.started"
  | "phase.completed"
  | "agent.thinking"
  | "agent.acting"
  | "agent.idle"
  | "agent.speaking"
  | "agent.moving"
  | "tool.called"
  | "tool.completed"
  | "tool.failed"
  | "transaction.created"
  | "invoice.created"
  | "bill.created"
  | "payment.received"
  | "payment.sent"
  | "org.switched"
  | "org.visited"
  | "error";

export interface SimulationEvent {
  id: string;
  type: EventType;
  timestamp: string;
  data: Record<string, unknown>;
  agent?: {
    id: string | null;
    name: string;
    org_id: string | null;
  };
  phase?: {
    day: number;
    name: string;
    description: string;
  };
  tool?: {
    name: string;
    args: Record<string, unknown>;
    result: unknown;
    error: string | null;
    duration_ms: number;
  };
  transaction?: {
    type: string;
    amount: number;
    counterparty: string;
    description: string;
  };
  movement?: {
    agent_id: string;
    agent_name: string;
    from: string;
    to: string;
    reason: string;
  };
  org?: {
    id: string | null;
    name: string;
  };
}

export interface EventHistoryMessage {
  type: "event_history";
  events: SimulationEvent[];
}

export interface SubscribedMessage {
  type: "subscribed";
  event_types: string[];
  org_ids: string[];
}

export type ServerMessage = SimulationEvent | EventHistoryMessage | SubscribedMessage | { type: "pong" };

type EventHandler = (event: SimulationEvent) => void;
type ConnectionHandler = () => void;

export class SimulationWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  private eventHandlers: Map<string, Set<EventHandler>> = new Map();
  private globalHandlers: Set<EventHandler> = new Set();
  private connectHandlers: Set<ConnectionHandler> = new Set();
  private disconnectHandlers: Set<ConnectionHandler> = new Set();
  private isManualClose = false;

  constructor(url: string = "ws://localhost:8765") {
    this.url = url;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.isManualClose = false;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log("[WS] Connected to simulation");
      this.reconnectAttempts = 0;
      this.connectHandlers.forEach((handler) => handler());
    };

    this.ws.onclose = (event) => {
      console.log("[WS] Disconnected", event.code, event.reason);
      this.disconnectHandlers.forEach((handler) => handler());

      if (!this.isManualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        setTimeout(() => this.connect(), delay);
      }
    };

    this.ws.onerror = (error) => {
      console.error("[WS] Error:", error);
    };

    this.ws.onmessage = (message) => {
      try {
        const data = JSON.parse(message.data) as ServerMessage;
        this.handleMessage(data);
      } catch (error) {
        console.error("[WS] Failed to parse message:", error);
      }
    };
  }

  disconnect(): void {
    this.isManualClose = true;
    this.ws?.close();
    this.ws = null;
  }

  private handleMessage(data: ServerMessage): void {
    if (data.type === "event_history") {
      // Handle batch of historical events
      const historyMsg = data as EventHistoryMessage;
      historyMsg.events.forEach((event) => this.dispatchEvent(event));
    } else if (data.type === "subscribed") {
      console.log("[WS] Subscription confirmed:", data);
    } else if (data.type === "pong") {
      // Heartbeat response
    } else {
      // Regular simulation event
      this.dispatchEvent(data as SimulationEvent);
    }
  }

  private dispatchEvent(event: SimulationEvent): void {
    // Call type-specific handlers
    const handlers = this.eventHandlers.get(event.type);
    handlers?.forEach((handler) => handler(event));

    // Call global handlers
    this.globalHandlers.forEach((handler) => handler(event));
  }

  /**
   * Subscribe to specific event types.
   */
  subscribe(eventTypes?: EventType[], orgIds?: string[]): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      console.warn("[WS] Cannot subscribe: not connected");
      return;
    }

    this.ws.send(
      JSON.stringify({
        type: "subscribe",
        event_types: eventTypes || [],
        org_ids: orgIds || [],
      })
    );
  }

  /**
   * Unsubscribe from event types.
   */
  unsubscribe(eventTypes?: EventType[], orgIds?: string[]): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return;
    }

    this.ws.send(
      JSON.stringify({
        type: "unsubscribe",
        event_types: eventTypes || [],
        org_ids: orgIds || [],
      })
    );
  }

  /**
   * Register a handler for a specific event type.
   */
  on(eventType: EventType, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.eventHandlers.get(eventType)?.delete(handler);
    };
  }

  /**
   * Register a handler for all events.
   */
  onAny(handler: EventHandler): () => void {
    this.globalHandlers.add(handler);
    return () => {
      this.globalHandlers.delete(handler);
    };
  }

  /**
   * Register a handler for connection events.
   */
  onConnect(handler: ConnectionHandler): () => void {
    this.connectHandlers.add(handler);
    return () => {
      this.connectHandlers.delete(handler);
    };
  }

  /**
   * Register a handler for disconnection events.
   */
  onDisconnect(handler: ConnectionHandler): () => void {
    this.disconnectHandlers.add(handler);
    return () => {
      this.disconnectHandlers.delete(handler);
    };
  }

  /**
   * Send a ping to check connection.
   */
  ping(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "ping" }));
    }
  }

  /**
   * Check if connected.
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Global singleton instance
let wsInstance: SimulationWebSocket | null = null;

export function getWebSocket(url?: string): SimulationWebSocket {
  if (!wsInstance) {
    wsInstance = new SimulationWebSocket(url);
  }
  return wsInstance;
}
