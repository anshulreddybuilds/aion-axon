import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Command from "./Command.jsx";
import Topology, { computeStages } from "./Topology.jsx";
import Topology3D from "./Topology3D.jsx";
import Inventory from "./Inventory.jsx";
import JudgeMode from "./JudgeMode.jsx";
import MissionTheater from "./MissionTheater.jsx";
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
  judge: {
    crumb: "JUDGE MODE",
    title: "Don't trust the claim. Call the endpoint.",
    blurb:
      "A live proof center over the same governed API the rest of this dashboard uses — red team, ledger verification, quarantine, contracts, lineage, and why a human had to decide. Nothing here is seeded.",
  },
  theater: {
    crumb: "MISSION THEATER",
    title: "Watch the spine run, live.",
    blurb:
      "Type a real capability need and run the actual governed acquisition loop against production — research, generation, screening, sandbox, evaluation, and a human approval gate that really installs or really rejects.",
  },
};

export default function App() {
  const [data, setData] = useState(null);
  const [passport, setPassport] = useState(null);
  // The fetched passport lives in its OWN state, never inside `data`.
  //
  // It used to be stashed as `data.selected`, but refresh() does
  // setData(await loadAll()) every 3 seconds and loadAll() has no
  // `selected` key -- so the poll wiped the passport within one tick of
  // it arriving. The Evidence view showed a capability visibly selected
  // (cyan border on its chip) while both panels read "No acquired
  // capability selected", because the chip's state and the passport's
  // state were being stored in two places with different lifetimes.
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [view, setView] = useState("command");
  const [node, setNode] = useState(null);
  // 2D is the default and the fallback everywhere. 3D is opt-in, in the
  // Pipeline view only, per the owner's own time-boxed rollout plan: it
  // ships behind a toggle, never replacing the 2D rendering outright.
  const [pipelineIs3D, setPipelineIs3D] = useState(false);

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
    let cancelled = false;
    api
      .passport(passport)
      .then((body) => {
        if (!cancelled) setSelected(body);
      })
      .catch(() => {});
    // Guards against a slow fetch for a previously-clicked capability
    // landing after a newer one and overwriting it.
    return () => {
      cancelled = true;
    };
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

  const decide = async (id, approved, capability) => {
    setBusy(true);
    try {
      const decision = await api.decide(id, approved);

      // POST /approvals/{id}/decide answers HTTP 200 even when the
      // decision didn't apply -- ALREADY_DECIDED, NOT_FOUND, BLOCKED
      // (kill switch), and CONTENTION are all normal 200 bodies, not
      // thrown errors, so the await above never throws for them. This
      // call discarded that response entirely and always proceeded as
      // if it had succeeded -- the same bug already fixed in
      // MissionTheater.jsx (see that file's decide()) but never applied
      // here, the actual production approval queue.
      const expected = approved ? "APPROVED" : "REJECTED";
      if (decision.status !== expected) {
        setError(
          `Decision not recorded: ${decision.status}${
            decision.reason ? ` — ${decision.reason}` : ""
          }${decision.error ? ` — ${decision.error}` : ""}`
        );
        return;
      }

      // Approving does not install. POST /approvals/{id}/decide records
      // the decision only; the install is a separate call that re-reads
      // that decision from Firestore. This UI never made it, so clicking
      // Approve cleared the queue and then silently did nothing -- the
      // registry never moved and a mission blocked on the capability never
      // resumed. Found live: an approval recorded APPROVED while the
      // registry stayed at 11 and the mission stayed BLOCKED.
      //
      // The server's two-step design is deliberate and correct. The defect
      // was that no caller ever took the second step.
      if (approved && capability) {
        const installed = await api.install(capability);
        // BUG-010: ALREADY_INSTALLED is a real, safe, idempotent
        // outcome -- exactly what the concurrency-safe install claim
        // (BUG-003) exists to guarantee under a duplicate call (a
        // network retry, or a second click before this button's own
        // disabled state takes effect). Treating it the same as a real
        // FAILED/APPROVAL_REQUIRED error would show a scary red banner
        // for a capability that is, in fact, genuinely installed.
        if (!["INSTALLED", "ALREADY_INSTALLED"].includes(installed?.status)) {
          // BUG-009: the same reason/error mismatch as BUG-008, found
          // here in the actual production UI -- synapse.install()'s
          // FAILED-status responses (unknown capability, no approval on
          // record, real Firestore contention) all carry their message
          // under "error", never "reason". Reading only "reason" always
          // fell through to the bare status word.
          setError(
            `Approved, but install did not complete: ${
              installed?.reason || installed?.error || installed?.status || "unknown"
            }`
          );
        }
      }

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
              <Command onChanged={refresh} />

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
              <div className="flex justify-end">
                <button
                  onClick={() => setPipelineIs3D((v) => !v)}
                  className="text-[9px] tracking-[0.14em] px-3 py-1.5 rounded border border-edge text-muted hover:border-cyan/40 hover:text-cyan"
                >
                  {pipelineIs3D ? "◱ SWITCH TO 2D" : "◳ TRY 3D (PREVIEW)"}
                </button>
              </div>
              {pipelineIs3D ? (
                <Topology3D stages={stages} selected={node} onSelect={setNode} />
              ) : (
                <Topology stages={stages} selected={node} onSelect={setNode} />
              )}
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
                <EvidencePanel capability={selected} />
                <SkillPassport capability={selected} />
              </div>
            </div>
          )}

          {view === "theater" && <MissionTheater />}

          {view === "judge" && (
            <JudgeMode
              pending={pending}
              acquiredNames={acquired.map((c) => c.name)}
            />
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
