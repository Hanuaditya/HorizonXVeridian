/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,jsx}',
    './components/**/*.{js,jsx}',
    './lib/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        veridian: {
          purple: { 50:'#EEEDFE', 200:'#AFA9EC', 400:'#7F77DD', 600:'#534AB7', 800:'#3C3489' },
          green:  { 400:'#4ADE80', 500:'#22C55E', 600:'#16A34A' },
          red:    { 400:'#F87171', 500:'#EF4444', 600:'#DC2626' },
          amber:  { 400:'#FBBF24', 500:'#F59E0B', 600:'#D97706' },
        },
        dark: { 900:'#080810', 800:'#0E0E1A', 700:'#141422', 600:'#1C1C2E', 500:'#24243A' },
      },
      fontFamily: {
        sans: ['Inter','system-ui','sans-serif'],
        mono: ['JetBrains Mono','Fira Code','monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 2.5s cubic-bezier(0.4,0,0.6,1) infinite',
        'fade-in':    'fadeIn 0.35s ease-out',
        'slide-down': 'slideDown 0.35s ease-out',
      },
      keyframes: {
        fadeIn:    { '0%':{ opacity:'0', transform:'translateY(6px)' }, '100%':{ opacity:'1', transform:'translateY(0)' } },
        slideDown: { '0%':{ opacity:'0', transform:'translateY(-12px)' }, '100%':{ opacity:'1', transform:'translateY(0)' } },
      },
    },
  },
  plugins: [],
}
