import type { CompetitionDistribution, DistributionBin } from '@/shared/api';
import { CHART_FONT, useChart } from '@/shared/charts';
import { themeToken } from '@/shared/theme';
import type { ChartConfiguration } from 'chart.js';
import { useCallback } from 'react';

interface DistributionChartProps {
  competition: CompetitionDistribution;
  isOwnProfile?: boolean;
}

export function DistributionChart({ competition, isOwnProfile = false }: DistributionChartProps): React.JSX.Element {
  const canvasRef = useChart(
    useCallback((): ChartConfiguration => {
      const bins = competition.distribution_bins;
      const meTime = competition.athlete_result?.time_s;
      const isMine = (b: DistributionBin | undefined) =>
        !!b && !!meTime && meTime >= b.bin_start_s && meTime <= b.bin_end_s;

      const brand = themeToken('--brand');
      const soft = themeToken('--brand-soft');
      const run = themeToken('--sport-run');
      const muted = themeToken('--text-muted');
      const grid = themeToken('--border-soft');

      return {
        type: 'bar',
        data: {
          labels: bins.map((b) => b.label.split(' - ')[0]),
          datasets: [
            {
              label: 'Финишёров в интервале',
              data: bins.map((b) => b.count),
              backgroundColor: bins.map((b) => (isMine(b) ? run : soft)),
              borderColor: bins.map((b) => (isMine(b) ? run : brand)),
              borderWidth: 1.5,
              borderRadius: 4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: (items) => bins[items[0]?.dataIndex ?? -1]?.label ?? '',
                afterLabel: (item) =>
                  isMine(bins[item.dataIndex])
                    ? isOwnProfile
                      ? 'Здесь ваш финиш'
                      : 'Здесь финиш спортсмена'
                    : '',
              },
            },
          },
          scales: {
            x: {
              ticks: { color: muted, font: CHART_FONT, maxRotation: 0, autoSkip: true },
              grid: { display: false },
            },
            y: {
              beginAtZero: true,
              ticks: { color: muted, font: CHART_FONT, precision: 0 },
              grid: { color: grid },
            },
          },
        },
      };
    }, [competition, isOwnProfile]),
  );

  return (
    <canvas ref={canvasRef} role="img" aria-label="Гистограмма финишных времён участников дистанции">
      {competition.distribution_bins.map((bin) => bin.label + ': ' + bin.count).join('; ')}
    </canvas>
  );
}
