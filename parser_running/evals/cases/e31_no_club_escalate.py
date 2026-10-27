"""E31 (передать человеку): у runc в протоколах нет клуба — сотрудников Сбера по клубу не найти.
Это вопрос правил (решает заказчик через руководителя), а не парсера."""
from protocol import Task

META = {"id": "E31", "title": "нет поля клуба — нужно решение заказчика", "expected": "escalate:human"}
ORACLE = {"action": "escalate", "to": "human",
          "reason": "площадка не публикует клуб; нужен список сотрудников или поиск по ФИО известных спортсменов"}


def task() -> Task:
    return Task("E31", "runc", "match", "missing_field", "results.runc.run",
                {"field": "club", "share_filled": 0.0, "rows": 94851,
                 "note": "на runc проходит «СберПрайм Московский Марафон», а признак сотрудника — клуб Сбера"})
