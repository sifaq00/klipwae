/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#07070d",
        panel: "#0e0e17",
        raise: "#151522",
        edge: "#23233a",
        accent: "#14b8a6",
        neon: "#22d3ee",
        gold: "#fbbf24",
      },
      fontFamily: {
        display: ["Space Grotesk", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
        barStripes: {
          "0%": { backgroundPosition: "0 0" },
          "100%": { backgroundPosition: "24px 0" },
        },
        spinSlow: {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
      },
      animation: {
        fadeUp: "fadeUp 0.4s ease-out both",
        pulseGlow: "pulseGlow 2s ease-in-out infinite",
        barStripes: "barStripes 0.8s linear infinite",
        spinSlow: "spinSlow 6s linear infinite",
      },
    },
  },
  plugins: [],
};
