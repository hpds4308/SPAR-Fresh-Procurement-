/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        crate: {
          950: "#0F2A1C",
          900: "#153826",
          800: "#1D4A33",
          700: "#2F6D4E",
          600: "#3F8A64",
        },
        tomato: {
          600: "#C93A21",
          500: "#E4472B",
          400: "#EE6A4C",
        },
        mango: {
          500: "#F3A712",
          400: "#F7BE45",
        },
        paper: {
          100: "#FAF4E4",
          200: "#F3EAD1",
        },
        sage: {
          50: "#F4F9F3",
          100: "#E7F2E5",
          200: "#D7E9D6",
          300: "#C3DCC4",
        },
      },
      fontFamily: {
        display: ["'Plus Jakarta Sans'", "sans-serif"],
        body: ["Inter", "sans-serif"],
      },
      // Centralized shadow tokens — previously this exact card shadow was
      // hand-copied as an arbitrary value into ~20 components. New/updated
      // components should use shadow-card / shadow-dropdown / shadow-modal
      // instead of repeating the raw rgba value.
      boxShadow: {
        card: "0 10px 30px -12px rgba(21,56,38,0.15)",
        dropdown: "0 12px 28px -8px rgba(21,56,38,0.22)",
        modal: "0 24px 64px -12px rgba(15,42,28,0.35)",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0) rotate(0deg)" },
          "50%": { transform: "translateY(-10px) rotate(-1deg)" },
        },
        sway: {
          "0%, 100%": { transform: "rotate(-2deg)" },
          "50%": { transform: "rotate(2deg)" },
        },
        bob: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        shake: {
          "0%, 100%": { transform: "translateX(0)" },
          "20%": { transform: "translateX(-6px)" },
          "40%": { transform: "translateX(5px)" },
          "60%": { transform: "translateX(-4px)" },
          "80%": { transform: "translateX(3px)" },
        },
        popIn: {
          "0%": { opacity: "0", transform: "scale(0.9)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        drift: {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(-16px, 14px) scale(1.04)" },
        },
        produceFloat: {
          "0%, 100%": { transform: "translate(0, 0) rotate(var(--produce-rot-a, -1.5deg))" },
          "50%": { transform: "translate(0, -14px) rotate(var(--produce-rot-b, 1.5deg))" },
        },
        produceSway: {
          "0%, 100%": { transform: "translate(0, 0) rotate(var(--produce-rot-a, -2deg))" },
          "50%": { transform: "translate(10px, 6px) rotate(var(--produce-rot-b, 2deg))" },
        },
        produceDrift: {
          "0%, 100%": { transform: "translate(0, 0) rotate(var(--produce-rot-a, -3deg)) scale(1)", opacity: "var(--produce-op-a, 0.85)" },
          "50%": { transform: "translate(12px, -16px) rotate(var(--produce-rot-b, 4deg)) scale(1.03)", opacity: "var(--produce-op-b, 1)" },
        },
        produceGlow: {
          "0%, 100%": { opacity: "var(--produce-op-a, 0.6)", transform: "scale(1)" },
          "50%": { opacity: "var(--produce-op-b, 0.85)", transform: "scale(1.02)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-up": "fadeUp 0.7s cubic-bezier(0.16,1,0.3,1) both",
        float: "float 6s ease-in-out infinite",
        sway: "sway 4.5s ease-in-out infinite",
        bob: "bob 3.6s ease-in-out infinite",
        shake: "shake 0.45s ease-in-out",
        "pop-in": "popIn 0.35s cubic-bezier(0.16,1,0.3,1) both",
        drift: "drift 10s ease-in-out infinite",
        "produce-float": "produceFloat 9s ease-in-out infinite",
        "produce-sway": "produceSway 11s ease-in-out infinite",
        "produce-drift": "produceDrift 13s ease-in-out infinite",
        "produce-glow": "produceGlow 8s ease-in-out infinite",
        shimmer: "shimmer 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
