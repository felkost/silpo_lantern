// B2 (G5+G6 stage spec): the three screens render from real session
// data, the Consent screen's numbers come from the proposal's own typed
// fields (never from `guest_text_uk`), and the a11y smoke passes.
//
// `fetch` is stubbed per test -- no dev server, no apps/api process, no
// network. The SSE body is a real ReadableStream so `streamSessionEvents`
// exercises its actual framing parser, not a mock of it.

import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { parseSseBlock } from "./api";
import { ConsentScreen } from "./components/ConsentScreen";
import { ReceiptScreen } from "./components/ReceiptScreen";
import type { Candidate } from "./types";

const CANDIDATE: Candidate = {
  action_id: "a1",
  product_name: "Молоко «Галичина» 2,5%",
  quantity: "1",
  expected_delta: "39.99",
  guest_text_uk: "Додамо молоко, щоб дотягнути до мінімальної суми.",
  kind: "add",
  compensates_action_id: null,
};

function sseStream(frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      controller.close();
    },
  });
}

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

const ENVELOPE = { session_id: "s1", trace_id: "t1", version: { schema_hash: "h" } };

beforeEach(() => {
  vi.restoreAllMocks();
  // G10: the app resumes a stored session on mount; one test's session
  // must not leak into the next.
  sessionStorage.clear();
});

describe("recovery card", () => {
  it("renders diagnosis then consent from a live event stream", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST" && url.endsWith("/session")) {
          return new Response(
            JSON.stringify({
              session_id: "s1",
              status: "created",
              authorized: true,
              auth_url: "/auth/start",
            }),
            { status: 200 },
          );
        }
        return new Response(
          sseStream([
            frame("diagnosis", {
              ...ENVELOPE,
              primary_code: "order.cost.min",
              gap: "194.11",
              gap_is_borderline: false,
              validations: [
                { code: "order.cost.min", level: "error", type: "cost" },
              ],
              channels: [],
            }),
            frame("options", { ...ENVELOPE, candidates: [CANDIDATE] }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("primary-code")).toHaveTextContent("order.cost.min");
    });
    expect(screen.getByTestId("gap")).toHaveTextContent("194.11");
    expect(screen.getByTestId("product-name")).toHaveTextContent("Молоко");
  });

  it("shows the receipt screen when the write verifies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST" && url.endsWith("/session")) {
          return new Response(
            JSON.stringify({
              session_id: "s1",
              status: "created",
              authorized: true,
              auth_url: "/auth/start",
            }),
            { status: 200 },
          );
        }
        return new Response(
          sseStream([
            frame("receipt", {
              ...ENVELOPE,
              status: "receipt",
              reason: "",
              actual_delta: "39.99",
              blocker_cleared: true,
              remaining_gap: null,
            }),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("receipt-verified")).toBeInTheDocument();
    });
    expect(screen.getByTestId("actual-delta")).toHaveTextContent("39.99");
  });

  it("keeps round 1's receipt visible through a second consent round (D42)", async () => {
    // G7 (D-G7-05): the exact regression an adversarial audit of this
    // stage's plan caught -- `persist_receipt` clears `receipt` and
    // routes back to `diagnose` inside the SAME stream when a verified
    // write does not clear the blocker. Naively replacing `receipt`
    // instead of accumulating loses round 1's proof the instant round 2
    // starts.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST" && url.endsWith("/session")) {
          return new Response(
            JSON.stringify({
              session_id: "s1",
              status: "created",
              authorized: true,
              auth_url: "/auth/start",
            }),
            { status: 200 },
          );
        }
        return new Response(
          sseStream([
            frame("receipt", {
              ...ENVELOPE,
              status: "receipt",
              reason: "",
              actual_delta: "39.99",
              blocker_cleared: false,
              remaining_gap: "2.98",
            }),
            frame("diagnosis", {
              ...ENVELOPE,
              primary_code: "order.cost.min",
              gap: "2.98",
              gap_is_borderline: true,
              validations: [],
              channels: [],
            }),
            frame("options", { ...ENVELOPE, candidates: [CANDIDATE] }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("prior-receipts")).toBeInTheDocument();
    });
    expect(screen.getByTestId("prior-receipt-0")).toHaveTextContent("39.99");
    // The consent screen for round 2 is showing, not the receipt screen.
    expect(screen.getByTestId("product-name")).toBeInTheDocument();
  });

  it("surfaces an error event as its own screen", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST" && url.endsWith("/session")) {
          return new Response(
            JSON.stringify({
              session_id: "s1",
              status: "created",
              authorized: true,
              auth_url: "/auth/start",
            }),
            { status: 200 },
          );
        }
        return new Response(
          sseStream([
            frame("error", { ...ENVELOPE, error: "write refused: state_hash mismatch" }),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toHaveTextContent(
        "write refused: state_hash mismatch",
      );
    });
  });
});

