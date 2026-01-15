/** @type {import('tailwindcss').Config} */
import forms from "@tailwindcss/forms";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        // Deep, rich dark mode backgrounds (Cosmic)
        dark: {
          bg: '#020617',     // Slate 950 (darker base)
          surface: '#0f172a', // Slate 900
          card: 'rgba(15, 23, 42, 0.75)', // Glassy Slate 900
          border: 'rgba(51, 65, 85, 0.4)', // Slate 700 with opacity
          input: 'rgba(30, 41, 59, 0.6)',  // Dark input bg
        },
        // Brand colors (based on vibrant indigo)
        brand: {
          50: "rgb(var(--color-brand-50) / <alpha-value>)",
          100: "rgb(var(--color-brand-100) / <alpha-value>)",
          200: "rgb(var(--color-brand-200) / <alpha-value>)",
          300: "rgb(var(--color-brand-300) / <alpha-value>)",
          400: "rgb(var(--color-brand-400) / <alpha-value>)",
          500: "rgb(var(--color-brand-500) / <alpha-value>)",
          600: "rgb(var(--color-brand-600) / <alpha-value>)",
          700: "rgb(var(--color-brand-700) / <alpha-value>)",
          800: "rgb(var(--color-brand-800) / <alpha-value>)",
          900: "rgb(var(--color-brand-900) / <alpha-value>)",
          950: "rgb(var(--color-brand-950) / <alpha-value>)",
        },
        // Semantic colors (based on emerald)
        success: {
          50: "rgb(var(--color-success-50) / <alpha-value>)",
          100: "rgb(var(--color-success-100) / <alpha-value>)",
          200: "rgb(var(--color-success-200) / <alpha-value>)",
          300: "rgb(var(--color-success-300) / <alpha-value>)",
          400: "rgb(var(--color-success-400) / <alpha-value>)",
          500: "rgb(var(--color-success-500) / <alpha-value>)",
          600: "rgb(var(--color-success-600) / <alpha-value>)",
          700: "rgb(var(--color-success-700) / <alpha-value>)",
          800: "rgb(var(--color-success-800) / <alpha-value>)",
          900: "rgb(var(--color-success-900) / <alpha-value>)",
          950: "rgb(var(--color-success-950) / <alpha-value>)",
        },
        // Semantic colors (based on amber)
        warning: {
          50: "rgb(var(--color-warning-50) / <alpha-value>)",
          100: "rgb(var(--color-warning-100) / <alpha-value>)",
          200: "rgb(var(--color-warning-200) / <alpha-value>)",
          300: "rgb(var(--color-warning-300) / <alpha-value>)",
          400: "rgb(var(--color-warning-400) / <alpha-value>)",
          500: "rgb(var(--color-warning-500) / <alpha-value>)",
          600: "rgb(var(--color-warning-600) / <alpha-value>)",
          700: "rgb(var(--color-warning-700) / <alpha-value>)",
          800: "rgb(var(--color-warning-800) / <alpha-value>)",
          900: "rgb(var(--color-warning-900) / <alpha-value>)",
          950: "rgb(var(--color-warning-950) / <alpha-value>)",
        },
        // Semantic colors (based on rose)
        danger: {
          50: "rgb(var(--color-danger-50) / <alpha-value>)",
          100: "rgb(var(--color-danger-100) / <alpha-value>)",
          200: "rgb(var(--color-danger-200) / <alpha-value>)",
          300: "rgb(var(--color-danger-300) / <alpha-value>)",
          400: "rgb(var(--color-danger-400) / <alpha-value>)",
          500: "rgb(var(--color-danger-500) / <alpha-value>)",
          600: "rgb(var(--color-danger-600) / <alpha-value>)",
          700: "rgb(var(--color-danger-700) / <alpha-value>)",
          800: "rgb(var(--color-danger-800) / <alpha-value>)",
          900: "rgb(var(--color-danger-900) / <alpha-value>)",
          950: "rgb(var(--color-danger-950) / <alpha-value>)",
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      boxShadow: {
        'glow': '0 0 15px -3px rgba(99, 102, 241, 0.4)',
        'glow-lg': '0 0 25px -5px rgba(99, 102, 241, 0.6)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.2)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'float': 'float 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-5px)' },
        },
      },
    },
  },
  plugins: [forms],
};

