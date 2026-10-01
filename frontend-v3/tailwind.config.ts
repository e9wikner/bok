import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },

        // Skalets tokens (modul `skal`). Ligger BREDVID shadcn-paletten
        // ovan — ingen av dess variabler omdefinieras. SPEC-skal.md §7.
        bok: {
          app: "var(--bok-app)",
          yta: "var(--bok-yta)",
          "yta-svag": "var(--bok-yta-svag)",
          "yta-falt": "var(--bok-yta-falt)",
          black: "var(--bok-black)",
          "black-hover": "var(--bok-black-hover)",
          text: "var(--bok-text)",
          "text-2": "var(--bok-text-2)",
          "text-dampad": "var(--bok-text-dampad)",
          "text-svag": "var(--bok-text-svag)",
          meta: "var(--bok-meta)",
          linje: "var(--bok-linje)",
          "linje-svag": "var(--bok-linje-svag)",
          "linje-svagast": "var(--bok-linje-svagast)",
          kant: "var(--bok-kant)",
          "kant-streckad": "var(--bok-kant-streckad)",
          lank: "var(--bok-lank)",
          "lank-hover": "var(--bok-lank-hover)",
          // Gult bär betydelse: väntar på människan.
          "vantar-yta": "var(--bok-vantar-yta)",
          "vantar-kant": "var(--bok-vantar-kant)",
          "vantar-text": "var(--bok-vantar-text)",
          "vantar-meta": "var(--bok-vantar-meta)",
          "vantar-prick": "var(--bok-vantar-prick)",
          "fel-yta": "var(--bok-fel-yta)",
          "fel-kant": "var(--bok-fel-kant)",
          "fel-rubrik": "var(--bok-fel-rubrik)",
          "fel-text": "var(--bok-fel-text)",
          "fel-meta": "var(--bok-fel-meta)",
          // Grönt bär betydelse: postat och låst.
          "klart-yta": "var(--bok-klart-yta)",
          "klart-kant": "var(--bok-klart-kant)",
          "klart-text": "var(--bok-klart-text)",
          "klart-meta": "var(--bok-klart-meta)",
          "klart-prick": "var(--bok-klart-prick)",
          bubbla: "var(--bok-bubbla)",
        },
      },
      boxShadow: {
        "bok-kort": "var(--bok-skugga-kort)",
        "bok-meny": "var(--bok-skugga-meny)",
        "bok-chattlist": "var(--bok-skugga-chattlist)",
      },
      spacing: {
        "bok-header": "var(--bok-header-desktop)",
        "bok-header-mobil": "var(--bok-header-mobil)",
        "bok-fot": "var(--bok-fot-desktop)",
        "bok-vykolumn": "var(--bok-vykolumn)",
        "bok-chattrad": "var(--bok-chattrad-mobil)",
        "bok-traffyta": "var(--bok-traffyta)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.3s ease-out",
      },
    },
  },
  plugins: [],
};
export default config;
