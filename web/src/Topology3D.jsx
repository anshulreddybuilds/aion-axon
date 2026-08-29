import { useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { STAGES, TONE, useFiringPulses } from "./Topology.jsx";

/**
 * EXECUTION TOPOLOGY, in 3D — the same twelve real stages as Topology.jsx,
 * laid out on a ring instead of a grid.
 *
 * Built with plain CSS 3D transforms (perspective + rotateY + translateZ),
 * NOT WebGL. That is a deliberate, recorded trade-off: `CLAUDE.md` banned
 * WebGL for exactly the failure mode this project cannot afford --
 * an 8GB machine dropping frames mid-screen-recording, which reads on
 * camera as "this system is unreliable" even when it is the video capture
 * that is struggling, not the product. CSS transforms are compositor-only:
 * the browser moves already-rasterised layers, so there is no per-frame
 * JavaScript animation loop and no shader pipeline to stall. This gets
 * most of the 3D effect at a fraction of the frame-rate risk, which is
 * the owner's own stated preference for how to build this.
 *
 * The rule that survives the rebuild unchanged: EVERY animation fires
 * because a real event happened, never on a timer.
 *   - Rotating the ring: only ever the direct result of a drag gesture or
 *     a click, both real user actions. There is no auto-spin.
 *   - A node popping toward the camera: only when useFiringPulses (the
 *     exact same detector Topology.jsx uses) reports that stage's own
 *     counter just moved for real.
 *   - Depth (which nodes look near vs. far) is a plain function of the
 *     current rotation angle, recomputed on render -- not an animation,
 *     a static consequence of where the ring currently sits.
 */

const RADIUS = 640; // was 300, then 460 -- still not enough clearance
// once the vertical tilt below was removed and up to 5 cards could sit
// at meaningful opacity at once (see VISIBLE_THRESHOLD).
const STEP = 360 / STAGES.length;
const DRAG_SENSITIVITY = 0.35;
const CLICK_DRAG_THRESHOLD = 6; // px — below this, a pointer-up is a click

function normalize(angle) {
  const a = angle % 360;
  return a < 0 ? a + 360 : a;
}

export default function Topology3D({ stages, selected, onSelect }) {
  const firing = useFiringPulses(stages);

  const [rotation, setRotation] = useState(0);
  const [transitioning, setTransitioning] = useState(false);
  const drag = useRef(null); // { startX, startRotation, moved }

  // When a stage genuinely fires, bring it to face the camera. The pop
  // (below, per-node) is the real event's animation; this is the "camera"
  // reacting to the same real event rather than a separate decoration.
  const lastAutoFaced = useRef(null);
  const firedKeys = Object.keys(firing);
  if (firedKeys.length && firedKeys[0] !== lastAutoFaced.current && !drag.current) {
    lastAutoFaced.current = firedKeys[0];
    const idx = STAGES.findIndex((s) => s.key === firedKeys[0]);
    if (idx >= 0) {
      const target = normalize(-idx * STEP);
      // Deferred so React finishes this render before the transform jumps,
      // otherwise the transition-class toggle and the new angle can land
      // in the same paint and the rotation appears to snap instead of ease.
      queueMicrotask(() => {
        setTransitioning(true);
        setRotation(target);
        setTimeout(() => setTransitioning(false), 600);
      });
    }
  }

  const onPointerDown = (e) => {
    drag.current = { startX: e.clientX, startRotation: rotation, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.startX;
    if (Math.abs(dx) > CLICK_DRAG_THRESHOLD) drag.current.moved = true;
    setRotation(drag.current.startRotation + dx * DRAG_SENSITIVITY);
  };

  const endDrag = () => {
    drag.current = null;
  };

  const selectNode = (key, idx) => {
    if (drag.current?.moved) return; // was a drag, not a click
    onSelect(selected === key ? null : key);
    setTransitioning(true);
    setRotation(normalize(-idx * STEP));
    setTimeout(() => setTransitioning(false), 600);
  };

  // Depth styling is pure math over the current angle -- not animated,
  // just recomputed whenever `rotation` changes (by drag or by click).
  const depths = useMemo(
    () =>
      STAGES.map((_, idx) => {
        const facing = normalize(idx * STEP + rotation);
        const rad = (facing * Math.PI) / 180;
        const forwardness = (1 + Math.cos(rad)) / 2; // 1 = facing camera, 0 = facing away
        // First attempt (squared falloff, no visibility cutoff) still let
        // up to 5 adjacent cards sit at high-enough opacity to visibly
        // collide -- fading a card was not the same as removing it from
        // the collision. VISIBLE_THRESHOLD instead makes a hard decision:
        // a card more than ~60 degrees off-camera (roughly 2 stages away
        // at 30 degrees/stage) is not a faint card, it is gone (near-zero
        // opacity, not clickable), so only the 3 cards actually facing
        // the viewer ever compete for screen space at once.
        const VISIBLE_THRESHOLD = 0.75; // forwardness = (1+cos)/2
        const visible = forwardness > VISIBLE_THRESHOLD;
        const eased = Math.pow(forwardness, 4);
        return {
          opacity: visible ? 0.15 + 0.85 * eased : 0.04,
          scale: visible ? 0.7 + 0.3 * eased : 0.5,
          z: Math.round(forwardness * 100),
          interactive: visible,
        };
      }),
    [rotation]
  );

  return (
    <section className="bg-panel border border-edge rounded-lg p-5">
      <div className="flex items-start justify-between mb-1">
        <div>
          <p className="text-[9px] tracking-[0.22em] text-muted">
            EXECUTION TOPOLOGY — 3D
          </p>
          <h2 className="text-[15px] mt-1">Governed capability spine</h2>
        </div>
        <p className="text-[9px] tracking-[0.18em] text-muted">
          DRAG TO ROTATE · CLICK A NODE
        </p>
      </div>

      <div
        className="relative mt-6 mb-2 select-none touch-none"
        style={{ height: 340, perspective: 2200 }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <div
          className="absolute inset-0"
          style={{
            transformStyle: "preserve-3d",
            // No rotateX tilt: it shifted near/far cards up and down
            // relative to each other (a Z difference becoming a screen-Y
            // difference), which is what let two cards land close enough
            // in Y as well as X to visually collide. A flat ring keeps
            // every card's vertical position identical -- only X (from
            // rotateY) and scale (from perspective) differ, which is
            // exactly the "governed capability spine" that's supposed to
            // read as one clean row, not a cluttered cluster.
            transform: `translateX(50%) rotateY(${rotation}deg)`,
            transition: transitioning ? "transform 0.6s ease" : "none",
            cursor: drag.current ? "grabbing" : "grab",
          }}
        >
          {STAGES.map((stage, idx) => {
            const s = stages[stage.key];
            const tone = TONE[s.state];
            const isFiring = !!firing[stage.key];
            const isSelected = selected === stage.key;
            const depth = depths[idx];

            return (
              <div
                key={stage.key}
                className="absolute top-1/2 left-0 w-[150px] -ml-[75px] -mt-[58px]"
                style={{
                  transformStyle: "preserve-3d",
                  transform: `rotateY(${idx * STEP}deg) translateZ(${RADIUS}px)`,
                  zIndex: depth.z,
                }}
              >
                <motion.button
                  onClick={() => selectNode(stage.key, idx)}
                  animate={
                    isFiring
                      ? { scale: [depth.scale, depth.scale * 1.18, depth.scale] }
                      : { scale: depth.scale }
                  }
                  transition={{ duration: 0.6 }}
                  // Individual transform props (rotateY, scale), NOT a raw
                  // `transform` string -- framer-motion composes these into
                  // one transform itself. Setting style.transform directly
                  // on a motion component fights its own animated scale and
                  // silently drops the counter-rotation the instant a pulse
                  // fires, which would make the card's text spin sideways.
                  style={{
                    opacity: depth.opacity,
                    rotateY: -idx * STEP - rotation,
                    pointerEvents: depth.interactive ? "auto" : "none",
                  }}
                  className={`w-full text-left rounded-md border px-3 py-2.5 backdrop-blur-sm bg-void/70 transition-colors ${
                    isSelected
                      ? "border-cyan bg-cyan/[0.08]"
                      : `${tone.ring} hover:border-cyan/40`
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <span className="text-[8px] tracking-[0.18em] text-muted">
                      {stage.n}
                    </span>
                    <span
                      className="h-1.5 w-1.5 rounded-full mt-0.5"
                      style={{
                        background: tone.dot,
                        boxShadow: isFiring ? `0 0 10px ${tone.dot}` : "none",
                      }}
                    />
                  </div>
                  <p className="text-[12px] mt-1.5 leading-tight">{stage.label}</p>
                  <p className={`text-[9px] mt-1 ${tone.text}`}>{s.stat}</p>
                </motion.button>
              </div>
            );
          })}
        </div>
      </div>

      {selected && (
        <div className="mt-4 border-t border-edge pt-3">
          <p className="text-[9px] tracking-[0.18em] text-muted">
            {STAGES.find((s) => s.key === selected)?.n} /{" "}
            {stages[selected].state} / TELEMETRY
          </p>
          <h3 className="text-[14px] mt-1">
            {STAGES.find((s) => s.key === selected)?.label}
          </h3>
          <p className="text-[11px] text-muted mt-1">{stages[selected].detail}</p>
          <p className={`text-[11px] mt-2 ${TONE[stages[selected].state].text}`}>
            {stages[selected].stat}
          </p>
        </div>
      )}

      <p className="text-[8px] text-muted mt-4">
        Same live data as the 2D view, laid out in 3D. Every figure comes from
        the real API; a node only pops toward you because its own counter
        genuinely just moved.
      </p>
    </section>
  );
}
