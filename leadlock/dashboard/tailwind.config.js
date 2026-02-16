/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f4ff',
          100: '#e0e9ff',
          200: '#c7d6fe',
          300: '#a4b8fc',
          400: '#7b93f8',
          500: '#5a72f0',
          600: '#4259e3',
          700: '#3548cf',
          800: '#2d3da8',
          900: '#2a3785',
          950: '#1a2151',
        },
      },
      fontFamily: {
        sans: ['"Geist"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"Geist Mono"', '"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'data': ['0.8125rem', { lineHeight: '1.25rem', letterSpacing: '-0.01em', fontWeight: '500' }],
      },
      borderRadius: {
        'card': '10px',
      },
      boxShadow: {
        'card': '0 0 0 1px rgba(148, 163, 184, 0.06)',
        'card-hover': '0 0 0 1px rgba(148, 163, 184, 0.12)',
        'glow': '0 0 20px rgba(90, 114, 240, 0.08)',
      },
    },
  },
  plugins: [],
};
