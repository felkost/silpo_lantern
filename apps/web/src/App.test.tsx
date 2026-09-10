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
  args_hash: "a".repeat(64),
  tool_name: "silpo_add_or_update_cart_products",
  evidence: [],
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
            expected_delta: "39.99",
            verified: false,
            kind: "add",
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
    args_hash: "b".repeat(64),
    tool_name: "silpo_remove_cart_products",
    evidence: [],
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
    // The author, walking it live: «Я увійшов — продовжити» did nothing
    // (the callback already returns the guest here) and «Вийти» offered an
    // exit from a login that had not happened. One link, one way back.
    expect(screen.queryByRole("button", { name: /увійшов/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /вийти/i })).toBeNull();
    expect(screen.getByRole("button", { name: /скасувати/i })).toBeInTheDocument();
  });

  it("«Скасувати» on the login screen returns to the start", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === "DELETE") {
          return new Response(null, { status: 204 });
        }
        return new Response(
          JSON.stringify({ session_id: "s1", status: "created", authorized: false, auth_url: "/auth/start" }),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /перевірити мій кошик/i }).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: /скасувати/i }).click();
    });

    expect(screen.getByRole("button", { name: /перевірити мій кошик/i })).toBeEnabled();
    expect(sessionStorage.getItem("lantern_session_id")).toBeNull();
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

  it("logging out mid-stream re-enables the start button and drops late events", async () => {
    // Seen live on Render: a cold start keeps `/events` open for 20+ s;
    // «Вийти» pressed meanwhile left `busy` stuck and the late stream
    // overwrote the idle screen.
    sessionStorage.setItem("lantern_session_id", "s1");
    let release: (() => void) | null = null;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === "DELETE") {
          return new Response(null, { status: 204 });
        }
        await gate;
        return new Response(
          sseStream([frame("error", { ...ENVELOPE, error: "late" })]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /вийти/i }).click();
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /перевірити мій кошик/i })).toBeEnabled();
    });
    await act(async () => {
      release!();
    });

    expect(screen.queryByTestId("error-message")).toBeNull();
    expect(screen.getByRole("button", { name: /перевірити мій кошик/i })).toBeEnabled();
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

// G10 delivery C: the console shell. Theme is the one control on the
// shared header; it writes `data-theme` so an explicit choice wins over
// `prefers-color-scheme` in both directions.
describe("console shell", () => {
  it("toggles the theme both ways and survives blocked storage", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("nothing fetches on mount"); }));
    document.documentElement.removeAttribute("data-theme");
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    render(<App />);
    const toggle = screen.getByRole("switch", { name: /theme/i });
    await act(async () => { toggle.click(); });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    await act(async () => { screen.getByRole("switch", { name: /theme/i }).click(); });
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");

    setItem.mockRestore();
  });

  it("names the product and nothing else in the footer", () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("nothing fetches on mount"); }));
    render(<App />);
    expect(screen.getByRole("contentinfo")).toHaveTextContent(/^silpo lantern$/);
  });
});

// G10 delivery C: the stage feed is an append-only log of nodes the
// stream reported -- repeats shown as repeats, nothing pre-drawn, nothing
// pending -- because the graph's own paths (retry -> diagnose again, a
// compensation round entering write_guard directly) make any checklist a
// promise the run may not keep.
describe("stage feed", () => {
  it("lists observed nodes in arrival order with their io kind, repeats included", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          sseStream([
            frame("stage", { ...ENVELOPE, node: "read", io: "mcp" }),
            frame("stage", { ...ENVELOPE, node: "diagnose", io: "pure" }),
            frame("stage", { ...ENVELOPE, node: "plan", io: "llm" }),
            frame("stage", { ...ENVELOPE, node: "diagnose", io: "pure" }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        ),
      ),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByTestId("stage-row")).toHaveLength(4);
    });
    const rows = screen.getAllByTestId("stage-row").map((r) => r.textContent);
    expect(rows[0]).toMatch(/read/);
    expect(rows[0]).toMatch(/mcp/i);
    expect(rows[2]).toMatch(/plan/);
    expect(rows[2]).toMatch(/llm/i);
    expect(rows[3]).toMatch(/diagnose/);
    expect(screen.queryByText(/pending/i)).toBeNull();
  });
});

