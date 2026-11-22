import re
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"
APP_DIR = Path(__file__).resolve().parent.parent / "app"

BANNED_PATTERNS = [
    re.compile(r"подразделен", re.IGNORECASE),
    re.compile(r"общий пароль", re.IGNORECASE),
    re.compile(r"пьедестал", re.IGNORECASE),
]

def test_no_banned_terms_in_frontend_and_app():
    """Проверяет, что нет упоминаний 'подразделение', 'общий пароль', 'пьедестал' в frontend/src и app."""
    violations = []
    for base_dir in [FRONTEND_SRC, APP_DIR]:
        for file_path in base_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".py", ".html", ".css"}:
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in BANNED_PATTERNS:
                matches = pattern.findall(text)
                if matches:
                    violations.append(f"{file_path}: found {matches}")
    assert not violations, "Banned terms found:\n" + "\n".join(violations)

def test_rating_formula_view_content():
    """Проверяет наличие вкладок 4 видов спорта и точных обозначений легенды (T, Tл, Tмед, Bmed, K, Rmax, D+, N)."""
    formula_view = FRONTEND_SRC / "features" / "rating-formula" / "RatingFormulaView.tsx"
    assert formula_view.is_file(), "RatingFormulaView.tsx not found"
    content = formula_view.read_text(encoding="utf-8")

    # Sport tabs
    assert "'run', 'Бег'" in content
    assert "'ski', 'Лыжи и биатлон'" in content
    assert "'triathlon', 'Триатлон'" in content
    assert "'trail', 'Трейл'" in content

    # Legend symbols: T, Tл, Tмед, Bmed, K, Rmax, D+, N
    required_symbols = ["T", "Tл", "Tмед", "Bmed", "K", "Rmax", "D+", "N"]
    for sym in required_symbols:
        assert f">{sym}</span>" in content, f"Symbol {sym} not found in legend items"

def test_api_rating_formula_returns_norms(client, auth_headers):
    """Проверяет, что эндпоинт GET /api/rating/formula возвращает нормативы бега 2026."""
    headers = auth_headers("user")
    resp = client.get("/api/rating/formula", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["year"] == 2026
    assert len(data["norms"]) > 0
    distance_classes = {norm["distance_class"] for norm in data["norms"]}
    assert "10k" in distance_classes
