// The three calls apps/api exposes, plus the SSE stream reader.
//
// The SSE stream is consumed with `fetch` + a ReadableStream reader
// rather than the browser's own `EventSource`, for one measured reason:
// `EventSource` cannot send credentials/headers and cannot be driven by
// a test's mocked `fetch`, and this project's own interface gate is
// Vitest component tests (D-G5-11), not a browser driver. The parsing
// below handles exactly the `event:`/`data:` framing apps/api emits.

import type {
  ConsentAckResponse,
  CreateSessionResponse,
} from "./types";

export const API_BASE = import.meta.env?.VITE_API_BASE ?? "";

export async function createSession(): Promise<CreateSessionResponse> {
  const response = await fetch(`${API_BASE}/session`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`POST /session failed: ${response.status}`);
  }
  return (await response.json()) as CreateSessionResponse;
}

export async function submitConsent(
  sessionId: string,
  actionId: string,
): Promise<ConsentAckResponse> {
  const response = await fetch(`${API_BASE}/session/${sessionId}/consent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // Only `action_id` -- the server recomputes both hashes itself
    // (D-G5-18), so there is deliberately nothing else to send.
    body: JSON.stringify({ action_id: actionId }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.status }));
    throw new Error(String(detail.detail ?? response.status));
  }
  return (await response.json()) as ConsentAckResponse;
}

export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

/** Parses one SSE frame block ("event: x\ndata: {...}") into an object. */
export function parseSseBlock(block: string): SseEvent | null {
  let event = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  if (!event || dataLines.length === 0) {
    return null;
  }
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

/**
 * Opens the session's event stream and calls `onEvent` for each frame as
 * it arrives -- this is what actually drives the graph server-side, so
 * every event lands as its node completes, not in one batch at the end.
 */
export async function streamSessionEvents(
  sessionId: string,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/session/${sessionId}/events`);
  if (!response.ok || !response.body) {
    throw new Error(`GET /session/${sessionId}/events failed: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (parsed) {
        onEvent(parsed);
      }
    }
  }
  const tail = parseSseBlock(buffer);
  if (tail) {
    onEvent(tail);
  }
}
