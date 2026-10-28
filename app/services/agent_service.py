import json
import uuid
import sqlite3
import httpx
from typing import Dict, Any, Tuple
from app.config import (
    GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE, GIGACHAT_MODEL, GIGACHAT_VERIFY_SSL
)
from app.services.analytics_service import compute_athlete_metrics
from app.models import AssessmentResponse


SYSTEM_PROMPT = """Ты профессиональный спортивный аналитик беговой платформы Сбера.
Твоя задача — составить персональную оценку результатов спортсмена на основе предоставленных числовых метрик.

ПРАВИЛА:
1. Используй ТОЛЬКО числа, времена, процентили и факты из входных данных. НИЧЕГО НЕ ПРИДУМЫВАЙ.
2. Структурируй ответ по разделам:
   - 🎯 Общий уровень и соревновательный статус (на основе процентилей)
   - 📈 Прогресс и динамика по дистанциям (личные рекорды, изменение времени)
   - ⚡ Стабильность темпа
   - 💪 Сильные стороны
   - 🔍 Точки роста и рекомендации
3. Тон доброжелательный, конструктивный и мотивирующий.
4. В конце обязательно отметь, что оценка носит справочный характер."""


async def get_gigachat_token(credentials: str, scope: str, verify_ssl: bool) -> str:
    """Получает OAuth access-токен GigaChat."""
    oauth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Authorization": f"Basic {credentials.strip()}",
        "RqUID": str(uuid.uuid4()),
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"scope": scope}

    async with httpx.AsyncClient(verify=verify_ssl, timeout=15.0) as client:
        resp = await client.post(oauth_url, headers=headers, data=data)
        resp.raise_for_status()
        token_data = resp.json()
        return token_data.get("access_token", "")


async def call_gigachat_chat(token: str, model: str, user_content: str, verify_ssl: bool) -> str:
    """Вызывает метод chat/completions GigaChat."""
    chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.5,
        "max_tokens": 1500
    }

    async with httpx.AsyncClient(verify=verify_ssl, timeout=30.0) as client:
        resp = await client.post(chat_url, headers=headers, json=payload)
        resp.raise_for_status()
        res_json = resp.json()
        choices = res_json.get("choices", [])
        if choices and "message" in choices[0]:
            return choices[0]["message"]["content"]
        return "Не удалось сформировать текст ответа от GigaChat."


def generate_local_expert_assessment(metrics: Dict[str, Any]) -> str:
    """
    Генерирует структурированную экспертную оценку на основе вычисленных бэкендом метрик,
    если токен GigaChat не настроен в .env.
    """
    name = metrics.get("athlete_name", "Спортсмен")
    starts = metrics.get("total_starts", 0)
    pbs = metrics.get("personal_bests", [])
    avg_pct = metrics.get("average_percentile")
    best_pct = metrics.get("best_percentile")
    stability = metrics.get("stability", {})
    progress = metrics.get("progress_by_distance", [])
    strengths = metrics.get("strengths", [])
    weaknesses = metrics.get("weaknesses", [])

    lines = [
        f"### Персональная оценка результатов: {name}\n",
        f"**Всего стартов в протоколах:** {starts}\n",
        "#### 🎯 Соревновательный статус",
    ]

    if avg_pct is not None:
        lines.append(
            f"Средний процентиль среди участников: **{avg_pct}%** (в среднем финиширует в топ **{round(100 - avg_pct)}%** протоколов)."
        )
        if best_pct is not None:
            lines.append(f"Лучший результат относительно пелотона: обгон **{best_pct}%** участников забега.")
    else:
        lines.append("Недостаточно завершенных финишей для расчета процентилей.")

    lines.append("\n#### 🏆 Личные рекорды (PB)")
    if pbs:
        for pb in pbs:
            lines.append(f"- **{pb['distance_name']}**: {pb['time_formatted']} ({pb['pace_formatted']}) на «{pb['event_title']}»")
    else:
        lines.append("Личные рекорды на зачетных дистанциях пока не зафиксированы.")

    lines.append("\n#### 📈 Динамика и прогресс по дистанциям")
    if progress:
        for prg in progress:
            trend_icon = "🟢" if prg["trend"] == "улучшение" else ("🔴" if prg["trend"] == "спад" else "⚪")
            lines.append(
                f"- {trend_icon} **{prg['distance']}** ({prg['starts_count']} старта): "
                f"первый результат {prg['first_time']} ({prg['first_date']}), крайний {prg['latest_time']} ({prg['latest_date']}). "
                f"Динамика: **{prg['trend']}** ({'+' if prg['improvement_pct'] > 0 else ''}{prg['improvement_pct']}%)."
            )
    else:
        lines.append("Для анализа прогресса требуется минимум 2 старта на одной и той же дистанции.")

    lines.append("\n#### ⚡ Стабильность темпа")
    lines.append(f"Показатель стабильности: **{stability.get('status', 'не определено')}**.")
    if stability.get("description"):
        lines.append(f"{stability['description']}.")

    lines.append("\n#### 💪 Сильные стороны")
    if strengths:
        for s in strengths:
            lines.append(f"- {s}")
    else:
        lines.append("- Регулярное участие в соревнованиях.")

    lines.append("\n#### 🔍 Точки роста и рекомендации")
    if weaknesses:
        for w in weaknesses:
            lines.append(f"- {w}")
    else:
        lines.append("- Рекомендуется продолжать тренировочный план и закрепить результаты на целевых дистанциях.")

    lines.append("\n---\n*Примечание: Данная оценка носит исключительно справочный характер.*")
    return "\n".join(lines)


