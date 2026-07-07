/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cp: {
          bg: 'var(--cp-bg)',
          card: 'var(--cp-card)',
          footer: 'var(--cp-footer)',
          purple: 'var(--cp-purple)',
          'purple-light': 'var(--cp-purple-light)',
          rose: 'var(--cp-rose)',
          cyan: 'var(--cp-cyan)',
          text: 'var(--cp-text)',
          muted: 'var(--cp-muted)',
          dim: 'var(--cp-dim)',
          border: 'var(--cp-border)',
          input: 'var(--cp-input)',
          overlay: 'var(--cp-overlay)',
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
