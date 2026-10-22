import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        serif: ["Georgia", "Cambria", "Times New Roman", "serif"],
      },
      colors: {
        ink: "#16233b",
        civic: {
          50: "#eef4fb",
          100: "#d9e6f5",
          200: "#bccfee",
          300: "#94b6e2",
          400: "#5f8fc9",
          500: "#3570ae",
          600: "#1f4f8b",
          700: "#1a4274",
          800: "#16355c",
          900: "#122a48",
        },
      },
    },
  },
  plugins: [],
};

export default config;
