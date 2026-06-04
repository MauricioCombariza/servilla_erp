import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#1d4ed8", hover: "#1e40af" },
        surface: "#f8fafc",
      },
    },
  },
  plugins: [],
};

export default config;
