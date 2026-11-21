import type { RatingNorm } from '@/shared/api';
import { paths } from '@/shared/config';
import { pyRound } from '@/shared/lib';
import { AsyncView, EmptyState } from '@/shared/ui';
import { Link } from 'react-router-dom';
import layout from './RatingFormulaView.module.css';
import { useRatingFormula } from './useRatingFormula';

const DISTANCE_TITLES: Record<string, string> = {
  '24h': '24 часа',
  half_marathon: 'Полумарафон',
  marathon: 'Марафон',
  '1mile': '1 миля',
  '100km': '100 км',
};

const distanceTitle = (cls: string) => DISTANCE_TITLES[cls] ?? cls.replace(/m/g, ' м');
const normValue = (n: RatingNorm) => (n.unit === 's' ? pyRound(n.value, 1) : pyRound(n.value, 0));

export function RatingFormulaView(): React.JSX.Element {
  const query = useRatingFormula();
  const data = query.data;

  return (
    <div className={[layout.formulaPage, layout.formulaPageSimple].join(' ')}>
      <header className={layout.formulaSimpleHeader}>
        <Link to={paths.rating} className={layout.formulaSimpleBack}>
          ← Рейтинг
        </Link>
        <h1>Как посчитано</h1>
        <p>
          <strong>Бег</strong>
        </p>
      </header>

      <section
        className={[layout.formulaSimpleCard, layout.formulaSimpleCalculation].join(' ')}
        aria-labelledby="calculation-title"
      >
        <div className={layout.formulaSimpleCardHeading}>
          <span>Формула</span>
          <h2 id="calculation-title">Баллы за один результат</h2>
        </div>

        <div
          className={layout.formulaSimpleEquation}
          aria-label="норматив разделить на время умножить на тысячу"
        >
          <span>баллы</span>
          <b>=</b>
          <span className={layout.formulaSimpleFraction}>
            <strong>норматив</strong>
            <i>время</i>
          </span>
          <b>×</b>
          <strong>1000</strong>
        </div>

        <div className={layout.formulaSimpleNote}>
          Для обычных дистанций используется время в секундах. Сначала берётся chip time, а если его нет — gun
          time. Для 24 часов применяется формула:{' '}
          <strong>пройденные километры ÷ норматив в километрах × 1000</strong>.
        </div>
      </section>

      <section
        className={[layout.formulaSimpleCard, layout.formulaSimpleNorms].join(' ')}
        aria-labelledby="norms-title"
      >
        <div className={layout.formulaSimpleCardHeading}>
          <span>Таблица</span>
          <h2 id="norms-title">Нормативы</h2>
          <p>{data?.year ?? 2026} год · бег</p>
        </div>

        <AsyncView query={query}>
          {(data) =>
            data.norms.length === 0 ? (
              <EmptyState title="Нормативов пока нет" />
            ) : (
              <div className={layout.formulaSimpleTableWrap}>
                <table className={layout.formulaSimpleTable}>
                  <thead>
                    <tr>
                      <th scope="col">Дистанция</th>
                      <th scope="col">Мужчины</th>
                      <th scope="col">Женщины</th>
                      <th scope="col">Единица</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.norms
                      .filter((n) => n.gender === 'M')
                      .map((m) => {
                        const f = data.norms.find(
                          (n) => n.gender === 'F' && n.distance_class === m.distance_class,
                        );
                        return (
                          <tr key={m.distance_class}>
                            <th scope="row">{distanceTitle(m.distance_class)}</th>
                            <td>{normValue(m)}</td>
                            <td>{f ? normValue(f) : '—'}</td>
                            <td>{m.unit === 'km' ? 'км' : 'с'}</td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            )
          }
        </AsyncView>
        <p className={layout.formulaSimpleTableNote}>
          Норматив выбирается по дистанции и полу спортсмена. В рейтинг попадают только зачётные финиши.
        </p>
      </section>
    </div>
  );
}
