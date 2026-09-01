import type { Config } from "tailwindcss";
import defaultTheme from "tailwindcss/defaultTheme";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#1d550e", hover: "#0f2519" },
        surface: "#fdfdfb",
        brand: {
          dark: "#0f2519",
          DEFAULT: "#1d550e",
          light: "#558927",
          gold: "#f2da6e",
          bg: "#fdfdfb",
        },
      },
      fontFamily: {
        sans: ["Inter", ...defaultTheme.fontFamily.sans],
        heading: ["Sansation", ...defaultTheme.fontFamily.sans],
      },
    },
  },
  plugins: [],
};

export default config;
