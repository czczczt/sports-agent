// Гистограмма финишных времён дистанции (блок «Конкуренция»). Перенос скрипта из race_detail.html.
import type { CompetitionDistribution, DistributionBin } from '@/api/types';
import { themeToken } from '@/theme/ThemeProvider';
import { CHART_FONT, useChart } from './useChart';

export function DistributionChart({ competition }: { competition: CompetitionDistribution }) {
  const canvasRef = useChart(() => {
    const bins = competition.distribution_bins;
    const meTime = competition.athlete_result?.time_s;
    const isMine = (b: DistributionBin) => !!meTime && meTime >= b.bin_start_s && meTime <= b.bin_end_s;

    const brand = themeToken('--brand');
    const soft = themeToken('--brand-soft');
    const run = themeToken('--sport-run');
    const muted = themeToken('--text-muted');
    const grid = themeToken('--border-soft');

    return {
      type: 'bar',
      data: {
        labels: bins.map((b) => b.label.split(' - ')[0]),
        datasets: [{
          label: 'Финишёров в интервале',
          data: bins.map((b) => b.count),
          backgroundColor: bins.map((b) => (isMine(b) ? run : soft)),
          borderColor: bins.map((b) => (isMine(b) ? run : brand)),
          borderWidth: 1.5,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => bins[items[0].dataIndex].label,
              afterLabel: (item) => (isMine(bins[item.dataIndex]) ? 'Здесь ваш финиш' : ''),
            },
          },
        },
        scales: {
          x: { ticks: { color: muted, font: CHART_FONT, maxRotation: 0, autoSkip: true }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { color: muted, font: CHART_FONT, precision: 0 }, grid: { color: grid } },
        },
      },
    };
  }, [competition]);

  return <canvas ref={canvasRef} role="img" aria-label="Гистограмма финишных времён участников дистанции" />;
}