async def get_or_generate_assessment(
    conn: sqlite3.Connection,
    athlete_id: int
) -> AssessmentResponse:
    """
    Возвращает оценку спортсмена:
    1. Проверяет кэш.
    2. Если в кэше нет — рассчитывает метрики, вызывает GigaChat (или fallback), кэширует результат.
    """
    cur = conn.cursor()

    # 1. Проверяем кэш
    cached_row = cur.execute("""
        SELECT assessment_text, metrics_json, model
        FROM athlete_assessment_cache
        WHERE athlete_id = ?
    """, (athlete_id,)).fetchone()

    if cached_row:
        metrics = json.loads(cached_row["metrics_json"])
        athlete_name = metrics.get("athlete_name", f"Атлет #{athlete_id}")
        return AssessmentResponse(
            athlete_id=athlete_id,
            athlete_name=athlete_name,
            assessment_text=cached_row["assessment_text"],
            metrics=metrics,
            model=cached_row["model"],
            cached=True
        )

    # 2. Расчет метрик на бэкенде
    metrics = compute_athlete_metrics(conn, athlete_id)
    athlete_name = metrics.get("athlete_name", f"Атлет #{athlete_id}")
    used_model = "local-analytics-engine"
    assessment_text = ""

    # Пробуем GigaChat, если задан GIGACHAT_CREDENTIALS в .env
    if GIGACHAT_CREDENTIALS and GIGACHAT_CREDENTIALS.strip() and GIGACHAT_CREDENTIALS != "change-me":
        try:
            token = await get_gigachat_token(GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE, GIGACHAT_VERIFY_SSL)
            user_msg = f"Вот числовые метрики спортсмена {athlete_name}:\n" + json.dumps(metrics, ensure_ascii=False, indent=2)
            assessment_text = await call_gigachat_chat(token, GIGACHAT_MODEL, user_msg, GIGACHAT_VERIFY_SSL)
            used_model = f"GigaChat ({GIGACHAT_MODEL})"
        except Exception as exc:
            # Fallback на структурированный генератор при ошибке сети/авторизации
            assessment_text = generate_local_expert_assessment(metrics)
            assessment_text += f"\n\n*(Запрос к GigaChat не удался: {str(exc)}. Использована встроенная аналитическая модель.)*"
            used_model = "local-analytics-fallback"
    else:
        # Токен не задан: используем локальную аналитическую генерацию
        assessment_text = generate_local_expert_assessment(metrics)
        used_model = "local-analytics-engine (укажите GIGACHAT_CREDENTIALS в .env для GigaChat)"

    # 3. Сохраняем в кэш
    metrics_json = json.dumps(metrics, ensure_ascii=False)
    cur.execute("""
        INSERT OR REPLACE INTO athlete_assessment_cache (athlete_id, assessment_text, metrics_json, model)
        VALUES (?, ?, ?, ?)
    """, (athlete_id, assessment_text, metrics_json, used_model))
    conn.commit()

    return AssessmentResponse(
        athlete_id=athlete_id,
        athlete_name=athlete_name,
        assessment_text=assessment_text,
        metrics=metrics,
        model=used_model,
        cached=False
    )
