import { ApiError } from '@/shared/api';
import { countLabel, dateRu, sportTitle } from '@/shared/lib';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { collectionApi, type CollectionBatch, type CollectionProtocol, type CollectionRace } from './api';
import styles from './AdminCollectionView.module.css';

const publicationStatus: Record<string, [string, 'pending' | 'error' | 'brand' | 'muted']> = {
  pending: ['Публикация ожидается', 'muted'],
  published: ['Опубликовано', 'brand'],
  failed: ['Ошибка публикации', 'error'],
};

function participants(count: number) {
  return countLabel(count, 'участник', 'участника', 'участников');
}

function distance(meters: number | null | undefined) {
  if (meters == null) return null;
  if (meters < 1_000) return `${meters.toLocaleString('ru-RU')} м`;
  return `${(meters / 1_000).toLocaleString('ru-RU')} км`;
}

function ProtocolVersion({
  protocol,
  label,
  preferred,
}: {
  protocol: CollectionProtocol;
  label: string;
  preferred: boolean;
}): React.JSX.Element {
  return (
    <div className={`${styles.panel} ${styles.protocolPanel}`}>
      <strong>{label}</strong>
      <p>{protocol.title}</p>
      <p className="small muted">
        {[protocol.date && dateRu(protocol.date), protocol.city].filter(Boolean).join(' · ')}
      </p>
      <p className="small">
        {[
          protocol.race_name,
          distance(protocol.distance_m),
          sportTitle(protocol.sport),
          protocol.relay && 'Эстафета',
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      <p className="small">
        {participants(protocol.participants)}
        {protocol.is_final === true && ' · Финальный протокол'}
        {protocol.is_final === false && ' · Предварительный протокол'}
      </p>
      {protocol.published && <span className="small">Уже опубликован</span>}
      {protocol.planned && <span className="small">Запланированный старт</span>}
      {preferred && <span className="small strong">Рекомендованный протокол</span>}
      {protocol.url && /^https?:\/\//i.test(protocol.url) && (
        <a href={protocol.url} target="_blank" rel="noreferrer">
          Протокол на {label}
        </a>
      )}
    </div>
  );
}

function RaceVersions({
  race,
  choice,
  disabled,
  sourceLabel,
  onChoice,
}: {
  race: CollectionRace;
  choice: string | undefined;
  disabled: boolean;
  sourceLabel: (source: string) => string;
  onChoice: (key: string | undefined) => void;
}): React.JSX.Element {
  const name = [race.label, distance(race.distance_m), sportTitle(race.sport), race.relay && 'Эстафета']
    .filter(Boolean)
    .join(' · ');
  const count = race.protocols.find(({ key }) => key === choice)?.participants ?? race.participants;
  const conflicted = Boolean(race.warning);
  const radioGroup = `protocol-${race.key}`;

  return (
    <li>
      <div className={styles.row}>
        <span className={styles.raceName}>{name}</span>
        <span className="small muted">{participants(count)}</span>
      </div>
      <details className={styles.protocols}>
        <summary className={conflicted ? styles.warning : undefined}>
          {conflicted ? 'Возможный дубль' : 'Исходные протоколы'}
          {conflicted &&
            race.protocols.some(({ published }) => published) &&
            ' · Есть опубликованный протокол'}
        </summary>
        {race.warning && <p className="small">{race.warning.replace(/^Возможный дубль: /, '')}</p>}
        <fieldset className={styles.sources} disabled={disabled}>
          {conflicted && <legend className="small strong">Какой протокол применить</legend>}
          <div className={styles.columns}>
            {race.protocols.map((protocol) => {
              const label = sourceLabel(protocol.source);
              return (
                <div key={protocol.key}>
                  <ProtocolVersion
                    protocol={protocol}
                    label={label}
                    preferred={protocol.key === race.preferred_protocol_key}
                  />
                  {conflicted && !protocol.planned && (
                    <label className={styles.choice}>
                      <input
                        type="radio"
                        name={radioGroup}
                        checked={choice === protocol.key}
                        onChange={() => onChoice(protocol.key)}
                      />
                      Выбрать {label} ({participants(protocol.participants)})
                    </label>
                  )}
                </div>
              );
            })}
          </div>
          {conflicted && (
            <label className={`${styles.choice} ${styles.codes}`}>
              <input
                type="radio"
                name={radioGroup}
                checked={choice === undefined}
                onChange={() => onChoice(undefined)}
              />
              Отложить решение
            </label>
          )}
        </fieldset>
      </details>
    </li>
  );
}

function reviewOptions(race: CollectionRace): string {
  return JSON.stringify(race.protocols);
}

export function CollectionPreview({
  batch,
  sourceLabel,
  onUpdate,
}: {
  batch: CollectionBatch;
  sourceLabel: (source: string) => string;
  onUpdate: () => Promise<void>;
}): React.JSX.Element {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [choices, setChoices] = useState<Record<string, { key: string; options: string } | undefined>>({});
  const choiceFor = (race: CollectionRace) => {
    const choice = choices[race.key];
    return choice && choice.options === reviewOptions(race) ? choice.key : undefined;
  };
  const canPublishRace = (race: CollectionRace) => !race.warning || choiceFor(race) !== undefined;
  const availableEvents = batch.events.filter(({ races }) => races.some(canPublishRace));
  const selectedEvents = availableEvents.filter(({ key }) => selected.has(key));
  const approve = useMutation({
    mutationFn: () =>
      collectionApi.approve(batch.id, {
        draft_ids: Array.from(new Set(selectedEvents.flatMap(({ draft_ids }) => draft_ids))),
        resolutions: selectedEvents.flatMap(({ races }) =>
          races.flatMap((race) => {
            const choice = choiceFor(race);
            return race.warning && choice ? [{ race_key: race.key, protocol_key: choice }] : [];
          }),
        ),
        preview_revision: batch.preview_revision,
      }),
    onSuccess: () => {
      setSelected(new Set());
      setChoices({});
      return onUpdate();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        setChoices({});
      }
      return onUpdate();
    },
  });
  const [statusLabel, statusTone] = publicationStatus[batch.publication_status] ?? [
    'Публикация ожидается',
    'muted',
  ];

  return (
    <section className={`card card--pad ${styles.stack}`} aria-labelledby="collection-preview">
      <div className={styles.row}>
        <h2 className="h2" id="collection-preview">
          Предпросмотр и публикация
        </h2>
        <span className={`chip chip--sm chip--${statusTone}`} role="status">
          {approve.isPending ? 'Публикуем…' : statusLabel}
        </span>
      </div>
      {batch.publication_error && (
        <p role="alert" className={styles.error}>
          {batch.publication_error}
        </p>
      )}
      {approve.error && (
        <p role="alert" className={styles.error}>
          {approve.error instanceof ApiError && approve.error.status === 409
            ? 'Предпросмотр изменился. Проверь версии протоколов и повтори утверждение.'
            : approve.error.message}
        </p>
      )}
      {approve.data && (
        <p className="small muted" role="status">
          Опубликованные дистанции: {approve.data.published_races}. Черновики, ожидающие решения:{' '}
          {approve.data.pending_draft_ids.length}.
        </p>
      )}
      {batch.events.length === 0 ? (
        <p className="muted">Нет черновиков для утверждения.</p>
      ) : (
        <>
          <ul className={styles.cleanList}>
            {batch.events.map((event) => {
              const available = event.races.some(canPublishRace);
              return (
                <li className={styles.panel} key={event.key}>
                  <div className={styles.row}>
                    <label className={styles.choice}>
                      <input
                        type="checkbox"
                        checked={available && selected.has(event.key)}
                        disabled={!available || approve.isPending}
                        onChange={({ target: { checked } }) => {
                          setSelected((previous) => {
                            const next = new Set(previous);
                            if (checked) next.add(event.key);
                            else next.delete(event.key);
                            return next;
                          });
                        }}
                      />
                      <strong>{event.title}</strong>
                    </label>
                    <span className="chip chip--sm chip--muted">
                      {event.is_new ? 'Новый старт' : 'Изменённый старт'}
                    </span>
                  </div>
                  <p className="small muted">
                    {[
                      event.date && dateRu(event.date),
                      event.city,
                      sourceLabel(event.source),
                      participants(event.participants),
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  <ul className={styles.cleanList}>
                    {event.races.map((race) => (
                      <RaceVersions
                        key={race.key}
                        race={race}
                        choice={choiceFor(race)}
                        disabled={approve.isPending}
                        sourceLabel={sourceLabel}
                        onChoice={(key) =>
                          setChoices((previous) => ({
                            ...previous,
                            [race.key]: key ? { key, options: reviewOptions(race) } : undefined,
                          }))
                        }
                      />
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
          <button
            type="button"
            className={`btn btn--primary ${styles.action}`}
            disabled={selectedEvents.length === 0 || approve.isPending}
            onClick={() => approve.mutate()}
          >
            Утвердить выбранное
          </button>
        </>
      )}
    </section>
  );
}
