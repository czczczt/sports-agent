import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { adminApi } from '@/api/endpoints';
import type { AccessRequestItem, ReportItem } from '@/api/types';
import { EmptyState, ErrorState, Icon, Loader } from '@/components/ui';
import { useAuth } from '@/context/AuthContext';
import { SITE_TITLE, useDocumentTitle } from '@/hooks/useDocumentTitle';
import { dateTimeRu, dateRu } from '@/lib/format';

const REPORT_KINDS: Record<string, string> = {
  not_me: 'Это не мой результат',
  add_start: 'Добавить мой старт',
  hide_me: 'Скрыть меня из рейтинга',
  link_me: 'Привязать к профилю',
  other_club: 'Другой клуб',
  data_error: 'Ошибка в данных',
  merge_profile: 'Объединить профили',
  other: 'Обращение',
};

export function AdminRequestsPage() {
  useDocumentTitle(`Заявки и модерация · ${SITE_TITLE}`);
  const { user, isAdmin, openAuthModal } = useAuth();
  const isModerator = isAdmin || user?.role === 'captain';

  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = (searchParams.get('tab') as 'access' | 'reports') || 'access';
  const accessFilter = searchParams.get('access_status') ?? 'pending';
  const reportsFilter = searchParams.get('report_status') ?? 'new';

  const [accessItems, setAccessItems] = useState<AccessRequestItem[]>([]);
  const [reportItems, setReportItems] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  const [athleteInputs, setAthleteInputs] = useState<Record<number, string>>({});
  const [commentInputs, setCommentInputs] = useState<Record<number, string>>({});
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ id: string; text: string; isError?: boolean } | null>(null);

  const loadData = async () => {
    if (!isModerator) return;
    setLoading(true);
    setError(null);
    try {
      if (currentTab === 'access') {
        const filter = accessFilter === 'all' ? '' : accessFilter;
        const res = await adminApi.accessRequests(filter);
        setAccessItems(res);
      } else {
        const filter = reportsFilter === 'all' ? '' : reportsFilter;
        const res = await adminApi.reports(filter);
        setReportItems(res);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error('Не удалось загрузить заявки'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentTab, accessFilter, reportsFilter, isModerator]);

  if (!isModerator) {
    return (
      <div className="card empty agent-auth-guard">
        <span className="empty__icon"><Icon name="user" /></span>
        <div className="strong">Требуются права модератора</div>
        <p className="small muted">Для просмотра и утверждения заявок требуется учётная запись администратора или капитана.</p>
        <button type="button" className="btn btn--primary" onClick={openAuthModal}>
          Войти
        </button>
      </div>
    );
  }

  const setTab = (tab: 'access' | 'reports') => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', tab);
    setSearchParams(next);
  };

  const setAccessStatusFilter = (st: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('access_status', st);
    setSearchParams(next);
  };

  const setReportsStatusFilter = (st: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('report_status', st);
    setSearchParams(next);
  };

  const handleAccessDecision = async (req: AccessRequestItem, decision: 'approve' | 'reject') => {
    const key = `access-${req.id}`;
    setProcessingId(key);
    setNotice(null);
    try {
      const athleteIdVal = athleteInputs[req.id] !== undefined
        ? (athleteInputs[req.id] ? parseInt(athleteInputs[req.id], 10) : null)
        : (req.candidate_athlete_id || req.athlete_id || null);

      const commentVal = commentInputs[req.id] || undefined;

      const updated = await adminApi.decideAccessRequest(req.id, {
        decision,
        athlete_id: athleteIdVal,
        comment: commentVal,
      });

      setAccessItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setNotice({
        id: key,
        text: decision === 'approve' ? 'Заявка на доступ успешно одобрена' : 'Заявка на доступ отклонена',
      });
    } catch (err: unknown) {
      setNotice({
        id: key,
        text: err instanceof Error ? err.message : 'Ошибка при принятии решения',
        isError: true,
      });
    } finally {
      setProcessingId(null);
    }
  };

  const handleReportDecision = async (report: ReportItem, decision: 'accepted' | 'resolved' | 'rejected') => {
    const key = `report-${report.id}`;
    setProcessingId(key);
    setNotice(null);
    try {
      const commentVal = commentInputs[report.id] || undefined;
      const updated = await adminApi.decideReport(report.id, {
        decision,
        moderator_comment: commentVal,
      });

      setReportItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      const label = decision === 'rejected' ? 'Обращение отклонено' : 'Решение сохранено';
      setNotice({
        id: key,
        text: label,
      });
    } catch (err: unknown) {
      setNotice({
        id: key,
        text: err instanceof Error ? err.message : 'Ошибка при сохранении решения',
        isError: true,
      });
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="h1 h1-sm">Модерация заявок</h1>
          <p className="lead">Рассмотрение заявок на регистрацию и обращений спортсменов.</p>
        </div>

        <div className="rating-segment">
          <button
            type="button"
            className={currentTab === 'access' ? 'is-active' : undefined}
            onClick={() => setTab('access')}
          >
            Заявки на доступ
          </button>
          <button
            type="button"
            className={currentTab === 'reports' ? 'is-active' : undefined}
            onClick={() => setTab('reports')}
          >
            Обращения
          </button>
        </div>
      </div>

      {currentTab === 'access' && (
        <div className="filters-bar" style={{ marginBottom: 16, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="small muted">Статус:</span>
          <div className="rating-segment">
            {[
              { val: 'pending', label: 'Ожидают' },
              { val: 'active', label: 'Одобренные' },
              { val: 'rejected', label: 'Отклонённые' },
              { val: 'all', label: 'Все' },
            ].map((f) => (
              <button
                key={f.val}
                type="button"
                className={accessFilter === f.val ? 'is-active' : undefined}
                onClick={() => setAccessStatusFilter(f.val)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {currentTab === 'reports' && (
        <div className="filters-bar" style={{ marginBottom: 16, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="small muted">Статус:</span>
          <div className="rating-segment">
            {[
              { val: 'new', label: 'Новые' },
              { val: 'accepted', label: 'Принятые' },
              { val: 'resolved', label: 'Выполненные' },
              { val: 'rejected', label: 'Отклонённые' },
              { val: 'all', label: 'Все' },
            ].map((f) => (
              <button
                key={f.val}
                type="button"
                className={reportsFilter === f.val ? 'is-active' : undefined}
                onClick={() => setReportsStatusFilter(f.val)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {error ? (
        <ErrorState error={error} onRetry={loadData} />
      ) : loading ? (
        <Loader text="Загрузка списка заявок…" />
      ) : currentTab === 'access' ? (
        accessItems.length === 0 ? (
          <EmptyState
            title="Заявок на доступ не найдено"
            text="С выбранным статусом в системе нет заявок пользователей."
          />
        ) : (
          <div className="grid-cards" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {accessItems.map((req) => {
              const key = `access-${req.id}`;
              const isBusy = processingId === key;
              const curNotice = notice?.id === key ? notice : null;
              const candidateId = req.candidate_athlete_id || req.athlete_id;
              const initialAthInput = athleteInputs[req.id] !== undefined
                ? athleteInputs[req.id]
                : (candidateId ? String(candidateId) : '');

              return (
                <div key={req.id} className="card card--pad" style={{ background: 'var(--surface)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
                    <div>
                      <div style={{ fontSize: 18, fontWeight: 700 }}>
                        {[req.last_name, req.first_name, req.middle_name].filter(Boolean).join(' ') || req.username}
                      </div>
                      <div className="small muted" style={{ marginTop: 2 }}>
                        Логин: <strong>{req.username}</strong> · Email: <strong>{req.email}</strong>
                      </div>
                    </div>
                    <div>
                      {req.status === 'pending' && <span className="chip chip--sm chip--pending">Ожидает</span>}
                      {req.status === 'active' && <span className="chip chip--sm chip--brand">Активен</span>}
                      {req.status === 'rejected' && <span className="chip chip--sm chip--error">Отклонён</span>}
                      {req.status === 'blocked' && <span className="chip chip--sm chip--error">Заблокирован</span>}
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10, padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 8 }}>
                    <div>
                      <span className="small muted">Дата рождения:</span>{' '}
                      <span className="small strong">{dateRu(req.birth_date)}</span>
                    </div>
                    <div>
                      <span className="small muted">Город:</span>{' '}
                      <span className="small strong">{req.city || '—'}</span>
                    </div>
                    <div>
                      <span className="small muted">Подана:</span>{' '}
                      <span className="small strong">{dateTimeRu(req.created_at)}</span>
                    </div>
                    <div>
                      <span className="small muted">Роль:</span>{' '}
                      <span className="small strong">{req.role}</span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span className="small strong">Привязка к спортсмену:</span>
                      {req.candidate_athlete_name && (
                        <span className="chip chip--sm chip--muted">
                          Кандидат: <Link to={`/athletes-view/${req.candidate_athlete_id}`} target="_blank" style={{ color: 'var(--brand-text)', marginLeft: 4, textDecoration: 'underline' }}>{req.candidate_athlete_name}</Link> (ID: {req.candidate_athlete_id})
                        </span>
                      )}
                      {req.athlete_id && !req.candidate_athlete_name && (
                        <span className="chip chip--sm chip--brand">
                          Привязан: <Link to={`/athletes-view/${req.athlete_id}`} target="_blank" style={{ color: 'inherit', marginLeft: 4, textDecoration: 'underline' }}>ID {req.athlete_id}</Link>
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 10, alignItems: 'center' }}>
                      <label className="field" style={{ margin: 0 }}>
                        <span className="small muted">ID спортсмена:</span>
                        <input
                          type="number"
                          className="input input--sm"
                          placeholder="ID профиля"
                          value={initialAthInput}
                          onChange={(e) => setAthleteInputs({ ...athleteInputs, [req.id]: e.target.value })}
                          disabled={isBusy}
                        />
                      </label>
                      <label className="field" style={{ margin: 0 }}>
                        <span className="small muted">Комментарий модератора:</span>
                        <input
                          type="text"
                          className="input input--sm"
                          placeholder="Причина решения или заметка"
                          value={commentInputs[req.id] || ''}
                          onChange={(e) => setCommentInputs({ ...commentInputs, [req.id]: e.target.value })}
                          disabled={isBusy}
                        />
                      </label>
                    </div>
                  </div>

                  {curNotice && (
                    <div style={{
                      padding: '8px 12px',
                      borderRadius: 6,
                      fontSize: 13,
                      background: curNotice.isError ? 'var(--status-error-soft)' : 'var(--brand-soft)',
                      color: curNotice.isError ? 'var(--status-error)' : 'var(--status-counted)',
                    }}>
                      {curNotice.text}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 6 }}>
                    <button
                      type="button"
                      className="btn btn--sm btn--primary"
                      onClick={() => handleAccessDecision(req, 'approve')}
                      disabled={isBusy}
                    >
                      {req.status === 'active' ? 'Сохранить привязку' : 'Одобрить доступ'}
                    </button>
                    {req.status !== 'rejected' && (
                      <button
                        type="button"
                        className="btn btn--sm btn--ghost"
                        style={{ color: '#ef4444' }}
                        onClick={() => handleAccessDecision(req, 'reject')}
                        disabled={isBusy}
                      >
                        Отклонить
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )
      ) : (
        reportItems.length === 0 ? (
          <EmptyState
            title="Обращений не найдено"
            text="С выбранным статусом в системе нет обращений пользователей."
          />
        ) : (
          <div className="grid-cards" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {reportItems.map((rep) => {
              const key = `report-${rep.id}`;
              const isBusy = processingId === key;
              const curNotice = notice?.id === key ? notice : null;

              return (
                <div key={rep.id} className="card card--pad" style={{ background: 'var(--surface)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span className="chip chip--sm chip--brand">{REPORT_KINDS[rep.kind] || rep.kind}</span>
                        <span className="small muted">Заявка #{rep.id} · Автор ID: {rep.user_id}</span>
                      </div>
                      <div style={{ fontSize: 15, marginTop: 8, whiteSpace: 'pre-wrap' }}>
                        {rep.message}
                      </div>
                    </div>
                    <div>
                      {rep.status === 'new' && <span className="chip chip--sm chip--pending">Новая</span>}
                      {rep.status === 'accepted' && <span className="chip chip--sm chip--brand">Принята</span>}
                      {rep.status === 'resolved' && <span className="chip chip--sm chip--brand">Выполнена</span>}
                      {rep.status === 'rejected' && <span className="chip chip--sm chip--error">Отклонена</span>}
                    </div>
                  </div>

                  {(rep.athlete_id || rep.result_id || rep.event_id || rep.url) && (
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 8, fontSize: 13 }}>
                      {rep.athlete_id && (
                        <span>
                          Спортсмен: <Link to={`/athletes-view/${rep.athlete_id}`} target="_blank" style={{ color: 'var(--brand-text)', textDecoration: 'underline' }}>ID {rep.athlete_id}</Link>
                        </span>
                      )}
                      {rep.result_id && <span>Результат ID: {rep.result_id}</span>}
                      {rep.event_id && (
                        <span>
                          Старт: <Link to={`/events-view/${rep.event_id}`} target="_blank" style={{ color: 'var(--brand-text)', textDecoration: 'underline' }}>ID {rep.event_id}</Link>
                        </span>
                      )}
                      {rep.url && (
                        <span>
                          Ссылка: <a href={rep.url} target="_blank" rel="noreferrer" style={{ color: 'var(--brand-text)', textDecoration: 'underline' }}>{rep.url}</a>
                        </span>
                      )}
                    </div>
                  )}

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <label className="field" style={{ margin: 0 }}>
                      <span className="small muted">Комментарий модератора:</span>
                      <input
                        type="text"
                        className="input input--sm"
                        placeholder="Ответ пользователю или примечание"
                        defaultValue={rep.moderator_comment || ''}
                        onChange={(e) => setCommentInputs({ ...commentInputs, [rep.id]: e.target.value })}
                        disabled={isBusy}
                      />
                    </label>
                  </div>

                  {curNotice && (
                    <div style={{
                      padding: '8px 12px',
                      borderRadius: 6,
                      fontSize: 13,
                      background: curNotice.isError ? 'var(--status-error-soft)' : 'var(--brand-soft)',
                      color: curNotice.isError ? 'var(--status-error)' : 'var(--status-counted)',
                    }}>
                      {curNotice.text}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 4 }}>
                    <button
                      type="button"
                      className="btn btn--sm btn--primary"
                      onClick={() => handleReportDecision(rep, 'accepted')}
                      disabled={isBusy}
                    >
                      Принять
                    </button>
                    <button
                      type="button"
                      className="btn btn--sm btn--primary"
                      onClick={() => handleReportDecision(rep, 'resolved')}
                      disabled={isBusy}
                    >
                      Выполнить
                    </button>
                    <button
                      type="button"
                      className="btn btn--sm btn--ghost"
                      style={{ color: '#ef4444' }}
                      onClick={() => handleReportDecision(rep, 'rejected')}
                      disabled={isBusy}
                    >
                      Отклонить
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )
      )}
    </>
  );
}