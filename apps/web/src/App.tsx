// The recovery card: Diagnosis (+disclosure) -> Consent -> Receipt,
// driven by apps/api's own live SSE stream (each event arrives as its
// graph node completes, not as one batch at the end).
//
// The client calls `/events` TWICE by design: once after `POST /session`
// (the read pipeline, ending at `consent_required`), and again after
// `POST /session/{id}/consent` (the write pipeline, ending at `receipt`
// or `error`). That is the server's own contract -- consent recording
// and write execution are deliberately separate steps.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  SessionUnauthorizedError,
  createSession,
  deleteSession,
  streamSessionEvents,
  submitConsent,
} from "./api";
import { ConsentScreen } from "./components/ConsentScreen";
import { DiagnosisScreen } from "./components/DiagnosisScreen";
import { ReceiptScreen } from "./components/ReceiptScreen";
import type {
  Candidate,
  DiagnosisEvent,
  ReceiptEvent,
  Screen,
} from "./types";

// G7 (D-G7-05): the second consent+write round (D42) clears `receipt` in
// the graph state and routes back to `diagnose`, all inside one SSE
// stream -- `receipt(round 1) -> diagnosis(round 2) -> options ->
// consent_required`. Replacing a single `receipt` field loses round 1's
// receipt the instant round 2 starts (an adversarial audit of this
// stage's plan caught it before it shipped): the fix is to accumulate.

// G10 (A-G10-04): the session id is an HttpOnly cookie on the wire, so
// this page cannot read it back -- and Silpo's login returns the guest to
// a bare `/`, a fresh load. `sessionStorage` is the app's own copy, per
// tab, gone when the tab closes; a browser that refuses storage (private
// mode, blocked site data) just starts over, never crashes.
const STORAGE_KEY = "lantern_session_id";

