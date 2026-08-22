import { motion } from "framer-motion";

/**
 * The holographic core — three orbiting rings and a glowing centre.
 *
 * Pure CSS/SVG transforms, no WebGL, for the same reason the 3D topology
 * avoids it: an 8GB machine mid-screen-recording is where a shader
 * pipeline stalls, and a demo video that stutters reads as an unreliable
 * system.
 *
 * `spinning` is the one piece of continuous motion on this surface and it
 * is scoped deliberately: the rings turn while the system is IDLE and
 * WAITING for a command, which is a true statement about the system's
 * state ("standing by"), and they stop once execution begins so that the
 * only motion during the run belongs to real stage transitions.
 */
export default function Hologram({ docked, spinning = true }) {
  const size = docked ? 34 : 220;

  return (
    <motion.div
      animate={{
        width: size,
        height: size,
        opacity: docked ? 0.95 : 1,
      }}
      transition={{ duration: 0.75, ease: [0.16, 1, 0.3, 1] }}
      className="relative grid place-items-center shrink-0"
      aria-hidden="true"
    >
      {[
        { s: 1, dur: 8, colors: ["#00f0ff", "#0066ff"], border: "border-t-[1.5px] border-b-[1.5px]" },
        { s: 0.8, dur: 6, colors: ["#a855f7", "#00f0ff"], border: "border-l-[1.5px] border-r-[1.5px]" },
        { s: 0.6, dur: 4, colors: ["#38bdf8", "#0066ff"], border: "border-t-[1.5px] border-l-[1.5px]" },
      ].map((ring, i) => (
        <motion.div
          key={i}
          animate={spinning ? { rotate: i === 1 ? -360 : 360 } : { rotate: 0 }}
          transition={
            spinning
              ? { duration: ring.dur, ease: "linear", repeat: Infinity }
              : { duration: 0.6 }
          }
          className={`absolute rounded-full ${ring.border}`}
          style={{
            width: size * ring.s,
            height: size * ring.s,
            borderTopColor: ring.colors[0],
            borderBottomColor: ring.colors[1],
            borderLeftColor: ring.colors[0],
            borderRightColor: ring.colors[1],
            boxShadow: docked ? "none" : `0 0 25px ${ring.colors[0]}44`,
          }}
        />
      ))}

      <div
        className="rounded-full grid place-items-center"
        style={{
          width: size * 0.31,
          height: size * 0.31,
          background:
            "radial-gradient(circle, #ffffff 0%, #00f0ff 40%, #0066ff 80%)",
          boxShadow: docked
            ? "0 0 12px #00f0ff"
            : "0 0 35px #00f0ff, 0 0 60px rgba(0,102,255,0.8)",
        }}
      />
    </motion.div>
  );
}
