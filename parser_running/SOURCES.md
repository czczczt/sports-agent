# Беговые источники: разведка (2026-10-20)

| # | Источник | Доступ | Формат | Что видно | Решение |
|---|---|---|---|---|---|
| 1 | probeg.org | ✅ | HTML (сервер) | Агрегатор: `/event/N/`, база бегунов `/klb/person/N/`, `/runners/` | **Второй источник**: много стартов + ID людей |
| 2 | results.russiarunning.com | ✅ | **JSON API** (платформа RR) | ~2345 событий; в протоколе ФИО, пол, **возраст**, город, регион, клуб, **чистое и грязное время** | **Первый источник** |
| 3 | toplist.run | ✅ curl / ❌ браузер | SPA | API в бандле не найден | Отложить |
| 4 | results.zone | ✅ | HTML (Rails) | Список стартов на главной; бег, плавание, вело | Позже |
| 5 | results.runc.run | ✅ (не с TR-IP) | HTML (сервер) | Протокол: `/event/<код>/finishers/distance/<id>/page/N/page_size/1000/`, вариант `common/` — грязное время. Есть пол и возраст, **нет клуба** | ✅ Коннектор `runc.py` |
| 6 | dustydumbbells.com | ⚠️ | HTML | Главная открылась, `/api` — таймаут | Проверить, есть ли зачётные дистанции |
| 7 | grom.place | ✅ (не с TR-IP) | HTML + JSON в атрибуте `:initial-rows` | Данные RaceResult: год рождения, клуб, чистое и грязное время, места. Сайт медленный (E29) | ✅ Коннектор `grom.py` |
| 8 | myrunstats.ru | ✅ | SPA, `/api/v1` | Агрегатор статистики | Позже |
| 9 | skisport.ru/protocols | ✅ | HTML | Протоколы, в основном лыжи | Позже |
| 10 | myfinish.info | ⚠️ список ✅, протоколы ❌ | SPA (Angular) + JSON | `/php/ajax_gate.php?do=compUsrList&year=YYYY` → 6546 соревнований. Протоколы на `new.myfinish.info/<id>` — гео-блок (E19) | Ждём разведку из РФ |
| 11 | results.racetime.online | ✅ | HTML (ASP.NET) | Старты по коду (`/HuaweiAutumnRace…`) | Позже |
| 12 | timerman.org/results | ✅ | **JSON API — та же платформа RR** | Те же эндпоинты, что у russiarunning | Тот же коннектор |
| 13 | heroleague.ru/results | ✅ | SPA, `/api/event_results/…` | «Гонка Героев» — бег с препятствиями | Вопрос заказчику: считать ли бегом |

## Платформа RussiaRunning (RR) — один коннектор на 4 площадки
Те же эндпоинты отвечают на:
`results.russiarunning.com/api`, `timerman.org/results/api`, а также лыжные
`results.legkovrace.ru/api`, `results.pionercup.ru/api`.

| Эндпоинт | Тело / параметры | Ответ |
|---|---|---|
| `POST /events/list` | `{"page": {"skip", "take"}, "language": "ru"}` | `list[]`: id, code, title, beginDate, place, address, `disciplineCode` (`run`, …) |
| `POST /events/get` | `{"eventCode": …, "language": "ru"}` | событие + `races[]`: id, code, name, **`distance` (км)**, disciplineCode |
| `GET /results/options/get` | `RaceId`, `Language` | `isFinalProtocol`, отметки, какие колонки скрыты |
| `POST /results/individual/get` | `{"eventId", "raceId", "page": {"skip", "take" ≤ 100}, "filter": {}, "isStagesOn": false, "language": "ru"}`; `search` не передавать | `results[]` + `totalCount` |
| `POST /results/relay/get` | то же | эстафеты |

Поля результата: `fullName`, `gender`, `age`, `countryCode`, `region`, `city`, `raceClub`,
`number`, `position`, `individualResult` (чистое), `absoluteResult` (грязное), `status`,
позиции в поле/группе, сплиты.
**Даты рождения нет — только возраст.**