function readStoredSession(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredSession(id: string | null): void {
  try {
    if (id === null) {
      sessionStorage.removeItem(STORAGE_KEY);
    } else {
      sessionStorage.setItem(STORAGE_KEY, id);
    }
  } catch {
    // storage unavailable: the login round trip will need a new session
  }
}

function App() {
  const [screen, setScreen] = useState<Screen>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [diagnosis, setDiagnosis] = useState<DiagnosisEvent | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [receipts, setReceipts] = useState<ReceiptEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [authUrl, setAuthUrl] = useState<string>("");
  const [busy, setBusy] = useState(false);
  // Seen live on Render: a cold start keeps `/events` open for 20+ s, and
  // «Вийти» pressed meanwhile left `busy` stuck and let the late stream
  // overwrite the idle screen. Every stream checks it is still the
  // current session before touching state.
  const activeSession = useRef<string | null>(null);

  const consume = useCallback((id: string) => {
    return streamSessionEvents(id, (event) => {
      if (activeSession.current !== id) {
        return;
      }
      if (event.event === "diagnosis") {
        setDiagnosis(event.data as unknown as DiagnosisEvent);
        setScreen("diagnosis");
      } else if (event.event === "options") {
        setCandidates((event.data as { candidates: Candidate[] }).candidates);
      } else if (event.event === "consent_required") {
        setScreen("consent");
      } else if (event.event === "receipt") {
        setReceipts((prev) => [...prev, event.data as unknown as ReceiptEvent]);
        setScreen("receipt");
      } else if (event.event === "error") {
        setError(String((event.data as { error?: string }).error ?? "невідома помилка"));
        setScreen("error");
      }
    });
  }, []);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const session = await createSession();
      setSessionId(session.session_id);
      activeSession.current = session.session_id;
      writeStoredSession(session.session_id);
      setAuthUrl(session.auth_url);
      if (!session.authorized) {
        // The guest logs in at Silpo's own page (phone + OTP) and comes
        // back to /auth/callback; only then does the stream have a
        // credential to read THIS guest's cart with.
        setScreen("auth_required");
        return;
      }
      await consume(session.session_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
      setScreen("error");
    } finally {
      setBusy(false);
    }
  }, [consume]);

  const resume = useCallback(
    async (id: string) => {
      setBusy(true);
      try {
        await consume(id);
      } catch (exc) {
        if (activeSession.current !== id) {
          return; // logged out meanwhile: the outcome no longer matters
        }
        if (exc instanceof SessionUnauthorizedError) {
          // The stored session has no token: login was abandoned, timed
          // out, or the guest logged out elsewhere. Offer it again.
          setAuthUrl("/auth/start");
          setScreen("auth_required");
        } else {
          setError(exc instanceof Error ? exc.message : String(exc));
          setScreen("error");
        }
      } finally {
        if (activeSession.current === id) {
          setBusy(false);
        }
      }
    },
    [consume],
  );

  // Back from Silpo's login on a bare `/`: pick the session up where the
  // redirect dropped it. A GET on `/events` is safe to repeat, so a plain
  // reload here replays rather than re-runs.
  useEffect(() => {
    const stored = readStoredSession();
    if (stored !== null) {
      setSessionId(stored);
      activeSession.current = stored;
      void resume(stored);
    }
  }, [resume]);

  const logout = useCallback(async () => {
    const id = sessionId;
    activeSession.current = null;
    writeStoredSession(null);
    setSessionId(null);
    setBusy(false);
    setDiagnosis(null);
    setCandidates([]);
    setReceipts([]);
    setError(null);
    setScreen("idle");
    if (id !== null) {
      await deleteSession(id).catch(() => undefined);
    }
  }, [sessionId]);

  const consent = useCallback(
    async (actionId: string) => {
      if (sessionId === null) {
        return;
      }
      setBusy(true);
      try {
        await submitConsent(sessionId, actionId);
        // The write itself runs on this second stream, not in the POST.
        await consume(sessionId);
      } catch (exc) {
        setError(String(exc));
        setScreen("error");
      } finally {
        setBusy(false);
      }
    },
    [consume, sessionId],
  );

  return (
    <main>
      <h1>Ліхтарик</h1>

      {/* «Вийти» only once there is a login to end; on the login screen
          the same action is a cancel, not an exit (the author, live). */}
      {sessionId !== null && screen !== "auth_required" && (
        <p>
          <button type="button" onClick={logout} data-testid="logout">
            Вийти
          </button>
        </p>
      )}

      {screen === "idle" && (
        <button type="button" onClick={start} disabled={busy}>
          Перевірити мій кошик
        </button>
      )}

      {screen === "auth_required" && (
        <section aria-labelledby="auth-heading">
          <h2 id="auth-heading">Потрібен вхід у Сільпо</h2>
          <p>
            Щоб побачити саме ваш кошик, увійдіть у Сільпо за номером телефону.
            Застосунок ніколи не бачить ваш пароль чи код із SMS. Після входу ви
            автоматично повернетеся сюди.
          </p>
          <a href={authUrl} data-testid="auth-link">
            Увійти за номером телефону
          </a>
          <p>
            <button type="button" onClick={logout}>
              Скасувати
            </button>
          </p>
        </section>
      )}

      {/* G8 (D51): the compensation pass emits no `diagnosis` event (it
          routes persist_receipt -> write_guard directly, never through
          diagnose), so the last one in state is the PRE-write gap --
          showing it beside an offer to undo the very write that
          partially closed it would be actively misleading. */}
      {(screen === "diagnosis" ||
        (screen === "consent" &&
          !(candidates.length > 0 && candidates.every((c) => c.kind === "compensate")))) && (
        <DiagnosisScreen diagnosis={diagnosis} />
      )}

      {screen === "consent" && (
        <ConsentScreen
          candidates={candidates}
          onConsent={consent}
          submitting={busy}
          priorReceipts={receipts}
        />
      )}

      {screen === "receipt" && receipts.length > 0 && (
        <ReceiptScreen receipts={receipts} />
      )}

      {screen === "error" && (
        <section aria-labelledby="error-heading">
          <h2 id="error-heading">Не вдалося</h2>
          <p data-testid="error-message">{error}</p>
        </section>
      )}
    </main>
  );
}

export default App;
