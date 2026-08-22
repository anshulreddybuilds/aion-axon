/** Palette locked in §5.1 — set BEFORE any component, not tuned after. */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        void: "#06090f",
        panel: "#0c1119",
        edge: "#1b2432",
        cyan: "#37e0d8",
        ok: "#4ade80",
        danger: "#f87171",
        warn: "#fbbf24",
        muted: "#7d8899",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
