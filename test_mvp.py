"""
Комплексный тест функционала MVP платформы бегового рейтинга.
Проверяет:
1. Поиск спортсмена (е/ё, регистр, допуск +-1 год).
2. Профиль спортсмена (результаты, личные рекорды, динамика, заглушка рейтинга).
3. Каталог стартов и дистанций (фильтры, протокол, блок 'конкуренция').
4. ИИ-агент (расчёт числовых метрик, кэширование, дисклеймер).
"""
import sys
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db_connection

client = TestClient(app)


class TestSportsAgentMVP(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = get_db_connection()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_01_athlete_search_case_and_yo(self):
        """1. Поиск спортсмена без учета регистра и с заменой е/ё."""
        # Ищем 'федоров' и 'фёдоров'
        resp1 = client.get("/athletes/search?last_name=федоров&limit=10")
        resp2 = client.get("/athletes/search?last_name=ФЁДОРОВ&limit=10")
        
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        data1 = resp1.json()
        data2 = resp2.json()
        
        self.assertGreater(len(data1), 0, "Должны быть найдены кандидаты по фамилии Федоров")
        self.assertEqual(len(data1), len(data2), "Результаты с 'е' и 'ё' должны быть эквивалентны")

    def test_02_athlete_search_with_birth_year_tolerance(self):
        """1. Поиск с годом рождения и допуском +- 1 год."""
        resp = client.get("/athletes/search?last_name=иванов&birth_year=1990&limit=50")
        self.assertEqual(resp.status_code, 200)
        candidates = resp.json()
        self.assertGreater(len(candidates), 0)
        
        for cand in candidates:
            if cand["birth_year"] is not None:
                # Допуск в 1 год: от 1989 до 1991
                self.assertTrue(1989 <= cand["birth_year"] <= 1991, 
                                f"Год {cand['birth_year']} выходит за пределы 1990 +- 1")

    def test_03_athlete_summary_and_profile(self):
        """2. Профиль спортсмена: личные рекорды, динамика, рейтинг."""
        # Находим спортсмена с несколькими стартами
        cand = client.get("/athletes/search?last_name=иванов&limit=1").json()[0]
        athlete_id = cand["id"]

        resp = client.get(f"/athletes/{athlete_id}/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        self.assertIn("athlete", data)
        self.assertIn("personal_bests", data)
        self.assertIn("dynamics", data)
        self.assertIn("rating", data)
        
        # Проверяем заглушку рейтинга
        rating = data["rating"]
        self.assertEqual(rating["status"], "pending_curator_formula")
        self.assertIn("согласовании", rating["message"])

        # Проверяем список результатов
        res_resp = client.get(f"/athletes/{athlete_id}/results")
        self.assertEqual(res_resp.status_code, 200)
        results = res_resp.json()
        self.assertIsInstance(results, list)
        if len(results) > 0:
            sample = results[0]
            self.assertIn("time_formatted", sample)
            self.assertIn("pace_formatted", sample)
            self.assertIn("place_abs", sample)

    def test_04_events_catalog_and_filters(self):
        """3. Каталог стартов с фильтрами по дате, городу и площадке."""
        # Все старты
        resp = client.get("/events?limit=10")
        self.assertEqual(resp.status_code, 200)
        events = resp.json()
        self.assertGreater(len(events), 0)

        # Фильтр по площадке
        resp_rr = client.get("/events?source=russiarunning&limit=10")
        self.assertEqual(resp_rr.status_code, 200)
        events_rr = resp_rr.json()
        for ev in events_rr:
            self.assertEqual(ev["source_name"], "russiarunning")

        # Детальная карточка старта
        event_id = events[0]["id"]
        resp_detail = client.get(f"/events/{event_id}")
        self.assertEqual(resp_detail.status_code, 200)
        self.assertEqual(resp_detail.json()["id"], event_id)

    def test_05_race_protocol_and_competition(self):
        """3. Протокол дистанции и блок 'Конкуренция'."""
        # Получаем первую дистанцию
        cur = self.conn.cursor()
        race_row = cur.execute("SELECT id FROM race WHERE total_count > 10 LIMIT 1").fetchone()
        self.assertIsNotNone(race_row)
        race_id = race_row["id"]

        # Протокол
        resp_proto = client.get(f"/races/{race_id}/results?limit=20")
        self.assertEqual(resp_proto.status_code, 200)
        results = resp_proto.json()
        self.assertGreater(len(results), 0)

        # Поиск в протоколе по bib
        sample_bib = results[0]["bib"]
        if sample_bib:
            resp_search = client.get(f"/races/{race_id}/results?search={sample_bib}")
            self.assertEqual(resp_search.status_code, 200)
            search_res = resp_search.json()
            self.assertTrue(any(r["bib"] == sample_bib for r in search_res))

        # Блок 'Конкуренция'
        resp_comp = client.get(f"/races/{race_id}/competition")
        self.assertEqual(resp_comp.status_code, 200)
        comp = resp_comp.json()
        self.assertIn("distribution_bins", comp)
        self.assertIn("median_time_s", comp)
        self.assertIn("p25_time_s", comp)
        self.assertEqual(len(comp["distribution_bins"]), 10, "Должно быть 10 интервалов гистограммы")

    def test_06_agent_assessment_and_caching(self):
        """4. ИИ-агент спортсмена: расчет числовых метрик, кэширование и дисклеймер."""
        # Ищем спортсмена с несколькими стартами
        cur = self.conn.cursor()
        athlete_row = cur.execute("SELECT id FROM athlete WHERE starts_count >= 2 LIMIT 1").fetchone()
        self.assertIsNotNone(athlete_row)
        athlete_id = athlete_row["id"]

        # Очищаем кэш для чистоты теста
        cur.execute("DELETE FROM athlete_assessment_cache WHERE athlete_id = ?", (athlete_id,))
        self.conn.commit()

        # 1-й вызов: генерация оценки
        resp1 = client.post(f"/athletes/{athlete_id}/assessment")
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        
        self.assertIn("assessment_text", data1)
        self.assertIn("metrics", data1)
        self.assertIn("disclaimer", data1)
        self.assertIn("справочный характер", data1["disclaimer"])
        self.assertFalse(data1["cached"], "Первый вызов не должен быть из кэша")
        
        # 2-й вызов: проверка кэширования
        resp2 = client.post(f"/athletes/{athlete_id}/assessment")
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2["cached"], "Повторный вызов должен возвращаться из кэша")
        self.assertEqual(data1["assessment_text"], data2["assessment_text"])

    def test_07_html_views(self):
        """Проверка рендеринга страниц чернового веб-интерфейса."""
        # Поиск
        resp_search = client.get("/")
        self.assertEqual(resp_search.status_code, 200)
        self.assertIn("СберСпорт", resp_search.text)

        # Каталог стартов
        resp_events = client.get("/events-view")
        self.assertEqual(resp_events.status_code, 200)
        self.assertIn("Каталог беговых стартов", resp_events.text)

        # Профиль первого спортсмена
        cur = self.conn.cursor()
        aid = cur.execute("SELECT id FROM athlete LIMIT 1").fetchone()["id"]
        resp_profile = client.get(f"/athletes-view/{aid}")
        self.assertEqual(resp_profile.status_code, 200)
        self.assertIn("Профиль спортсмена", resp_profile.text)


if __name__ == "__main__":
    unittest.main()
