import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AxonLoop from "./AxonLoop.jsx";
import { api, loadAll } from "./api.js";
import {
  ApprovalCard,
  AuditFeed,
  AutonomyLedger,
  CapabilityCounter,
  EvidencePanel,
  KillSwitch,
  LiveBadge,
  MonitorPanel,
  SkillPassport,
  TrustBoundary,
} from "./panels.jsx";

const REFRESH_MS = 3000;

export default function App() {
  const [data, setData] = useState(null);
  const [passport, setPassport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // Refusals are transient — they are an EVENT, not a state the system
  // stays in, so the red flash is driven by a timer rather than by polling
  // finding a leftover flag.
  const [refusal, setRefusal] = useState(false);
  const refusalTimer = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const next = await loadAll();
      setData(next);
      setError(next.online ? null : "aion-core unreachable");
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const acquired = useMemo(() => {
    const tracked = data?.autonomy?.capabilities || [];
    return tracked.filter((c) => c.passport);
  }, [data]);

  // Show the most recently acquired capability by default: the passport
  // people want is almost always the newest one.
  useEffect(() => {
    if (!passport && acquired.length) {
      setPassport(acquired[acquired.length - 1].name);
    }
  }, [acquired, passport]);

  useEffect(() => {
    if (!passport) return;

    api
      .passport(passport)
      .then((body) => setData((d) => ({ ...d, selected: body })))
      .catch(() => {});
  }, [passport, data?.capabilities?.implemented]);

  const pending = data?.pending?.pending || [];
  const killed = !!data?.root?.kill_switch_active;

  const loopState = refusal
    ? "refusal"
    : killed
    ? "refusal"
    : pending.length
    ? "approval"
    : busy
    ? "working"
    : "idle";

  const activePhase = refusal || killed
    ? "govern"
    : pending.length
    ? "govern"
    : busy
    ? "execute"
    : null;

  const flashRefusal = () => {
    setRefusal(true);
    clearTimeout(refusalTimer.current);
    refusalTimer.current = setTimeout(() => setRefusal(false), 2000);
  };

  const decide = async (id, approved) => {
    setBusy(true);
    try {
      await api.decide(id, approved);
      if (!approved) flashRefusal();
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleKill = async (next) => {
    setBusy(true);
    try {
      await api.setKillSwitch(next);
      if (next) flashRefusal();
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen px-5 py-6 max-w-[1180px] mx-auto">
      <header className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-lg tracking-[0.2em] font-semibold">AION AXON</h1>
          <p className="text-[11px] text-muted">
            A governed agent that earns permission to become more capable.
          </p>
        </div>
        <LiveBadge online={!!data?.online} />
      </header>

      {error && (
        <p className="mb-4 text-[11px] text-danger border border-danger/40 rounded px-3 py-2">
          {error}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_1.15fr_1fr]">
        <div className="space-y-4">
          <CapabilityCounter
            implemented={data?.capabilities?.implemented}
            total={data?.capabilities?.total}
          />
          <AutonomyLedger
            tracked={data?.autonomy?.capabilities || []}
            threshold={data?.autonomy?.supervision_threshold ?? 40}
          />
          <TrustBoundary sandbox={data?.sandbox} />
        </div>

        <div className="space-y-4">
          <section className="bg-panel border border-edge rounded-lg p-4">
            <AxonLoop state={loopState} activePhase={activePhase} />
          </section>
          <ApprovalCard pending={pending} onDecide={decide} busy={busy} />
          <KillSwitch active={killed} onToggle={toggleKill} busy={busy} />
        </div>

        <div className="space-y-4">
          <EvidencePanel capability={data?.selected} />
          <SkillPassport capability={data?.selected} />
          {acquired.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {acquired.map((c) => (
                <button
                  key={c.name}
                  onClick={() => setPassport(c.name)}
                  className={`text-[10px] px-2 py-1 rounded border ${
                    passport === c.name
                      ? "border-cyan text-cyan"
                      : "border-edge text-muted hover:border-cyan/50"
                  }`}
                >
                  {c.name}
                </button>
              ))}
            </div>
          )}
          <AuditFeed events={data?.evolution?.events || []} />
          <MonitorPanel monitors={data?.monitors?.monitors || []} />
        </div>
      </div>

      <footer className="mt-6 text-[10px] text-muted">
        Every number on this page comes from the live aion-core API. Nothing
        here is mocked; an empty panel means the system genuinely has nothing
        to show.
      </footer>
    </main>
  );
}
