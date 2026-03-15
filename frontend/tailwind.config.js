/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cp: {
          bg: '#0F0F23',
          card: '#12122A',
          footer: '#0A0A1A',
          purple: '#7C3AED',
          'purple-light': '#A78BFA',
          rose: '#F43F5E',
          cyan: '#06B6D4',
          text: '#E2E8F0',
          muted: '#8B8BA0',
          dim: '#5B5B70',
          border: 'rgba(124, 58, 237, 0.25)',
        },
      },
      fontFamily: {
        orbitron: ['Orbitron', 'sans-serif'],
        exo: ['"Exo 2"', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
