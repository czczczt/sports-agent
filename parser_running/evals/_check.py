"""Запуск проверки кейса внутри песочницы, в отдельном процессе и без сети.

    python _check.py case <путь_к_кейсу.py> <песочница>   -> JSON {"ok": bool, "msg": str}
    python _check.py regression <песочница>
"""
import importlib.util
import json
import socket
import sys
import traceback
from pathlib import Path


def _no_network(*a, **k):
    raise OSError("сеть в песочнице отключена")


def main() -> None:
    mode, sandbox = sys.argv[1], Path(sys.argv[-1])
    sys.path.insert(0, str(sandbox))                 # модули парсера — из песочницы, с правками агента
    sys.path.insert(1, str(Path(__file__).parent))   # protocol.py, regression.py
    socket.socket.connect = _no_network              # агент не должен ходить в сеть при проверке
    socket.create_connection = _no_network
    try:
        if mode == "regression":
            import regression
            ok, msg = regression.run()
        else:
            spec = importlib.util.spec_from_file_location("case", sys.argv[2])
            case = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(case)
            ok, msg = case.check(sandbox)
    except Exception:  # noqa: BLE001 — любое падение = провал проверки
        ok, msg = False, traceback.format_exc(limit=3)[-600:]
    print(json.dumps({"ok": bool(ok), "msg": str(msg)[:600]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
