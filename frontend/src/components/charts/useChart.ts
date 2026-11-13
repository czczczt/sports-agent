// Общая обвязка Chart.js: создаёт график на <canvas>, уничтожает при размонтировании
// и пересоздаёт при смене темы (цвета берутся из CSS-токенов через themeToken).
import { useEffect, useRef, type DependencyList } from 'react';
import {
  BarController, BarElement, CategoryScale, Chart, LinearScale, LineController, LineElement,
  PointElement, Tooltip, type ChartConfiguration,
} from 'chart.js';
import { useTheme } from '@/theme/ThemeProvider';

Chart.register(LineController, LineElement, PointElement, BarController, BarElement, CategoryScale, LinearScale, Tooltip);

export const CHART_FONT = { family: "'Golos Text', system-ui, sans-serif", size: 11 };

export function useChart(buildConfig: () => ChartConfiguration, deps: DependencyList) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { effective } = useTheme();

  useEffect(() => {
    if (!canvasRef.current) return;
    const chart = new Chart(canvasRef.current, buildConfig());
    return () => chart.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effective, ...deps]);

  return canvasRef;
}