describe("consent screen numbers", () => {
  it("takes every figure from the proposal's typed fields", () => {
    render(<ConsentScreen candidates={[CANDIDATE]} onConsent={() => {}} submitting={false} />);

    expect(screen.getByTestId("quantity")).toHaveTextContent("1");
    expect(screen.getByTestId("expected-delta")).toHaveTextContent("39.99");
    expect(screen.getByTestId("product-name")).toHaveTextContent(CANDIDATE.product_name);
  });

  it("never derives a displayed figure from the model's own sentence", () => {
    // B2's rule: if the explainer's text carried a DIFFERENT number, the
    // figures on screen must still be the proposal's own -- a guest who
    // agrees to what a model wrote, while a different payload executes,
    // has not consented to the write that happens.
    const misleading: Candidate = {
      ...CANDIDATE,
      guest_text_uk: "Це коштуватиме лише 5.00 ₴.",
    };
    render(<ConsentScreen candidates={[misleading]} onConsent={() => {}} submitting={false} />);

    expect(screen.getByTestId("expected-delta")).toHaveTextContent("39.99");
    expect(screen.getByTestId("expected-delta")).not.toHaveTextContent("5.00");
    // The button a guest actually clicks states the typed figure too.
    expect(
      screen.getByRole("button", { name: /39\.99/ }),
    ).toBeInTheDocument();
  });

  it("renders product text as text, never as markup", () => {
    const injected: Candidate = {
      ...CANDIDATE,
      product_name: '<img src=x onerror="alert(1)">',
    };
    const { container } = render(
      <ConsentScreen candidates={[injected]} onConsent={() => {}} submitting={false} />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByTestId("product-name")).toHaveTextContent("<img");
  });
});

describe("receipt screen", () => {
  it("renders `unverified` as its own outcome, not a success", () => {
    render(
      <ReceiptScreen
        receipts={[
          {
            ...ENVELOPE,
            status: "unverified",
            reason: "read-back unreachable",
            actual_delta: null,
            blocker_cleared: false,
            remaining_gap: null,
          },
        ]}
      />,
    );

    expect(screen.getByTestId("receipt-unverified")).toBeInTheDocument();
    expect(screen.queryByTestId("receipt-verified")).toBeNull();
    // The raw developer string is translated to Ukrainian for the guest
    // (D-G7-04) -- it must not appear verbatim on this screen.
    expect(screen.getByTestId("receipt-reason")).not.toHaveTextContent(
      "read-back unreachable",
    );
    expect(screen.getByTestId("receipt-reason")).toHaveTextContent(
      "перевірте кошик",
    );
  });
});

describe("compensation offer (G8, D51)", () => {
  const COMPENSATION_CANDIDATE: Candidate = {
    action_id: "comp-1",
    product_name: "Молоко «Галичина» 2,5%",
    quantity: "-6",
    expected_delta: "-86.84",
    guest_text_uk: "Повернути «Молоко «Галичина» 2,5%» до попередньої кількості.",
    kind: "compensate",
    compensates_action_id: "a1",
  };

  it("renders the undo copy and suppresses the stale pre-write diagnosis", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST" && url.endsWith("/session")) {
          return new Response(
            JSON.stringify({
              session_id: "s1",
              status: "created",
              authorized: true,
              auth_url: "/auth/start",
            }),
            { status: 200 },
          );
        }
        return new Response(
          sseStream([
            frame("diagnosis", {
              ...ENVELOPE,
              primary_code: "order.cost.min",
              gap: "4.00",
              gap_is_borderline: true,
              validations: [],
              channels: [],
            }),
            frame("receipt", {
              ...ENVELOPE,
              status: "receipt",
              reason: "",
              actual_delta: "18.40",
              blocker_cleared: false,
              remaining_gap: "4.00",
            }),
            // No further "diagnosis" event -- persist_receipt routes
            // straight to write_guard for the offer, never through
            // diagnose again.
            frame("options", { ...ENVELOPE, candidates: [COMPENSATION_CANDIDATE] }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("compensation-lede")).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: /повернути кошик як було/i })).toBeInTheDocument();
    // The stale pre-write diagnosis is not rendered on this screen.
    expect(screen.queryByTestId("primary-code")).not.toBeInTheDocument();
    // The offer is opt-in: a real button, not an auto-triggered action.
    expect(screen.getByRole("button", { name: /повернути як було/i })).toBeEnabled();
  });

  it("shows a negative prior-receipt delta as a returned amount, not a raw negative", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST" && url.endsWith("/session")) {
          return new Response(
            JSON.stringify({
              session_id: "s1",
              status: "created",
              authorized: true,
              auth_url: "/auth/start",
            }),
            { status: 200 },
          );
        }
        return new Response(
          sseStream([
            frame("receipt", {
              ...ENVELOPE,
              status: "receipt",
              reason: "",
              actual_delta: "-86.84",
              blocker_cleared: false,
              remaining_gap: "500.77",
            }),
            frame("options", { ...ENVELOPE, candidates: [COMPENSATION_CANDIDATE] }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("prior-receipt-0")).toBeInTheDocument();
    });
    expect(screen.getByTestId("prior-receipt-0")).toHaveTextContent("Повернуто на 86.84");
    expect(screen.getByTestId("prior-receipt-0")).not.toHaveTextContent("-86.84");
  });
});

