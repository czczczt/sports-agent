"""
Автономно сгенерированный тестовый скрипт для probeg.org.
Сгенерирован моделью GigaChat-2-Pro.
Запуск:
    python test_probeg_parser.py
"""
import urllib.request
from bs4 import BeautifulSoup

URL = "https://probeg.org/race/129181/"

from bs4 import BeautifulSoup


class ProbegConnector:
    def parse_results(self, html):
        # Парсим HTML-документ
        soup = BeautifulSoup(html, 'html.parser')
        
        # Находим таблицу результатов
        table = soup.find('table', class_='results-t') or soup.find('table')
        
        participants = []
        
        # Проходимся по строкам таблицы (пропускаем заголовок)
        for row in table.find_all('tr'):
            # Пропускаем строки с заголовками колонок
            if any(cell.name == 'th' for cell in row.find_all()):
                continue
            
            # Получаем ячейки строки
            cells = row.find_all('td')
            
            # Проверяем корректность количества ячеек
            if not cells or len(cells) < 5:
                continue
            
            # Извлекаем нужные поля участнику
            place = cells[0].get_text(strip=True)
            name = [p.strip() for p in cells[1].get_text().split('\n') if p.strip()][0]
            bib = cells[2].get_text(strip=True) if len(cells) > 2 else None
            city = cells[3].get_text(strip=True) if len(cells) > 3 else None
            time = cells[4].get_text(strip=True) if len(cells) > 4 else None
            
            # Добавляем участника в результат
            participants.append({
                "place": place,
                "name": name,
                "bib": bib,
                "city": city,
                "time": time
            })
        
        return participants

if __name__ == "__main__":
    print(f"Тестируем парсер для {URL}...")
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    connector = ProbegConnector()
    results = connector.parse_results(html)
    print(f"Успешно извлечено финишеров: {len(results)}")
    for r in results[:5]:
        print(" ", r)
