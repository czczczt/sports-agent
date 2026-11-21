// График темпа спортсмена по стартам (профиль). Перенос скрипта из athlete_profile.html.
import type { Plugin } from 'chart.js';
import type { DynamicsPoint } from '@/api/types';
import { themeToken } from '@/theme/ThemeProvider';
import { CHART_FONT, useChart } from './useChart';

const NORM_SHORT: Record<string, string> = {
  marathon: '42 км',
  half_marathon: '21.1 км',
  '10000m': '10 км',
  '5000m': '5 км',
  '3000m': '3 км',
  '1500m': '1.5 км',
  '1000m': '1 км',
  '800m': '800 м',
  '400m': '400 м',
  '200m': '200 м',
  '100m': '100 м',
  '60m': '60 м',
  '100k': '100 км',
};

function shortDistance(d: DynamicsPoint): string {
  if (d.norm_distance && NORM_SHORT[d.norm_distance]) return NORM_SHORT[d.norm_distance];
  if (d.distance_name) {
    const km = d.distance_name.match(/(\d+(?:[.,]\d+)?)\s*км/i);
    if (km) return `${km[1].replace(',', '.')} км`;
    const m = d.distance_name.match(/(\d+)\s*м/i);
    if (m) return `${m[1]} м`;
  }
  return d.distance_name || '';
}

function dayMonth(date: string): string {
  const parts = date ? date.split(/[-T :]/) : [];
  return parts.length >= 3 ? `${parts[2].padStart(2, '0')}.${parts[1].padStart(2, '0')}` : date || '';
}

const paceMin = (d: DynamicsPoint) => (d.pace_s_per_km ? +(d.pace_s_per_km / 60).toFixed(2) : null);

export function PaceChart({ data }: { data: DynamicsPoint[] }) {
  const canvasRef = useChart(() => {
    const brand = themeToken('--brand');
    const muted = themeToken('--text-muted');
    const grid = themeToken('--border-soft');
    const surface = themeToken('--surface');

    // Один старт: точка посередине, по краям невидимые точки — иначе линия не рисуется.
    const isSingle = data.length === 1;
    const labels = isSingle
      ? ['', [dayMonth(data[0].date), shortDistance(data[0])], ' ']
      : data.map((d) => [dayMonth(d.date), shortDistance(d)]);
    const values = isSingle ? [paceMin(data[0]), paceMin(data[0]), paceMin(data[0])] : data.map(paceMin);
    const pointAt = (i: number) => data[isSingle ? 0 : i];

    // Подпись «время» над осью Y, по центру столбца чисел.
    const axisCaption: Plugin<'line'> = {
      id: 'axisCaption',
      afterDraw(c) {
        const y = c.scales.y;
        if (!y) return;
        const ctx = c.ctx;
        ctx.save();
        ctx.font = "11px 'Golos Text', system-ui, sans-serif";
        const numCenterX = y.right - 3 - ctx.measureText('5,0').width / 2;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillStyle = muted;
        ctx.fillText('время', numCenterX, y.top - 14);
        ctx.restore();
      },
    };

    return {
      type: 'line',
      plugins: [axisCaption as Plugin],
      data: {
        labels,
        datasets: [{
          label: 'Темп, мин/км',
          data: values,
          borderColor: brand,
          backgroundColor: brand,
          pointBackgroundColor: brand,
          pointBorderColor: surface,
          pointRadius: isSingle ? [0, 4, 0] : 4,
          borderWidth: 2.5,
          tension: isSingle ? 0 : 0.25,
          spanGaps: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 28, bottom: 0, left: 0, right: 12 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: (item) => !isSingle || item.dataIndex === 1,
            callbacks: {
              title: (items) => {
                const p = pointAt(items[0].dataIndex);
                return p ? `${p.date} · ${p.event_title}` : '';
              },
              label: (item) => {
                const p = pointAt(item.dataIndex);
                return p ? ` ${p.distance_name}: ${p.time_formatted} (${p.pace_formatted})` : '';
              },
            },
          },
        },
        scales: {
          x: { ticks: { display: false, autoSkip: false }, grid: { display: false } },
          y: {
            reverse: true,
            ticks: {
              color: muted,
              font: CHART_FONT,
              callback: (val) => (typeof val === 'number' ? val.toFixed(1).replace('.', ',') : val),
            },
            grid: { color: grid },
          },
        },
      },
    };
  }, [data]);

  return <canvas ref={canvasRef} role="img" aria-label="График темпа спортсмена по датам стартов" />;
}
