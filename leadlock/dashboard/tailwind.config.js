/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'data': ['0.8125rem', { lineHeight: '1.25rem', letterSpacing: '-0.01em', fontWeight: '500' }],
      },
      borderRadius: {
        'card': '12px',
      },
      boxShadow: {
        'card': '0 0 0 1px rgba(148, 163, 184, 0.04), 0 4px 24px rgba(0, 0, 0, 0.2)',
        'card-hover': '0 0 0 1px rgba(148, 163, 184, 0.08), 0 8px 32px rgba(0, 0, 0, 0.3)',
        'glow': '0 0 24px rgba(99, 102, 241, 0.12)',
        'glow-lg': '0 0 48px rgba(99, 102, 241, 0.15)',
      },
      animation: {
        'fade-up': 'fade-up 0.4s ease-out',
      },
    },
  },
  plugins: [],
};
