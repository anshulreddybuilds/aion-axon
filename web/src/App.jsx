import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Topology, { computeStages } from "./Topology.jsx";
import Inventory from "./Inventory.jsx";
import { CompletionRing, Hero, Sidebar, TopStrip } from "./Shell.jsx";
import { api, loadAll } from "./api.js";
import {
  ApprovalCard,
  AuditFeed,
  AutonomyLedger,
  CapabilityCounter,
  EvidencePanel,
  KillSwitch,
  MonitorPanel,
  SkillPassport,
  TrustBoundary,
} from "./panels.jsx";

const REFRESH_MS = 3000;

const HEROES = {
  command: {
    crumb: "LIVE OVERVIEW",
    title: "Command the spine.",
    blurb:
      "A governed execution surface for seeing what the system knows, what it is allowed to do, and where a human must decide.",
  },
  pipeline: {
    crumb: "PIPELINE",
    title: "Inspect every handoff.",
    blurb:
      "The capability spine is intentionally visible: no package moves from intent to evolution without evidence.",
  },
  ledger: {
    crumb: "AUTONOMY LEDGER",
    title: "Trust is earned, and losable.",
    blurb:
      "Autonomy rises on verified outcomes and falls when reality disagrees. Below the supervision threshold, a human is asked again.",
  },
  evidence: {
    crumb: "EVIDENCE",
    title: "Why this skill exists.",
    blurb:
      "Every acquired capability keeps its chain of custody — the need, the research, the screen, the sandbox, the score, and who approved it.",
  },
};

export default function App() {
  const [data, setData] = useState(null);
  const [passport, setPassport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [view, setView] = useState("command");
  const [node, setNode] = useState(null);

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

  const acquired = useMemo(
    () => (data?.autonomy?.capabilities || []).filter((c) => c.passport),
    [data]
  );

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

  // One computation, shared by the ring, the grid and the table, so the
  // three can never quietly disagree about the same stage.
  const stages = useMemo(() => computeStages(data), [data]);
  const stageStates = useMemo(
    () =>
      Object.fromEntries(Object.entries(stages).map(([k, v]) => [k, v.state])),
    [stages]
  );

  const decide = async (id, approved) => {
    setBusy(true);
    try {
      await api.decide(id, approved);
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
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const hero = HEROES[view];

  return (
    <div className="min-h-screen flex">
      <Sidebar view={view} onView={setView} />

      <main className="flex-1 min-w-0">
        <TopStrip online={!!data?.online} killed={killed} />

        <Hero
          crumb={hero.crumb}
          title={hero.title}
          blurb={hero.blurb}
          pendingCount={pending.length}
        />

        <div className="px-5 pb-8">
          {error && (
            <p className="mb-4 text-[11px] text-danger border border-danger/40 rounded px-3 py-2">
              {error}
            </p>
          )}

          {view === "command" && (
            <div className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-[300px_1fr]">
                <CompletionRing stageStates={stageStates} />
                <Topology stages={stages} selected={node} onSelect={setNode} />
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-4">
                  <CapabilityCounter
                    implemented={data?.capabilities?.implemented}
                    total={data?.capabilities?.total}
                  />
                  <TrustBoundary sandbox={data?.sandbox} />
                  <ApprovalCard
                    pending={pending}
                    onDecide={decide}
                    busy={busy}
                  />
                  <KillSwitch active={killed} onToggle={toggleKill} busy={busy} />
                </div>
                <div className="space-y-4">
                  <AuditFeed events={data?.evolution?.events || []} />
                  <MonitorPanel monitors={data?.monitors?.monitors || []} />
                </div>
              </div>
            </div>
          )}

          {view === "pipeline" && (
            <div className="space-y-4">
              <Topology stages={stages} selected={node} onSelect={setNode} />
              <Inventory stages={stages} onSelect={setNode} />
            </div>
          )}

          {view === "ledger" && (
            <div className="grid gap-4 lg:grid-cols-2">
              <AutonomyLedger
                tracked={data?.autonomy?.capabilities || []}
                threshold={data?.autonomy?.supervision_threshold ?? 40}
              />
              <AuditFeed events={data?.evolution?.events || []} />
            </div>
          )}

          {view === "evidence" && (
            <div className="space-y-4">
              {acquired.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {acquired.map((c) => (
                    <button
                      key={c.name}
                      onClick={() => setPassport(c.name)}
                      className={`text-[10px] px-2.5 py-1.5 rounded border ${
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
              <div className="grid gap-4 lg:grid-cols-2">
                <EvidencePanel capability={data?.selected} />
                <SkillPassport capability={data?.selected} />
              </div>
            </div>
          )}

          <footer className="mt-6 text-[9px] text-muted">
            Every number on this surface comes from the live aion-core API.
            Nothing here is mocked; an empty panel means the system genuinely
            has nothing to show.
          </footer>
        </div>
      </main>
    </div>
  );
}
