/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          500: '#2E7D32',
          600: '#1B5E20',
          700: '#14532d',
        },
        lychee: {
          red: '#C62828',
          gold: '#FF8F00',
          green: '#2E7D32',
          light: '#FFF8F0',
        },
      },
      boxShadow: {
        panel: '0 10px 30px rgba(15, 23, 42, 0.08)',
      },
    },
  },
  plugins: [],
}
