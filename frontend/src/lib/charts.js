/** Chart.js registration and a shared, paper-toned house style. */
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, Filler, Tooltip, Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement,
  Filler, Tooltip, Legend)

ChartJS.defaults.font.family =
  "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
ChartJS.defaults.font.size = 11
ChartJS.defaults.color = '#6B6459'

export const C = {
  observed:   '#1A1815',
  predicted:  '#A6957A',
  band:       'rgba(166, 149, 122, 0.18)',
  scenario:   '#4A6B57',
  scenarioBand: 'rgba(74, 107, 87, 0.16)',
  positive:   '#4A6B57',
  negative:   '#9A6B34',
  grid:       'rgba(26, 24, 21, 0.07)',
  paper:      '#FFFFFF',
}

export function baseOptions({ yTitle, xTitle, reverseY = false } = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          boxWidth: 8, boxHeight: 8, usePointStyle: true, padding: 16,
          font: { size: 11, weight: '500' },
          // Datasets prefixed with "_" are structural (band edges), not content.
          filter: (item) => !item.text.startsWith('_'),
        },
      },
      tooltip: {
        backgroundColor: '#1A1815',
        padding: 12,
        cornerRadius: 10,
        titleFont: { weight: '600', size: 12 },
        bodyFont: { size: 12 },
        displayColors: true,
        boxPadding: 4,
        filter: (item) => !item.dataset.label.startsWith('_'),
      },
    },
    scales: {
      x: {
        title: { display: !!xTitle, text: xTitle, color: '#948C7E' },
        grid: { color: C.grid, drawTicks: false },
        border: { color: '#E6DFD3' },
        ticks: { maxRotation: 0, autoSkipPadding: 18, padding: 8 },
      },
      y: {
        title: { display: !!yTitle, text: yTitle, color: '#948C7E' },
        grid: { color: C.grid, drawTicks: false },
        border: { display: false },
        reverse: reverseY,
        ticks: { padding: 8 },
      },
    },
  }
}
