/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper:        '#FAF9F7',
        sidebar:      '#2C241E',
        'sidebar-hover': '#3D342D',
        primary:      '#2D2A26',
        secondary:    '#6B6560',
        tertiary:     '#9C9792',
        surface:      '#FFFFFF',
        'warm-gray':  '#F3F0EC',
        grid:         '#E8E4DD',
        'accent-orange': '#C75B2A',
        'accent-orange-hover': '#A84A1F',
        'accent-soft':    '#FDF0E8',
        'accent-green':   '#3D7A6E',
        'accent-gold':    '#B88A44',
        'danger':         '#C44D4D',
        'danger-soft':    '#FDF0F0',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        body:    ['"Plus Jakarta Sans"', '"Noto Sans SC"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', '"SF Mono"', 'monospace'],
      },
      borderRadius: {
        sm:   '3px',
        DEFAULT: '5px',
        md:   '8px',
        lg:   '14px',
        xl:   '20px',
        full: '9999px',
      },
      boxShadow: {
        'sm':    '0 1px 2px rgba(26,29,35,0.03)',
        'card':  '0 1px 3px rgba(26,29,35,0.04), 0 1px 2px rgba(26,29,35,0.02)',
        'raised':'0 4px 16px rgba(26,29,35,0.05), 0 1px 4px rgba(26,29,35,0.03)',
        'modal': '0 16px 48px rgba(26,29,35,0.10), 0 4px 12px rgba(26,29,35,0.05)',
        'glow':  '0 0 0 3px rgba(199,91,42,0.12)',
      },
      transitionTimingFunction: {
        'spring':  'cubic-bezier(0.32, 0.72, 0, 1)',
        'out-expo':'cubic-bezier(0.16, 1, 0.3, 1)',
        'in-out':  'cubic-bezier(0.65, 0, 0.35, 1)',
      },
    },
  },
  plugins: [],
}
