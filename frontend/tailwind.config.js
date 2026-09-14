/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Warm, paper-like neutrals. No saturated brand colour anywhere --
        // the only strong tones are reserved for clinical status.
        sand: {
          50:  '#FDFBF7',
          100: '#FAF7F2',
          200: '#F4EFE6',
          300: '#EBE4D7',
          400: '#DDD3C1',
          500: '#C7B9A1',
          600: '#A6957A',
        },
        ink: {
          DEFAULT: '#1A1815',
          soft:    '#3A352E',
          muted:   '#6B6459',
          faint:   '#948C7E',
        },
        line: {
          DEFAULT: '#E6DFD3',
          strong:  '#D4C9B6',
        },
        // Status tones, desaturated to sit inside a neutral palette.
        status: {
          calm:   '#4A6B57',
          calmBg: '#E8EFE9',
          watch:  '#9A6B34',
          watchBg:'#F6EDE0',
          alert:  '#95403A',
          alertBg:'#F6E5E3',
        },
      },
      fontFamily: {
        // Handwritten accent -- headlines and the wordmark only, never data.
        hand: ['Caveat', 'Segoe Script', 'cursive'],
        // Warm serif for headings.
        display: ['Fraunces', 'Iowan Old Style', 'Georgia', 'serif'],
        // Clean sans for everything readable, with tabular figures for numbers.
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI',
               'Roboto', 'sans-serif'],
      },
      borderRadius: { xl2: '1.25rem' },
      boxShadow: {
        soft: '0 1px 2px rgba(26,24,21,0.04), 0 8px 24px -12px rgba(26,24,21,0.14)',
        lift: '0 2px 4px rgba(26,24,21,0.05), 0 18px 40px -20px rgba(26,24,21,0.28)',
      },
      keyframes: {
        'fade-up': {
          '0%':   { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        'draw': { '0%': { strokeDashoffset: '1' }, '100%': { strokeDashoffset: '0' } },
        'blink': {
          '0%,92%,100%': { transform: 'scaleY(1)' },
          '96%': { transform: 'scaleY(0.08)' },
        },
      },
      animation: {
        'fade-up': 'fade-up .5s cubic-bezier(.2,.8,.2,1) both',
        'fade-in': 'fade-in .4s ease both',
        blink: 'blink 5.5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
