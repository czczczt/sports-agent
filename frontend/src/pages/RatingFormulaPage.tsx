// «Как посчитано» (/rating-formula). Перенос rating_formula.html: формула и нормативы 2026 года.
import { Link } from 'react-router-dom';
import { ratingApi } from '@/api/endpoints';
import type { RatingNorm } from '@/api/types';
import { PageState } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { pyRound } from '@/lib/format';

const DISTANCE_TITLES: Record<string, string> = {
  '24h': '24 часа',
  half_marathon: 'Полумарафон',
  marathon: 'Марафон',
  '1mile': '1 миля',
  '100km': '100 км',
};

const distanceTitle = (cls: string) => DISTANCE_TITLES[cls] ?? cls.replace(/m/g, ' м');
const normValue = (n: RatingNorm) => (n.unit === 's' ? pyRound(n.value, 1) : pyRound(n.value, 0));

export function RatingFormulaPage() {
  useDocumentTitle('Как посчитано — беговой рейтинг');
  const { data, error, loading, reload } = useApi((signal) => ratingApi.formula(signal), []);

  return (
    <div className="formula-page formula-page--simple">
      <header className="formula-simple-header">
        <Link to="/rating-view" className="formula-simple-back">← Рейтинг</Link>
        <h1>Как посчитано</h1>
        <p><strong>Бег</strong></p>
      </header>

      <section className="formula-simple-card formula-simple-calculation" aria-labelledby="calculation-title">
        <div className="formula-simple-card__heading">
          <span>Формула</span>
          <h2 id="calculation-title">Баллы за один результат</h2>
        </div>

        <div className="formula-simple-equation" aria-label="норматив разделить на время умножить на тысячу">
          <span>баллы</span>
          <b>=</b>
          <span className="formula-simple-fraction">
            <strong>норматив</strong>
            <i>время</i>
          </span>
          <b>×</b>
          <strong>1000</strong>
        </div>

        <div className="formula-simple-note">
          Для обычных дистанций используется время в секундах. Сначала берётся chip time, а если его нет — gun time.
          Для 24 часов применяется формула: <strong>пройденные километры ÷ норматив в километрах × 1000</strong>.
        </div>
      </section>

      <section className="formula-simple-card formula-simple-norms" aria-labelledby="norms-title">
        <div className="formula-simple-card__heading">
          <span>Таблица</span>
          <h2 id="norms-title">Нормативы</h2>
          <p>{data?.year ?? 2026} год · бег</p>
        </div>

        <PageState loading={loading} error={error} hasData={!!data} onRetry={reload}>
          {() => (
            <div className="formula-simple-table-wrap">
              <table className="formula-simple-table">
                <thead>
                  <tr>
                    <th>Дистанция</th>
                    <th>Мужчины</th>
                    <th>Женщины</th>
                    <th>Единица</th>
                  </tr>
                </thead>
                <tbody>
                  {data!.norms.filter((n) => n.gender === 'M').map((m) => {
                    const f = data!.norms.find((n) => n.gender === 'F' && n.distance_class === m.distance_class);
                    return (
                      <tr key={m.distance_class}>
                        <th>{distanceTitle(m.distance_class)}</th>
                        <td>{normValue(m)}</td>
                        {f && <td>{normValue(f)}</td>}
                        <td>{m.unit === 'km' ? 'км' : 'с'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </PageState>
        <p className="formula-simple-table-note">Норматив выбирается по дистанции и полу спортсмена. В рейтинг попадают только зачётные финиши.</p>
      </section>
    </div>
  );
}
