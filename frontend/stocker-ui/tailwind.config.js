/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts,scss}'],
  theme: {
    extend: {
      colors: {
        canvas: 'var(--color-canvas)',
        'canvas-subtle': 'var(--color-canvas-subtle)',
        border: 'var(--color-border)',
        text: 'var(--color-text)',
        muted: 'var(--color-muted)',
        accent: 'var(--color-accent)',
        'accent-soft': 'var(--color-accent-soft)',
        'accent-softer': 'var(--color-accent-softer)',
        success: 'var(--color-success)',
        'success-soft': 'var(--color-success-soft)',
        'success-muted': 'var(--color-success-muted)',
        danger: 'var(--color-danger)',
        'danger-soft': 'var(--color-danger-soft)',
        'danger-muted': 'var(--color-danger-muted)',
        warning: 'var(--color-warning)',
        'warning-soft': 'var(--color-warning-soft)',
        'warning-muted': 'var(--color-warning-muted)'
      },
      borderColor: {
        DEFAULT: 'var(--color-border)'
      },
      boxShadow: {
        subtle: 'var(--shadow-subtle)',
        popover: 'var(--shadow-popover)',
        focus: 'var(--shadow-focus)'
      },
      borderRadius: {
        DEFAULT: 'var(--radius-md)',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)'
      },
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)']
      },
      fontSize: {
        xs: ['var(--font-size-xs)', { lineHeight: 'var(--line-height-base)' }],
        sm: ['var(--font-size-sm)', { lineHeight: 'var(--line-height-base)' }],
        base: ['var(--font-size-base)', { lineHeight: 'var(--line-height-base)' }],
        lg: ['var(--font-size-lg)', { lineHeight: 'var(--line-height-base)' }],
        xl: ['var(--font-size-xl)', { lineHeight: 'var(--line-height-base)' }],
        '2xl': ['var(--font-size-2xl)', { lineHeight: 'var(--line-height-tight)' }]
      }
    }
  },
  plugins: []
};
