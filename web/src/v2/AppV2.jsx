import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Power } from "lucide-react";
import { api, hasOwnerToken, loadAll } from "../api.js";
import { computeStages } from "../Topology.jsx";
import CommandCapsule from "./CommandCapsule.jsx";
import StageGrid from "./StageGrid.jsx";
import TelemetryPane from "./TelemetryPane.jsx";
import { Card, CardHead, Dot, MicroLabel, NavIsland, Pill, Reveal } from "./Shell2.jsx";

/**
 * v2 surface — the obsidian/glass redesign.
 *
 * Composed of the same live data as v1 and the SAME computeStages, so the
 * two surfaces cannot drift into disagreeing about what a stage's state
 * is. This is a re-skin plus a richer right pane, not a second source of
 * truth.
 */

const REFRESH_MS = 3000;

function StatusLine({ result }) {
  const status = result?.status || "UNKNOWN";
  const tone =
    status === "COMPLETED" ? "ok" : status === "BLOCKED" ? "warn" : "danger";

  return (
    <div className="border-l-2 border-white/10 pl-3">
      <div className="flex items-center gap-2">
        <Dot tone={tone} />
        <MicroLabel>Axon · {status}</MicroLabel>
      </div>

      {result?.blocked_on && (
        <p className="text-[11px] text-amber-300 mt-1.5 leading-relaxed">
          gap: {result.blocked_on.capability_description || result.blocked_on.description}
        </p>
      )}

      {/* WHY it failed, not just that it did.
          This previously rendered "Axon · FAILED" and nothing else whenever
          a mission came back FAILED with no steps and no gap -- which is
          exactly what a quota refusal looks like. A failure with no reason
          is the same defect as a silent mic error: the reader is told
          something went wrong and given nothing to act on. */}
      {(result?.reason || result?.error) && (
        <p className="text-[11px] text-red-300 mt-1.5 leading-relaxed break-all">
          {result.reason || result.error}
        </p>
      )}

      {(result?.step_results || []).map((step, i) => (
        <p key={i} className="text-[10.5px] text-zinc-400 mt-1 tabular-nums">
          step {i + 1} · {step.status || "?"} {step.tool ? `· ${step.tool}` : ""}
        </p>
      ))}

      {/* Last resort: a FAILED result that carried no reason, no gap and no
          steps would otherwise render as a bare status word. Say so, rather
          than leave a blank line that looks like the UI broke. */}
      {status !== "COMPLETED" &&
        !result?.reason &&
        !result?.error &&
        !result?.blocked_on &&
        !(result?.step_results || []).length && (
          <p className="text-[10.5px] text-zinc-500 mt-1.5 leading-relaxed">
            The server returned {status} without a reason. Raw response:{" "}
            <span className="font-mono break-all">
              {JSON.stringify(result).slice(0, 240)}
            </span>
          </p>
        )}
    </div>
  );
}

