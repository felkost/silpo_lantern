// The three calls apps/api exposes, plus the SSE stream reader.
//
// The SSE stream is consumed with `fetch` + a ReadableStream reader
// rather than the browser's own `EventSource`, for one measured reason:
// `EventSource` cannot send credentials/headers and cannot be driven by
// a test's mocked `fetch`, and this project's own interface gate is
// Vitest component tests, not a browser driver. The parsing
// below handles exactly the `event:`/`data:` framing apps/api emits.

import type {
  ConsentAckResponse,
  CreateSessionResponse,
  EvidenceResponse,
} from "./types";

export const API_BASE = import.meta.env?.VITE_API_BASE ?? "";

// both spend caps answer 429; the guest gets one plain line,
// never a bare status code.
export const CAP_REACHED_UK =
  "Досягнуто денний ліміт сесій -- спробуйте завтра.";

export class SessionUnauthorizedError extends Error {}

function failed(label: string, status: number): Error {
  if (status === 429) {
    return new Error(CAP_REACHED_UK);
  }
  if (status === 401) {
    return new SessionUnauthorizedError(`${label}: 401`);
  }
  return new Error(`${label} failed: ${status}`);
}

export async function createSession(): Promise<CreateSessionResponse> {
  const response = await fetch(`${API_BASE}/session`, { method: "POST" });
  if (!response.ok) {
    throw failed("POST /session", response.status);
  }
  return (await response.json()) as CreateSessionResponse;
}

/** «Перевірити знову»: a fresh run for the same login. The server answers
 * with the NEW session id and moves the cookie to it. */
export async function restartSession(sessionId: string): Promise<CreateSessionResponse> {
  const response = await fetch(`/session/${sessionId}/restart`, { method: "POST" });
  if (!response.ok) {
    throw failed("POST /session/{id}/restart", response.status);
  }
  return (await response.json()) as CreateSessionResponse;
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/session/${sessionId}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 401) {
    throw failed(`DELETE /session/${sessionId}`, response.status);
  }
}

export async function submitConsent(
  sessionId: string,
  actionId: string,
): Promise<ConsentAckResponse> {
  const response = await fetch(`${API_BASE}/session/${sessionId}/consent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // Only `action_id` -- the server recomputes both hashes itself
    //, so there is deliberately nothing else to send.
    body: JSON.stringify({ action_id: actionId }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.status }));
    throw new Error(String(detail.detail ?? response.status));
  }
  return (await response.json()) as ConsentAckResponse;
}

/** fetched only when the jury asks -- never on mount. */
export async function getEvidence(): Promise<EvidenceResponse> {
  const response = await fetch(`${API_BASE}/evidence`);
  if (!response.ok) {
    throw failed("GET /evidence", response.status);
  }
  return (await response.json()) as EvidenceResponse;
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
    throw failed(`GET /session/${sessionId}/events`, response.status);
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
