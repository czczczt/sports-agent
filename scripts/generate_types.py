"""Export the FastAPI contract and regenerate the frontend client types."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402

FRONTEND_DIR = ROOT_DIR / "frontend"
OPENAPI_JSON = FRONTEND_DIR / "openapi.json"


def generate_types(check: bool = False) -> None:
    spec_json = json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"
    if check:
        if not OPENAPI_JSON.is_file() or OPENAPI_JSON.read_text(encoding="utf-8") != spec_json:
            sys.exit("OpenAPI contract drift detected. Run 'python scripts/generate_types.py'.")
        print("OpenAPI contract check passed.")
        return

    OPENAPI_JSON.write_text(spec_json, encoding="utf-8", newline="\n")
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise RuntimeError("npm is required to generate API types")
    subprocess.run([npm, "run", "gen:api"], cwd=FRONTEND_DIR, check=True)


if __name__ == "__main__":
    generate_types(check="--check" in sys.argv)