export default function AppV2() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [node, setNode] = useState(null);
  const [unlocked, setUnlocked] = useState(hasOwnerToken());
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);

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

  const stages = useMemo(() => computeStages(data), [data]);

  const verifiedPct = useMemo(() => {
    const values = Object.values(stages);
    if (!values.length) return null;
    const verified = values.filter((s) => s.state === "VERIFIED").length;
    return Math.round((verified / values.length) * 100);
  }, [stages]);

  const killed = !!data?.root?.kill_switch_active;
  const pending = data?.pending?.pending || [];

  const addLog = (entry) =>
    setLog((l) => [{ ...entry, at: Date.now() }, ...l].slice(0, 6));

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

  const decide = async (id, approved, capability) => {
    setBusy(true);
    try {
      await api.decide(id, approved);

      // Approving records the decision; it does not install. The install
      // is a separate call that re-reads that decision from Firestore, and
      // no UI ever made it -- so Approve cleared the queue and silently
      // changed nothing. See the same fix in App.jsx and v4/AppV4.jsx.
      if (approved && capability) {
        const installed = await api.install(capability);
        // BUG-010: ALREADY_INSTALLED is a real, safe, idempotent
        // outcome (see App.jsx), not an error -- do not show one for it.
        if (!["INSTALLED", "ALREADY_INSTALLED"].includes(installed?.status)) {
          // BUG-009: same reason/error mismatch as App.jsx/AppV4.jsx --
          // synapse.install()'s FAILED responses carry their message
          // under "error", not "reason".
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

  return (
    <div className="min-h-screen bg-obsidian text-zinc-100 font-sans">
      <NavIsland
        online={!!data?.online}
        killed={killed}
        verifiedPct={verifiedPct}
        unlocked={unlocked}
        quotaNote="Planning spends real Gemini quota"
      />

      <main className="px-4 pb-10 pt-5 max-w-[1600px] mx-auto">
        {error && (
          <div className="glass rounded-xl px-3.5 py-2.5 mb-4 flex items-center gap-2 border-red-400/25">
            <AlertTriangle size={13} className="text-red-300 shrink-0" />
            <p className="text-[11px] text-red-300">{error}</p>
          </div>
        )}

        <Reveal className="max-w-3xl mx-auto mb-6">
          <CommandCapsule
            unlocked={unlocked}
            onUnlock={() => setUnlocked(true)}
            onChanged={refresh}
            onLog={addLog}
          />

          {log.length > 0 && (
            <div className="mt-4 space-y-3">
              {log.map((entry) => (
                <div key={entry.at + entry.kind}>
                  {entry.kind === "you" && (
                    <div className="border-l-2 border-cobalt/50 pl-3">
                      <MicroLabel>You</MicroLabel>
                      <p className="text-[12px] mt-1 leading-relaxed">
                        {entry.text}
                      </p>
                    </div>
                  )}
                  {entry.kind === "error" && (
                    <div className="border-l-2 border-red-400/60 pl-3">
                      <MicroLabel className="!text-red-300">Failed</MicroLabel>
                      <p className="text-[11px] text-red-300 mt-1 leading-relaxed">
                        {entry.text}
                      </p>
                    </div>
                  )}
                  {entry.kind === "axon" && <StatusLine result={entry.result} />}
                </div>
              ))}
            </div>
          )}
        </Reveal>

        <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
          <Reveal delay={0.05}>
            <StageGrid stages={stages} selected={node} onSelect={setNode} />
          </Reveal>

          <Reveal delay={0.1}>
            <TelemetryPane data={data} stages={stages} />
          </Reveal>
        </div>

        <div className="grid gap-4 lg:grid-cols-2 mt-4">
          <Reveal delay={0.15}>
            <Card className="p-5">
              <CardHead
                label="Human approval"
                title={
                  pending.length
                    ? `${pending.length} waiting on you`
                    : "Nothing is waiting on you"
                }
              />
              {pending.length === 0 ? (
                <p className="text-[11px] text-zinc-500 leading-relaxed">
                  Nothing installs without a named human decision. An empty
                  queue means nothing is pending, not that approval was skipped.
                </p>
              ) : (
                <div className="space-y-2.5">
                  {pending.map((p) => (
                    <div
                      key={p.request_id || p.id}
                      className="border border-white/[0.06] rounded-xl px-3 py-2.5"
                    >
                      <p className="text-[11.5px] font-medium tracking-tight">
                        {p.capability || p.action || p.request_id}
                      </p>
                      <div className="flex gap-2 mt-2.5">
                        <button
                          onClick={() => decide(p.request_id || p.id, true, p.capability)}
                          disabled={busy}
                          className="px-3 py-1.5 rounded-lg border border-emerald-400/40 text-emerald-300 text-[10px] tracking-wider uppercase font-semibold hover:bg-emerald-400/10 disabled:opacity-40 transition-colors"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => decide(p.request_id || p.id, false, p.capability)}
                          disabled={busy}
                          className="px-3 py-1.5 rounded-lg border border-red-400/40 text-red-300 text-[10px] tracking-wider uppercase font-semibold hover:bg-red-400/10 disabled:opacity-40 transition-colors"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </Reveal>

          <Reveal delay={0.2}>
            <Card className="p-5">
              <CardHead
                label="Kill switch"
                title={killed ? "Everything is halted" : "Armed and released"}
                right={<Pill tone={killed ? "danger" : "ok"}>{killed ? "Halted" : "Live"}</Pill>}
              />
              <button
                onClick={() => toggleKill(!killed)}
                disabled={busy}
                className={`w-full flex items-center justify-center gap-2 rounded-xl border py-3 text-[11px] tracking-wider uppercase font-semibold transition-colors disabled:opacity-40 ${
                  killed
                    ? "border-emerald-400/40 text-emerald-300 hover:bg-emerald-400/10"
                    : "border-red-400/40 text-red-300 hover:bg-red-400/10"
                }`}
              >
                <Power size={14} />
                {killed ? "Release the kill switch" : "Stop everything"}
              </button>
              <p className="text-[9.5px] text-zinc-600 mt-3 leading-relaxed">
                Halts execution at the gate. Every route to a tool passes
                through it, so there is nothing that can keep running behind it.
              </p>
            </Card>
          </Reveal>
        </div>

        <footer className="mt-8 text-[9px] text-zinc-600 leading-relaxed max-w-3xl">
          Every number on this surface comes from the live aion-core API.
          Nothing is mocked and no sequence is simulated; an empty panel means
          the system genuinely has nothing to show.
        </footer>
      </main>
    </div>
  );
}
