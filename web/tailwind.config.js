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

        // v2 obsidian surface (owner design direction, 23 Aug). Added
        // ALONGSIDE the palette above rather than replacing it: the v1
        // surface is still the live production site and the filming
        // fallback, so redefining its colors underneath it would silently
        // restyle the thing that currently works.
        obsidian: "#050507",
        carbon: "#0E0F17",
        cobalt: "#0088ff",
        electric: "#38bdf8",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
        sans: [
          "Inter",
          "Geist",
          "SF Pro Display",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
