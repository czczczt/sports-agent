import { useTheme } from '@/shared/theme';
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type ChartConfiguration,
} from 'chart.js';
import { useEffect, useRef } from 'react';

Chart.register(
  LineController,
  LineElement,
  PointElement,
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
);

export const CHART_FONT = { family: "'Golos Text', system-ui, sans-serif", size: 11 };

export function useChart(buildConfig: () => ChartConfiguration) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { effective } = useTheme();

  useEffect(() => {
    if (!canvasRef.current) return;
    const chart = new Chart(canvasRef.current, buildConfig());
    return () => chart.destroy();
  }, [effective, buildConfig]);

  return canvasRef;
}
