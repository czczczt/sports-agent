"""Automatic TypeScript types generation script per SPEC v1.3 §4.1.

Exports FastAPI OpenAPI specification and invokes openapi-typescript to update
frontend/src/api/schema.d.ts.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402

FRONTEND_DIR = ROOT_DIR / "frontend"
OPENAPI_JSON = FRONTEND_DIR / "openapi.json"
TARGET_DTS = FRONTEND_DIR / "src" / "api" / "schema.d.ts"


def generate_types(check: bool = False) -> None:
    print("[TYPEGEN] Exporting OpenAPI schema from FastAPI...")
    openapi_spec = app.openapi()
    spec_json = json.dumps(openapi_spec, indent=2, ensure_ascii=False) + "\n"

    if check:
        if not OPENAPI_JSON.exists():
            print(f"[TYPEGEN] ERROR: {OPENAPI_JSON} does not exist. Run generate_types.py first.", file=sys.stderr)
            sys.exit(1)
        existing_spec = OPENAPI_JSON.read_text(encoding="utf-8")
        # Normalize line endings
        if existing_spec.replace("\r\n", "\n").strip() != spec_json.replace("\r\n", "\n").strip():
            print(
                "[TYPEGEN] ERROR: OpenAPI contract drift detected between FastAPI backend and frontend/openapi.json!\n"
                "Run 'python scripts/generate_types.py' or 'npm --prefix frontend run gen:api' to synchronize.",
                file=sys.stderr,
            )
            sys.exit(1)
        print("[TYPEGEN] OpenAPI contract check passed: no drift detected.")
        return

    print(f"[TYPEGEN] Writing OpenAPI schema to {OPENAPI_JSON}...")
    OPENAPI_JSON.write_text(spec_json, encoding="utf-8")
    print(f"[TYPEGEN] OpenAPI schema exported successfully ({len(openapi_spec.get('paths', {}))} paths).")

    print(f"[TYPEGEN] Compiling TypeScript types into {TARGET_DTS} via openapi-typescript...")
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
    check_mode = "--check" in sys.argv
    generate_types(check=check_mode)