// G10 delivery C: the claim panel is organised by what a field PROVES,
// not where it came from (D-G10-03). Live evidence only; anything not seen
// in this session says so.
describe("claim panel", () => {
  function sessionStream() {
    return sseStream([
      frame("diagnosis", {
        ...ENVELOPE,
        primary_code: "order.cost.min",
        gap: "194.11",
        gap_is_borderline: false,
        products_total: "404.89",
        threshold_source: "validation_context",
        validations: [
          { code: "order.cost.min", level: "error", type: "cost", is_known: true },
          { code: "timeslot.not_found", level: "error", type: "slot", is_known: false },
        ],
        channels: [],
      }),
      frame("options", {
        ...ENVELOPE,
        candidates: [
          {
            ...CANDIDATE,
            args_hash: "c".repeat(64),
            tool_name: "silpo_add_or_update_cart_products",
            evidence: [
              { price: "39.99", availability: true, source_tool: "silpo_find_products_batch", captured_at: "2026-09-07T12:00:00+00:00" },
            ],
          },
        ],
      }),
      frame("consent_required", ENVELOPE),
    ]);
  }

  it("says what was not observed before anything runs", () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("nothing fetches on mount"); }));
    render(<App />);
    expect(screen.getAllByText(/not observed in this session/i).length).toBeGreaterThanOrEqual(4);
  });

  it("shows the arithmetic inputs, the unknown code and the candidate hash from the live stream", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(sessionStream(), { status: 200 })));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("claim-arithmetic")).toHaveTextContent("404.89");
    });
    expect(screen.getByTestId("claim-arithmetic")).toHaveTextContent("194.11");
    expect(screen.getByTestId("claim-arithmetic")).toHaveTextContent("validation_context");
    expect(screen.getByTestId("claim-disclosure")).toHaveTextContent("timeslot.not_found");
    expect(screen.getByTestId("claim-disclosure")).toHaveTextContent(/unknown/i);
    expect(screen.getByTestId("claim-consent")).toHaveTextContent("c".repeat(64).slice(0, 12));
  });

  it("shows the recorded binding after consent, and the read-back after the receipt", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    let phase = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST" && url.endsWith("/consent")) {
          return new Response(
            JSON.stringify({ status: "consent_recorded", action_id: "a1", args_hash: "c".repeat(64), state_hash: "d".repeat(64), expires_at: "2026-09-07T12:05:00+00:00" }),
            { status: 200 },
          );
        }
        phase += 1;
        if (phase === 1) {
          return new Response(sessionStream(), { status: 200 });
        }
        return new Response(
          sseStream([
            frame("receipt", { ...ENVELOPE, status: "receipt", reason: "", expected_delta: "39.99", actual_delta: "35.99", verified: true, kind: "add", blocker_cleared: false, remaining_gap: "4.00" }),
          ]),
          { status: 200 },
        );
      }),
    );

    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /39\.99/ })).toBeInTheDocument();
    });
    await act(async () => {
      screen.getByRole("button", { name: /39\.99/ }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("claim-consent")).toHaveTextContent("d".repeat(64).slice(0, 12));
    });
    expect(screen.getByTestId("claim-readback")).toHaveTextContent("39.99");
    expect(screen.getByTestId("claim-readback")).toHaveTextContent("35.99");
    expect(screen.getByTestId("claim-readback")).toHaveTextContent(/verified/i);
  });

  it("loads measured evidence only on request and shows n, interval and the command", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/evidence")) {
          return new Response(
            JSON.stringify({
              population: "offline",
              generated_at: "2026-09-10T17:43:23+00:00",
              regenerate: "python -m scripts.compute_metrics --tracked",
              metrics: [
                { name: "ReadbackCoverage", value: 1.0, n: 33, interval: [0.8957, 1.0], caveat: "Gate 1.00." },
                { name: "FalseRecovery", value: 0.0, n: 33, interval: null, caveat: "A count." },
              ],
              disclosure: {
                state: "Baseline cart, below the minimum order sum",
                observed_at: "2026-09-10",
                products_total: 461.82,
                app_showed: ["Мінімальна сума замовлення 699.00 ₴"],
                validations: [
                  { code: "order.cost.min", level: "error", rendered_by_app: true },
                  { code: "order.payment_types.disabled", level: "info", rendered_by_app: false },
                ],
              },
            }),
            { status: 200 },
          );
        }
        throw new Error(`unexpected fetch ${url}`);
      }),
    );

    render(<App />);
    expect(fetch).not.toHaveBeenCalled();
    await act(async () => {
      screen.getByRole("button", { name: /load measured evidence/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("measured-earlier")).toHaveTextContent("ReadbackCoverage");
    });
    const block = screen.getByTestId("measured-earlier");
    expect(block).toHaveTextContent("n = 33");
    expect(block).toHaveTextContent("[0.90, 1.00]");
    expect(block).toHaveTextContent("python -m scripts.compute_metrics --tracked");
    expect(block).toHaveTextContent("2026-09-10");
    expect(block).toHaveTextContent("offline");
    // claim 1's audited check: which code the app rendered, and which it did not
    expect(screen.getByTestId("claim-disclosure")).toHaveTextContent("order.payment_types.disabled");
    expect(screen.getByTestId("claim-disclosure")).toHaveTextContent(/not rendered/i);
  });

  it("drops the stale diagnosis from the panel on the compensation screen", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          sseStream([
            frame("diagnosis", { ...ENVELOPE, primary_code: "order.cost.min", gap: "194.11", gap_is_borderline: false, products_total: "404.89", threshold_source: "validation_context", validations: [], channels: [] }),
            frame("receipt", { ...ENVELOPE, status: "receipt", reason: "", expected_delta: "39.99", actual_delta: "39.99", verified: true, kind: "add", blocker_cleared: false, remaining_gap: "154.12" }),
            frame("options", { ...ENVELOPE, candidates: [{ ...CANDIDATE, action_id: "c1", kind: "compensate", compensates_action_id: "a1", args_hash: "e".repeat(64), tool_name: "silpo_remove_cart_products", evidence: [] }] }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        ),
      ),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("compensation-lede")).toBeInTheDocument();
    });
    expect(screen.getByTestId("claim-arithmetic")).not.toHaveTextContent("194.11");
  });
});

