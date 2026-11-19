"""Automatic TypeScript types generation script per SPEC v1.3 §4.1.

Exports FastAPI OpenAPI specification and invokes openapi-typescript to update
frontend/src/api/schema.d.ts.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys

from app.main import app

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
OPENAPI_JSON = FRONTEND_DIR / "openapi.json"
TARGET_DTS = FRONTEND_DIR / "src" / "api" / "schema.d.ts"


def generate_types() -> None:
    print(f"[TYPEGEN] Exporting OpenAPI schema from FastAPI to {OPENAPI_JSON}...")
    openapi_spec = app.openapi()
    with open(OPENAPI_JSON, "w", encoding="utf-8") as f:
        json.dump(openapi_spec, f, indent=2, ensure_ascii=False)
    print(f"[TYPEGEN] OpenAPI schema exported successfully ({len(openapi_spec.get('paths', {}))} paths).")

    print(f"[TYPEGEN] Compiling TypeScript types into {TARGET_DTS} via openapi-typescript...")
    npx_cmd = shutil.which("npx") or ("cmd /c npx" if sys.platform == "win32" else "npx")
    cmd = (
        ["cmd", "/c", "npx", "openapi-typescript", "openapi.json", "-o", "src/api/schema.d.ts"]
        if sys.platform == "win32"
        else ["npx", "openapi-typescript", "openapi.json", "-o", "src/api/schema.d.ts"]
    )

    res = subprocess.run(cmd, cwd=FRONTEND_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[TYPEGEN] Error running openapi-typescript: {res.stderr}", file=sys.stderr)
        sys.exit(res.returncode)

    print(f"[TYPEGEN] Successfully generated: {TARGET_DTS}")


if __name__ == "__main__":
    generate_types()
