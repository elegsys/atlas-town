import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        town: {
          sky: "#87ceeb",
          grass: "#90ee90",
          road: "#696969",
        },
      },
      animation: {
        "pulse-soft": "pulse-soft 1.5s ease-in-out infinite",
        float: "float 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
