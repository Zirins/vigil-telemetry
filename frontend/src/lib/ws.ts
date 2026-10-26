import type { WSMessage } from "@/types";

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ??
  "ws://localhost:8001";

type MessageHandler = (message: WSMessage) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private serviceId: number | null = null;
  private handlers = new Set<MessageHandler>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;

  connect(serviceId: number): void {
    if (
      this.serviceId === serviceId &&
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this.disconnect(false);
    this.serviceId = serviceId;
    this.intentionalClose = false;

    const socket = new WebSocket(`${WS_BASE}/ws/${serviceId}`);
    this.ws = socket;

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data as string) as WSMessage;
        this.handlers.forEach((handler) => handler(message));
      } catch {
        // Ignore malformed frames
      }
    };

    socket.onclose = () => {
      if (!this.intentionalClose && this.serviceId === serviceId) {
        this.reconnectTimer = setTimeout(() => {
          if (this.serviceId === serviceId) {
            this.connect(serviceId);
          }
        }, 3000);
      }
    };
  }

  subscribe(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  disconnect(clearService = true): void {
    this.intentionalClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    if (clearService) {
      this.serviceId = null;
    }
  }
}

export const wsClient = new WebSocketClient();
