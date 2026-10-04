/** @type {import('tailwindcss').Config} */
export default {
  // Theming is driven by a `dark` class on <html>, set by ThemeContext.
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Semantic surfaces and text, backed by the CSS variables in
        // index.css. Components reference these instead of raw slate shades,
        // so light and dark are defined in exactly one place.
        app: 'rgb(var(--app-bg) / <alpha-value>)',
        surface: {
          DEFAULT: 'rgb(var(--surface) / <alpha-value>)',
          muted: 'rgb(var(--surface-muted) / <alpha-value>)',
          sunken: 'rgb(var(--surface-sunken) / <alpha-value>)',
        },
        edge: {
          DEFAULT: 'rgb(var(--border) / <alpha-value>)',
          strong: 'rgb(var(--border-strong) / <alpha-value>)',
        },
        ink: {
          DEFAULT: 'rgb(var(--text) / <alpha-value>)',
          muted: 'rgb(var(--text-muted) / <alpha-value>)',
          faint: 'rgb(var(--text-faint) / <alpha-value>)',
        },
        brand: {
          50: '#eef5ff',
          100: '#d9e8ff',
          500: '#2563eb',
          600: '#1d4ed8',
          700: '#1e40af',
        },
        // The sidebar stays dark in both themes; it only deepens a little.
        sidebar: {
          DEFAULT: 'rgb(var(--sidebar) / <alpha-value>)',
          hover: 'rgb(var(--sidebar-hover) / <alpha-value>)',
          active: 'rgb(var(--sidebar-active) / <alpha-value>)',
        },
      },
      boxShadow: {
        card: 'var(--shadow-card)',
      },
    },
  },
  plugins: [],
}
