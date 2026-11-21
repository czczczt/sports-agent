"""Раздача собранного React-интерфейса (frontend/dist) из FastAPI.

Сборка: `npm --prefix frontend run build` → frontend/dist (index.html + assets/).
Все URL, которые не заняты API, отдают index.html — дальше маршрутизирует React Router.
Решение описано в docs/adr/0002-react-frontend.md.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

PROJECT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", PROJECT_DIR / "frontend" / "dist")).resolve()

# Префиксы JSON API: для них нельзя отдавать index.html, иначе опечатка в адресе
# вернёт HTML вместо понятной 404.
API_PREFIXES = ("api/", "docs", "redoc", "openapi.json")

_NOT_BUILT = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Интерфейс не собран</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 640px; margin: 48px auto; line-height: 1.5;">
<h1>Интерфейс не собран</h1>
<p>Не найден <code>frontend/dist/index.html</code>. Соберите React-приложение:</p>
<pre>npm --prefix frontend install
npm --prefix frontend run build</pre>
<p>Или запустите dev-сервер: <code>npm --prefix frontend run dev</code> → http://localhost:5173.</p>
<p>API работает: <a href="/docs">/docs</a>.</p>
</body></html>"""


def mount_frontend(app: FastAPI) -> None:
    """Подключает статику сборки и SPA-fallback. Вызывать последним — после всех роутеров API."""
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        # Имена файлов в assets/ содержат хэш — их можно кэшировать надолго.
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")

        # Файлы из корня сборки (favicon и т. п.), без выхода за пределы dist.
        if full_path:
            candidate = (FRONTEND_DIST / full_path).resolve()
            if candidate.is_file() and FRONTEND_DIST in candidate.parents:
                return FileResponse(candidate)

        index = FRONTEND_DIST / "index.html"
        if not index.is_file():
            return HTMLResponse(_NOT_BUILT, status_code=503)
        # index.html не кэшируем: после пересборки браузер должен получить новые ссылки на assets.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