describe("a11y smoke", () => {
  it("gives every section a heading its aria-labelledby points at", () => {
    const { container } = render(
      <ConsentScreen candidates={[CANDIDATE]} onConsent={() => {}} submitting={false} />,
    );
    const section = container.querySelector("section");
    const labelledBy = section?.getAttribute("aria-labelledby");

    expect(labelledBy).toBeTruthy();
    expect(document.getElementById(labelledBy!)).not.toBeNull();
  });

  it("gives every button an accessible name", () => {
    render(<ConsentScreen candidates={[CANDIDATE]} onConsent={() => {}} submitting={false} />);
    for (const button of screen.getAllByRole("button")) {
      expect(button).toHaveAccessibleName();
    }
  });
});

describe("sse framing", () => {
  it("parses an event/data block", () => {
    expect(parseSseBlock('event: diagnosis\ndata: {"gap":"1.00"}')).toEqual({
      event: "diagnosis",
      data: { gap: "1.00" },
    });
  });

  it("returns null for a block with no event name", () => {
    expect(parseSseBlock('data: {"gap":"1.00"}')).toBeNull();
  });

  it("returns null rather than throwing on malformed data", () => {
    expect(parseSseBlock("event: diagnosis\ndata: {not json")).toBeNull();
  });
});

describe("guest login", () => {
  it("sends an unauthorized session to Silpo's own login first", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST" && url.endsWith("/session")) {
          return new Response(
            JSON.stringify({
              session_id: "s1",
              status: "created",
              authorized: false,
              auth_url: "/auth/start",
            }),
            { status: 200 },
          );
        }
        throw new Error("the event stream must not be opened before login");
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("auth-link")).toBeInTheDocument();
    });
    expect(screen.getByTestId("auth-link")).toHaveAttribute("href", "/auth/start");
    // G10 (A-G10-04): the id survives the round trip through Silpo's login
    // page, which reloads this app on a bare `/`.
    expect(sessionStorage.getItem("lantern_session_id")).toBe("s1");
  });
});

// G10 delivery A: the callback lands on a bare `/`, so the app must find
// its own session again; and reachability without logout is not shipped
// (G10-4).
describe("session round trip and logout", () => {
  it("resumes the stored session on load and streams its events", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? "GET"} ${url}`);
        return new Response(
          sseStream([
            frame("diagnosis", {
              ...ENVELOPE,
              primary_code: "order.cost.min",
              gap: "194.11",
              gap_is_borderline: false,
              validations: [],
              channels: [],
            }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("primary-code")).toHaveTextContent("order.cost.min");
    });
    expect(calls).toEqual(["GET /session/s1/events"]); // no second POST /session
  });

  it("returns to the login screen when the stored session has no token", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "no" }), { status: 401 })),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("auth-link")).toBeInTheDocument();
    });
  });

  it("logs out: DELETE /session, storage cleared, back to the start", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? "GET"} ${url}`);
        if (init?.method === "DELETE") {
          return new Response(null, { status: 204 });
        }
        return new Response(
          sseStream([
            frame("diagnosis", {
              ...ENVELOPE,
              primary_code: "order.cost.min",
              gap: "194.11",
              gap_is_borderline: false,
              validations: [],
              channels: [],
            }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /вийти/i })).toBeInTheDocument();
    });
    await act(async () => {
      screen.getByRole("button", { name: /вийти/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /перевірити мій кошик/i })).toBeInTheDocument();
    });
    expect(calls).toContain("DELETE /session/s1");
    expect(sessionStorage.getItem("lantern_session_id")).toBeNull();
  });

  it("explains a 429 in Ukrainian rather than echoing the status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "cap" }), { status: 429 })),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toHaveTextContent(/ліміт/i);
    });
  });
});