// G10: the answer rating lives in React state only (author's decision:
// session state, never Neon). Nothing leaves the browser.
describe("answer rating", () => {
  it("records a score and a comment without any request", async () => {
    const fetchSpy = vi.fn(async () => { throw new Error("nothing fetches"); });
    vi.stubGlobal("fetch", fetchSpy);

    render(<App />);
    await act(async () => {
      screen.getByRole("button", { name: /rate 4 of 5/i }).click();
    });

    expect(screen.getByTestId("rating-value")).toHaveTextContent("4 / 5");
    expect(screen.getByRole("button", { name: /rate 4 of 5/i })).toHaveAttribute("aria-pressed", "true");
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// G10 step 7b (D90): spend is shown as spend -- tokens, dollars, the
// project's ceiling -- never as a remaining balance.
describe("token economics", () => {
  it("shows the session's cumulative spend from the last stage frame, never a remainder", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          sseStream([
            frame("stage", { ...ENVELOPE, node: "read", io: "mcp", usage: { tokens: 0, cost_usd: 0, ceiling_usd: 20 } }),
            frame("stage", { ...ENVELOPE, node: "plan", io: "llm", usage: { tokens: 1100, cost_usd: 0.001125, ceiling_usd: 20 } }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        ),
      ),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("spend")).toHaveTextContent("1100 tokens");
    });
    expect(screen.getByTestId("spend")).toHaveTextContent("$0.0011");
    expect(screen.getByTestId("spend")).toHaveTextContent("ceiling $20");
    expect(screen.getByTestId("spend")).not.toHaveTextContent(/remaining/i);
  });
});

// Author's live feedback after the first console session: the panel, the
// pile of identical validation lines and the loading state need Ukrainian
// explanations. Technical identifiers stay English (A-G10-02); the words
// that explain them are for the reader.
describe("explanations", () => {
  it("every panel block carries a Ukrainian «Що це?» explanation", () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("nothing fetches"); }));
    render(<App />);
    const helps = screen.getAllByText(/^Що це\?$/);
    expect(helps.length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText(/MCP — читання/)).toBeInTheDocument();
  });

  it("groups identical validation lines with a count and explains an unknown reason", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          sseStream([
            frame("diagnosis", {
              ...ENVELOPE,
              primary_code: null,
              gap: null,
              gap_is_borderline: false,
              products_total: "404.89",
              threshold_source: "unverified",
              validations: [
                { code: "timeslot.not_found", level: "error", type: "slot", is_known: false },
                { code: "product.offer.stock.max", level: "error", type: "stock", is_known: true },
                { code: "product.offer.stock.max", level: "error", type: "stock", is_known: true },
                { code: "product.offer.stock.max", level: "error", type: "stock", is_known: true },
              ],
              channels: [],
            }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        ),
      ),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("primary-code")).toHaveTextContent("невідома");
    });
    expect(screen.getByTestId("validation-product.offer.stock.max")).toHaveTextContent("× 3");
    expect(screen.getAllByTestId("validation-product.offer.stock.max")).toHaveLength(1);
    expect(screen.getByTestId("unknown-reason")).toHaveTextContent(/не є відомим правилом/);
  });
});

// The same grouping the card does (× 10), on the panel's first claim --
// the live screen listed ten identical lines there too.
describe("claim panel grouping", () => {
  it("groups identical validation codes with a count", async () => {
    sessionStorage.setItem("lantern_session_id", "s1");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          sseStream([
            frame("diagnosis", {
              ...ENVELOPE, primary_code: null, gap: null, gap_is_borderline: false,
              products_total: "605.62", threshold_source: "unverified",
              validations: [
                { code: "product.offer.stock.max", level: "error", type: "stock", is_known: true },
                { code: "product.offer.stock.max", level: "error", type: "stock", is_known: true },
              ],
              channels: [],
            }),
            frame("consent_required", ENVELOPE),
          ]),
          { status: 200 },
        ),
      ),
    );
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("claim-disclosure")).toHaveTextContent("product.offer.stock.max");
    });
    expect(screen.getByTestId("claim-disclosure").textContent?.match(/product\.offer\.stock\.max/g)).toHaveLength(1);
    expect(screen.getByTestId("claim-disclosure")).toHaveTextContent("× 2");
  });
});
