import type { RatingNorm } from '@/shared/api';
import { paths } from '@/shared/config';
import { pyRound } from '@/shared/lib';
import { AsyncView, EmptyState } from '@/shared/ui';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import layout from './RatingFormulaView.module.css';
import { useRatingFormula } from './useRatingFormula';

const sportTabs = [
  ['all', 'Все виды'],
  ['run', 'Бег'],
  ['ski', 'Лыжи и биатлон'],
  ['triathlon', 'Триатлон'],
  ['trail', 'Трейл'],
] as const;

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
  const [activeTab, setActiveTab] = useState<(typeof sportTabs)[number][0]>('all');
  const query = useRatingFormula();
  const data = query.data;

  return (
    <div className={[layout.formulaPage, layout.formulaPageSimple].join(' ')}>
      <header className={layout.formulaSimpleHeader}>
        <Link to={paths.rating} className={layout.formulaSimpleBack}>
          ← Рейтинг
        </Link>
        <h1>Как посчитано</h1>
        <p>Формулы рейтинга по видам спорта и легенда обозначений.</p>
        <nav className={layout.formulaSportsNav} aria-label="Фильтр по видам спорта">
          {sportTabs.map(([value, label]) => (
            <button
              type="button"
              key={value}
              className={layout.formulaSportBtn}
              aria-pressed={activeTab === value}
              onClick={() => setActiveTab(value)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      {/* Сетка формул по видам спорта */}
      <div className={layout.formulaSportsGrid}>
        {/* 1. БЕГ */}
        {(activeTab === 'all' || activeTab === 'run') && (
          <section className={layout.formulaSimpleCard} aria-labelledby="formula-run-title">
            <span className={layout.formulaBadge}>Бег</span>
            <h2 id="formula-run-title">Беговой рейтинг</h2>
            <p className={layout.formulaCaption}>Нормативы по году, дистанции и полу (SPEC §9.1, §10.2)</p>

            <div className={layout.formulaExpression}>баллы = (норматив / время) × 1000</div>

            <div className={layout.formulaSimpleNote}>
              <p>
                Для стандартных дистанций время берётся в секундах. В приоритете чип-время (
                <strong>chip time</strong>), при его отсутствии — выстрел (<strong>gun time</strong>).
              </p>
              <p>
                Для суточного бега (24 часа) применяется формула:{' '}
                <strong>пройденные км ÷ норматив в км × 1000</strong>.
              </p>
            </div>
          </section>
        )}

        {/* 2. ЛЫЖИ И БИАТЛОН */}
        {(activeTab === 'all' || activeTab === 'ski') && (
          <section className={layout.formulaSimpleCard} aria-labelledby="formula-ski-title">
            <span className={layout.formulaBadge}>Лыжи и биатлон</span>
            <h2 id="formula-ski-title">Лыжный рейтинг и биатлон</h2>
            <p className={layout.formulaCaption}>
              Плюс очки Russialoppet ÷ 7 (подтверждение методологов, SPEC §9.2, §10.2)
            </p>

            <div className={layout.formulaExpression}>гонка = 100 × (N − место + 1) / N</div>
            <div className={layout.formulaExpression}>сезон = Σ баллы_гонок + очки_RL ÷ 7</div>

            <div className={layout.formulaSimpleNote}>
              <p>Биатлон входит в лыжный рейтинг и рассчитывается по той же формуле места.</p>
              <p>
                <strong>N</strong> — число финишёров того же пола на дистанции; <strong>место</strong> — среди
                того же пола.
              </p>
              <p>
                Марафоны серии Russialoppet по формуле места не считаются, а приносят{' '}
                <strong>очки RL ÷ 7</strong> (чтобы результат марафона не удваивался).
              </p>
            </div>
          </section>
        )}

        {/* 3. ТРИАТЛОН */}
        {(activeTab === 'all' || activeTab === 'triathlon') && (
          <section className={layout.formulaSimpleCard} aria-labelledby="formula-triathlon-title">
            <span className={layout.formulaBadge}>Триатлон</span>
            <h2 id="formula-triathlon-title">Триатлон (TriStats)</h2>
            <p className={layout.formulaCaption}>Относительно лидера группы (SPEC §9.3, §10.2)</p>

            <div className={layout.formulaExpression}>баллы = (Rmax × (1 − (Tа − Tл) / Tл) + Bmed) × K</div>

            <div className={layout.formulaSimpleNote}>
              <p>Группа формируется по полу и возрасту внутри гонки (если возрастных групп нет — по полу).</p>
              <p>
                <strong>Классы дистанций (Rmax):</strong>
              </p>
              <table className={layout.formulaRmaxTable}>
                <thead>
                  <tr>
                    <th scope="col">Класс</th>
                    <th scope="col">Дистанция</th>
                    <th scope="col">Rmax</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>full</td>
                    <td>Железная (226 км)</td>
                    <td>10 000</td>
                  </tr>
                  <tr>
                    <td>half</td>
                    <td>Полужелезная (113 км)</td>
                    <td>5 000</td>
                  </tr>
                  <tr>
                    <td>olympic</td>
                    <td>Олимпийская (51.5 км)</td>
                    <td>2 500</td>
                  </tr>
                  <tr>
                    <td>sprint</td>
                    <td>Спринт (25.75 км)</td>
                    <td>1 250</td>
                  </tr>
                  <tr>
                    <td>supersprint / indoor</td>
                    <td>Суперспринт / В манеже</td>
                    <td>625</td>
                  </tr>
                </tbody>
              </table>

              <p>
                <strong>Коэффициент старта (K):</strong> regular (обычный) = 1.0; worlds (чемпионат мира) =
                1.10; kona (Кона) = 1.15.
              </p>
            </div>
          </section>
        )}

        {/* 4. ТРЕЙЛ */}
        {(activeTab === 'all' || activeTab === 'trail') && (
          <section className={layout.formulaSimpleCard} aria-labelledby="formula-trail-title">
            <span className={layout.formulaBadge}>Трейл</span>
            <h2 id="formula-trail-title">Трейлраннинг</h2>
            <p className={layout.formulaCaption}>Без набора высоты не считается (SPEC §9.4, §10.2)</p>

            <div className={layout.formulaExpression}>
              баллы = max(0, 10 × (км + D+ / 100) × (1 − (Tа − Tл) / Tл) + Bmed)
            </div>

            <div className={layout.formulaSimpleNote}>
              <p>
                Базовый максимум очков трейла пропорционален длине и набору:{' '}
                <strong>Rmax = 10 × (км + D+ / 100)</strong>, коэффициент K = 1.0.
              </p>
              <p>
                <strong>D+</strong> — суммарный набор высоты в метрах. Без подтверждённого набора высоты старт
                является <strong>незачётным</strong>.
              </p>
              <p>Очки TopList (при наличии на toplist.run) сохраняются справочно и в рейтинг не идут.</p>
            </div>
          </section>
        )}
      </div>

      {/* Карточка Легенды по SPEC §10.2 */}
      <section
        className={[layout.formulaSimpleCard, layout.formulaLegendCard].join(' ')}
        aria-labelledby="legend-title"
      >
        <div className={layout.formulaSimpleCardHeading}>
          <span>Справочник</span>
          <h2 id="legend-title">Легенда обозначений</h2>
          <p>Параметры и константы формул по спецификации SPEC v1.3 §10.2</p>
        </div>

        <div className={layout.formulaLegendGrid}>
          <div className={layout.formulaLegendItem}>
            <span className={layout.formulaLegendSymbol}>Tа</span>
            <span className={layout.formulaLegendDesc}>Время финиша спортсмена (в секундах).</span>
          </div>
          <div className={layout.formulaLegendItem}>
            <span className={layout.formulaLegendSymbol}>Tл</span>
            <span className={layout.formulaLegendDesc}>
              Время лидера группы (пол + возрастная категория; либо только пол). Считается по всем финишёрам.
            </span>
          </div>
          <div className={layout.formulaLegendItem}>
            <span className={layout.formulaLegendSymbol}>Tмед</span>
            <span className={layout.formulaLegendDesc}>
              Медианное время группы (считается по всем строкам протокола, включая сторонних участников).
            </span>
          </div>
          <div className={layout.formulaLegendItem}>
            <span className={layout.formulaLegendSymbol}>Bmed</span>
            <span className={layout.formulaLegendDesc}>
              Бонус за обгон медианы: <strong>2 × max(0, Tмед − Tа)</strong> в минутах. Для финишировавших
              позже медианы Bmed = 0.
            </span>
          </div>
          <div className={layout.formulaLegendItem}>
            <span className={layout.formulaLegendSymbol}>K</span>
            <span className={layout.formulaLegendDesc}>
              Коэффициент статуса гонки: <strong>1.0</strong> (обычный старт), <strong>1.10</strong>{' '}
              (чемпионат мира / worlds), <strong>1.15</strong> (Kona).
            </span>
          </div>
          <div className={layout.formulaLegendItem}>
            <span className={layout.formulaLegendSymbol}>Rmax</span>
            <span className={layout.formulaLegendDesc}>
              Максимум баллов класса дистанции (для триатлона — фиксированный класс; для трейла — 10 × (км +
              D+/100)).
            </span>
          </div>
          <div className={layout.formulaLegendItem}>
            <span className={layout.formulaLegendSymbol}>D+</span>
            <span className={layout.formulaLegendDesc}>
              Суммарный вертикальный набор высоты (в метрах). Обязателен для зачёта трейла.
            </span>
          </div>
          <div className={layout.formulaLegendItem}>
            <span className={layout.formulaLegendSymbol}>N</span>
            <span className={layout.formulaLegendDesc}>
              Общее число финишёров того же пола на данной дистанции гонки.
            </span>
          </div>
        </div>
      </section>

      {(activeTab === 'all' || activeTab === 'run') && (
        <section
          className={[layout.formulaSimpleCard, layout.formulaSimpleNorms].join(' ')}
          aria-labelledby="norms-title"
        >
          <div className={layout.formulaSimpleCardHeading}>
            <span>Таблица</span>
            <h2 id="norms-title">Нормативы бега</h2>
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
      )}
    </div>
  );
}
