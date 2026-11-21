// «Как посчитано» (/rating-formula).
// Реализация по SPEC v1.3 §9.1–§9.4, §10.2 (строки 720–730):
// полные формулы четырёх видов спорта (бег, лыжи/биатлон, триатлон, трейл), легенда обозначений и нормативы бега 2026.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ratingApi } from '@/api/endpoints';
import type { RatingNorm } from '@/api/types';
import { PageState } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { pyRound } from '@/lib/format';

type SportTab = 'all' | 'run' | 'ski' | 'triathlon' | 'trail';

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
  useDocumentTitle('Как посчитано — формулы рейтинга по видам спорта');
  const [activeTab, setActiveTab] = useState<SportTab>('all');
  const { data, error, loading, reload } = useApi((signal) => ratingApi.formula(signal), []);

  return (
    <div className="formula-page formula-page--simple">
      <header className="formula-simple-header">
        <Link to="/rating-view" className="formula-simple-back">← Рейтинг</Link>
        <h1>Как посчитано</h1>
        <p>Формулы подсчёта очков рейтинга по видам спорта и легенда обозначений (SPEC v1.3 §9, §10.2)</p>

        <nav className="formula-sports-nav" aria-label="Фильтр по видам спорта">
          <button
            type="button"
            className={`formula-sport-btn ${activeTab === 'all' ? 'formula-sport-btn--active' : ''}`}
            onClick={() => setActiveTab('all')}
          >
            Все виды
          </button>
          <button
            type="button"
            className={`formula-sport-btn ${activeTab === 'run' ? 'formula-sport-btn--active' : ''}`}
            onClick={() => setActiveTab('run')}
          >
            Бег
          </button>
          <button
            type="button"
            className={`formula-sport-btn ${activeTab === 'ski' ? 'formula-sport-btn--active' : ''}`}
            onClick={() => setActiveTab('ski')}
          >
            Лыжи и биатлон
          </button>
          <button
            type="button"
            className={`formula-sport-btn ${activeTab === 'triathlon' ? 'formula-sport-btn--active' : ''}`}
            onClick={() => setActiveTab('triathlon')}
          >
            Триатлон
          </button>
          <button
            type="button"
            className={`formula-sport-btn ${activeTab === 'trail' ? 'formula-sport-btn--active' : ''}`}
            onClick={() => setActiveTab('trail')}
          >
            Трейл
          </button>
        </nav>
      </header>

      {/* Сетка формул по видам спорта */}
      <div className="formula-sports-grid">
        {/* 1. БЕГ */}
        {(activeTab === 'all' || activeTab === 'run') && (
          <section className="formula-simple-card" aria-labelledby="formula-run-title">
            <span className="formula-badge">Бег</span>
            <h2 id="formula-run-title">Беговой рейтинг</h2>
            <p className="formula-caption">Нормативы по году, дистанции и полу (SPEC §9.1, §10.2)</p>

            <div className="formula-expression">
              баллы = (норматив / время) × 1000
            </div>

            <div className="formula-simple-note">
              <p>Для стандартных дистанций время берётся в секундах. В приоритете чип-время (<strong>chip time</strong>), при его отсутствии — выстрел (<strong>gun time</strong>).</p>
              <p style={{ marginTop: '8px' }}>Для суточного бега (24 часа) применяется формула: <strong>пройденные км ÷ норматив в км × 1000</strong>.</p>
            </div>
          </section>
        )}

        {/* 2. ЛЫЖИ И БИАТЛОН */}
        {(activeTab === 'all' || activeTab === 'ski') && (
          <section className="formula-simple-card" aria-labelledby="formula-ski-title">
            <span className="formula-badge">Лыжи и биатлон</span>
            <h2 id="formula-ski-title">Лыжный рейтинг и биатлон</h2>
            <p className="formula-caption">Плюс очки Russialoppet ÷ 7 (подтверждение методологов, SPEC §9.2, §10.2)</p>

            <div className="formula-expression">
              гонка = 100 × (N − место + 1) / N
            </div>
            <div className="formula-expression" style={{ marginTop: '8px' }}>
              сезон = Σ баллы_гонок + очки_RL ÷ 7
            </div>

            <div className="formula-simple-note">
              <p>Биатлон входит в лыжный рейтинг и рассчитывается по той же формуле места.</p>
              <p style={{ marginTop: '8px' }}><strong>N</strong> — число финишёров того же пола на дистанции; <strong>место</strong> — среди того же пола.</p>
              <p style={{ marginTop: '8px' }}>Марафоны серии Russialoppet по формуле места не считаются, а приносят <strong>очки RL ÷ 7</strong> (чтобы результат марафона не удваивался).</p>
            </div>
          </section>
        )}

        {/* 3. ТРИАТЛОН */}
        {(activeTab === 'all' || activeTab === 'triathlon') && (
          <section className="formula-simple-card" aria-labelledby="formula-triathlon-title">
            <span className="formula-badge">Триатлон</span>
            <h2 id="formula-triathlon-title">Триатлон (TriStats)</h2>
            <p className="formula-caption">Относительно лидера группы (SPEC §9.3, §10.2)</p>

            <div className="formula-expression">
              баллы = (Rmax × (1 − (Tа − Tл) / Tл) + Bmed) × K
            </div>

            <div className="formula-simple-note">
              <p>Группа формируется по полу и возрасту внутри гонки (если возрастных групп нет — по полу).</p>
              <p style={{ marginTop: '8px' }}><strong>Классы дистанций (Rmax):</strong></p>
              <table className="formula-rmax-table">
                <thead>
                  <tr>
                    <th>Класс</th>
                    <th>Дистанция</th>
                    <th>Rmax</th>
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

              <p style={{ marginTop: '10px' }}><strong>Коэффициент старта (K):</strong> regular (обычный) = 1.0; worlds (чемпионат мира) = 1.10; kona (Кона) = 1.15.</p>
            </div>
          </section>
        )}

        {/* 4. ТРЕЙЛ */}
        {(activeTab === 'all' || activeTab === 'trail') && (
          <section className="formula-simple-card" aria-labelledby="formula-trail-title">
            <span className="formula-badge">Трейл</span>
            <h2 id="formula-trail-title">Трейлраннинг</h2>
            <p className="formula-caption">Без набора высоты не считается (SPEC §9.4, §10.2)</p>

            <div className="formula-expression">
              баллы = max(0, 10 × (км + D+ / 100) × (1 − (Tа − Tл) / Tл) + Bmed)
            </div>

            <div className="formula-simple-note">
              <p>Базовый максимум очков трейла пропорционален длине и набору: <strong>Rmax = 10 × (км + D+ / 100)</strong>, коэффициент K = 1.0.</p>
              <p style={{ marginTop: '8px' }}><strong>D+</strong> — суммарный набор высоты в метрах. Без подтверждённого набора высоты старт является <strong>незачётным</strong>.</p>
              <p style={{ marginTop: '8px' }}>Очки TopList (при наличии на toplist.run) сохраняются справочно и в рейтинг не идут.</p>
            </div>
          </section>
        )}
      </div>

      {/* Карточка Легенды по SPEC §10.2 */}
      <section className="formula-simple-card formula-legend-card" aria-labelledby="legend-title">
        <div className="formula-simple-card__heading">
          <span>Справочник</span>
          <h2 id="legend-title">Легенда обозначений</h2>
          <p>Параметры и константы формул по спецификации SPEC v1.3 §10.2</p>
        </div>

        <div className="formula-legend-grid">
          <div className="formula-legend-item">
            <span className="formula-legend-symbol">Tа</span>
            <span className="formula-legend-desc">Время финиша спортсмена (в секундах).</span>
          </div>
          <div className="formula-legend-item">
            <span className="formula-legend-symbol">Tл</span>
            <span className="formula-legend-desc">Время лидера группы (пол + возрастная категория; либо только пол). Считается по всем финишёрам.</span>
          </div>
          <div className="formula-legend-item">
            <span className="formula-legend-symbol">Tмед</span>
            <span className="formula-legend-desc">Медианное время группы (считается по всем строкам протокола, включая сторонних участников).</span>
          </div>
          <div className="formula-legend-item">
            <span className="formula-legend-symbol">Bmed</span>
            <span className="formula-legend-desc">Бонус за обгон медианы: <strong>2 × max(0, Tмед − Tа)</strong> в минутах. Для финишировавших позже медианы Bmed = 0.</span>
          </div>
          <div className="formula-legend-item">
            <span className="formula-legend-symbol">K</span>
            <span className="formula-legend-desc">Коэффициент статуса гонки: <strong>1.0</strong> (обычный старт), <strong>1.10</strong> (чемпионат мира / worlds), <strong>1.15</strong> (Kona).</span>
          </div>
          <div className="formula-legend-item">
            <span className="formula-legend-symbol">Rmax</span>
            <span className="formula-legend-desc">Максимум баллов класса дистанции (для триатлона — фиксированный класс; для трейла — 10 × (км + D+/100)).</span>
          </div>
          <div className="formula-legend-item">
            <span className="formula-legend-symbol">D+</span>
            <span className="formula-legend-desc">Суммарный вертикальный набор высоты (в метрах). Обязателен для зачёта трейла.</span>
          </div>
          <div className="formula-legend-item">
            <span className="formula-legend-symbol">N</span>
            <span className="formula-legend-desc">Общее число финишёров того же пола на данной дистанции гонки.</span>
          </div>
        </div>
      </section>

      {/* Таблица нормативов бега */}
      {(activeTab === 'all' || activeTab === 'run') && (
        <section className="formula-simple-card formula-simple-norms" aria-labelledby="norms-title">
          <div className="formula-simple-card__heading">
            <span>Таблица нормативов</span>
            <h2 id="norms-title">Нормативы бега</h2>
            <p>{data?.year ?? 2026} год · утверждённая нормативная сетка</p>
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
          <p className="formula-simple-table-note">Норматив выбирается по дистанции и полу спортсмена. В зачёт идут результаты сотрудников с подтверждёнными финишами.</p>
        </section>
      )}
    </div>
  );
}
