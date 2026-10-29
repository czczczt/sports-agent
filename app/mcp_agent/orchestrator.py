"""
Оркестратор конвейера сбора с ИИ-агентом:
1. Запускает стандартный детерминированный парсер.
2. Прогоняет тесты качества данных (проверка на NULL, порядок мест, времена).
3. Если тесты падают -> автоматически логирует issue и запускает fallback-парсинг через MCP.
"""
import hashlib
import sqlite3
import logging
from typing import Dict, Any, List, Optional
from app.db import get_db_connection
from app.mcp_agent.validator import validate_protocol_data, ValidationReport
from app.mcp_agent.mcp_client import MCPAgentClientStub

logger = logging.getLogger("mcp_agent")


def make_fingerprint(stage: str, kind: str, object_ref: str) -> str:
    """Генерирует стабильный ключ ошибки для дедупликации в таблице issue."""
    raw = f"{stage}:{kind}:{object_ref}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def report_quality_issue(
    conn: sqlite3.Connection,
    source_id: Optional[int],
    stage: str,
    kind: str,
    object_ref: str,
    details: str
) -> int:
    """Записывает обнаруженную проблему в таблицу issue базы данных."""
    cur = conn.cursor()
    fp = make_fingerprint(stage, kind, object_ref)
    
    cur.execute("""
        INSERT INTO issue (source_id, stage, kind, object_ref, fingerprint, details, status, assignee, occurrences)
        VALUES (?, ?, ?, ?, ?, ?, 'agent_working', 'agent', 1)
        ON CONFLICT(fingerprint) DO UPDATE SET
            occurrences = occurrences + 1,
            last_seen = CURRENT_TIMESTAMP,
            details = excluded.details,
            status = 'agent_working'
    """, (source_id, stage, kind, object_ref, fp, details))
    conn.commit()

    row = cur.execute("SELECT id FROM issue WHERE fingerprint = ?", (fp,)).fetchone()
    return row["id"] if row else 0


class ParsingAgentOrchestrator:
    """
    Оркестратор: управляет запуском парсеров, валидацией данных и вызовом ИИ-агента через MCP.
    """

    def __init__(self, mcp_client: Optional[MCPAgentClientStub] = None):
        self.mcp_client = mcp_client or MCPAgentClientStub()

    async def run_pipeline_with_ai_fallback(
        self,
        source_name: str,
        race_url: str,
        parsed_rows: List[Dict[str, Any]],
        race_info: Optional[Dict[str, Any]] = None,
        source_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Основной цикл конвейера:
        1. Валидация спарсенных строк (тесты на NULL, монотонность, полноту).
        2. Если всё корректно -> завершение с успехом.
        3. Если данные кривые -> вызов ИИ-агента по MCP для повторного извлечения.
        """
        # Шаг 1: Тесты качества данных
        report = validate_protocol_data(parsed_rows, race_info=race_info)

        if report.is_valid:
            logger.info(f"[Orchestrator] Данные дистанции {race_url} успешно прошли все тесты качества. Строк: {report.total_rows}.")
            return {
                "success": True,
                "fallback_triggered": False,
                "rows_count": report.total_rows,
                "fin_count": report.fin_rows,
                "issues": []
            }

        # Шаг 2: Тесты провалены (кривые данные, NULL)
        error_summary = "; ".join(report.issues)
        logger.warning(f"[Orchestrator] Тесты качества провалены для {race_url}. Причина: {error_summary}")

        # Фиксируем инцидент в БД issue
        conn = get_db_connection()
        try:
            issue_id = report_quality_issue(
                conn=conn,
                source_id=source_id,
                stage="check",
                kind="data_quality_failed",
                object_ref=race_url,
                details=f"Что: Нарушение качества данных. Причина: {error_summary}. Сделано: Передано ИИ-агенту MCP."
            )
        finally:
            conn.close()

        # Шаг 3: Запуск fallback-парсинга с помощью ИИ по MCP
        expected_schema = {
            "fields": [
                {"name": "bib", "type": "integer"},
                {"name": "full_name_raw", "type": "string", "required": True},
                {"name": "chip_time_s", "type": "float"},
                {"name": "gun_time_s", "type": "float"},
                {"name": "place_abs", "type": "integer"},
                {"name": "status", "type": "string", "enum": ["FIN", "DNF", "DSQ", "DNS"]}
            ]
        }

        mcp_result = await self.mcp_client.fallback_parse_race(
            source_url=race_url,
            reason=error_summary,
            expected_schema=expected_schema
        )

        return {
            "success": False,
            "fallback_triggered": True,
            "issue_id": issue_id,
            "issues": report.issues,
            "null_ratios": report.null_ratios,
            "mcp_agent_status": "ai_mcp_fallback_executed",
            "mcp_extracted_rows_count": len(mcp_result)
        }
