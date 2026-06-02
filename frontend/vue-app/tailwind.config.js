/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: '#F8FAFC',
        sidebar: '#1E293B',
        primary: '#334155',
        'accent-green': '#059669',
        'accent-orange': '#EA580C',
        teal: '#0F766E',
        amber: '#D97706',
        'warm-gray': '#F1F5F9',
        grid: '#E2E8F0',
        surface: '#FFFFFF',
      },
      fontFamily: {
        space: ['"Space Grotesk"', 'sans-serif'],
        sans: ['Inter', '"Noto Sans SC"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        none: '0px',
      },
      borderWidth: {
        hairline: '1px',
      },
    },
  },
  plugins: [],
}
