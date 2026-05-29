import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        covenant: {
          gold: '#FFF4B8',
          blue: '#336CC1',
          red: '#E8392C',
          green: '#2DB757',
          orange: '#F5A623',
          purple: '#9B5DE5',
          yellow: '#FFE600',
        },
      },
    },
  },
  plugins: [],
} satisfies Config
