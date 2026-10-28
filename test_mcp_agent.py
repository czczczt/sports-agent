"""
Тесты для заготовки ИИ-агента с fallback-парсингом по протоколу MCP.
"""
import asyncio
import unittest
from app.mcp_agent.validator import validate_protocol_data
from app.mcp_agent.mcp_client import MCPAgentClientStub
from app.mcp_agent.orchestrator import ParsingAgentOrchestrator
from app.db import get_db_connection


class TestMCPAgentFallback(unittest.TestCase):

    def test_01_valid_data_passes(self):
        """1. Корректные спарсенные данные проходят проверку без запуска агента."""
        valid_rows = [
            {"bib": 101, "full_name_raw": "Иванов Иван", "chip_time_s": 1200.0, "gun_time_s": 1205.0, "place_abs": 1, "status": "FIN"},
            {"bib": 102, "full_name_raw": "Петров Петр", "chip_time_s": 1250.0, "gun_time_s": 1255.0, "place_abs": 2, "status": "FIN"},
            {"bib": 103, "full_name_raw": "Сидоров Сидор", "chip_time_s": 1300.0, "gun_time_s": 1305.0, "place_abs": 3, "status": "FIN"}
        ]
        report = validate_protocol_data(valid_rows)
        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.issues), 0)

    def test_02_corrupted_data_with_nulls_fails(self):
        """2. Данные с высокой долей NULL и битыми временами вызывают ошибку валидации."""
        corrupted_rows = [
            {"bib": 101, "full_name_raw": None, "chip_time_s": None, "gun_time_s": None, "place_abs": 1, "status": "FIN"},
            {"bib": 102, "full_name_raw": "", "chip_time_s": None, "gun_time_s": None, "place_abs": 2, "status": "FIN"},
            {"bib": 103, "full_name_raw": "Сидоров Сидор", "chip_time_s": 1300.0, "gun_time_s": 1305.0, "place_abs": 3, "status": "FIN"}
        ]
        report = validate_protocol_data(corrupted_rows)
        self.assertFalse(report.is_valid)
        self.assertTrue(any("high_null_names" in issue for issue in report.issues))
        self.assertTrue(any("high_null_times" in issue for issue in report.issues))

    def test_03_orchestrator_triggers_mcp_fallback(self):
        """3. Оркестратор при провале тестов запускает ИИ-агента через MCP и логирует issue."""
        mcp_client = MCPAgentClientStub()
        orchestrator = ParsingAgentOrchestrator(mcp_client=mcp_client)

        corrupted_rows = [
            {"bib": 1, "full_name_raw": None, "chip_time_s": None, "gun_time_s": None, "place_abs": 1, "status": "FIN"},
            {"bib": 2, "full_name_raw": "Тест", "chip_time_s": None, "gun_time_s": None, "place_abs": 2, "status": "FIN"}
        ]

        async def run():
            return await orchestrator.run_pipeline_with_ai_fallback(
                source_name="russiarunning",
                race_url="https://results.russiarunning.com/event/test_123/race/1",
                parsed_rows=corrupted_rows,
                source_id=1
            )

        result = asyncio.run(run())

        self.assertFalse(result["success"])
        self.assertTrue(result["fallback_triggered"])
        self.assertIn("issue_id", result)
        self.assertEqual(result["mcp_agent_status"], "ai_mcp_fallback_executed")

        # Проверяем, что в MCP клиент поступил вызов инструментов
        self.assertTrue(any(call["tool"] == "playwright_fetch_page" for call in mcp_client.call_history))
        self.assertTrue(any(call["tool"] == "llm_extract_table" for call in mcp_client.call_history))

        # Проверяем запись в таблице issue в базе
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM issue WHERE id = ?", (result["issue_id"],)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["stage"], "check")
        self.assertEqual(row["assignee"], "agent")
        self.assertEqual(row["status"], "agent_working")


if __name__ == "__main__":
    unittest.main()
