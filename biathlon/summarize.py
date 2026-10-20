"""Сводка качества по отчётам run.py: какие проверки падают, в каких дисциплинах."""
import collections
import json
from pathlib import Path

import pandas as pd

P = Path(__file__).parent / "data" / "processed"
out = []
for rep in sorted(P.glob("report_*.json")):
    tag = rep.stem.removeprefix("report_")
    r = json.loads(rep.read_text(encoding="utf-8"))
    rs = [x for x in r["races"] if x.get("checks")]
    fails = collections.Counter(k for x in rs for k, v in x["checks"].items() if not v)
    by_disc = collections.defaultdict(lambda: [0, 0])
    for x in rs:
        by_disc[x.get("discipline")][1] += 1
        by_disc[x.get("discipline")][0] += x["status"] == "ok"
    df = pd.read_csv(P / f"results_{tag}.csv", dtype={"race_id": str})
    ok_ids = {x["race_id"] for x in rs if x["status"] == "ok"}
    out.append(f"## {tag}: {dict(r['stats'])}")
    out.append(f"  гонок с итоговым протоколом: {len(rs)}, прошли все проверки: {len(ok_ids)}")
    out.append(f"  записей всего: {len(df)}, в чистых гонках: {df.race_id.isin(ok_ids).sum()}")
    out.append(f"  падающие проверки: {dict(fails)}")
    out.append(f"  по дисциплинам (ok/всего): {dict(by_disc)}")
    for x in rs:
        if x["status"] != "ok":
            bad = [k for k, v in x["checks"].items() if not v]
            out.append(f"    {x['race_id']} {x['title'][:50]} | n={x['n_results']} провалы={bad} "
                       f"пример={x['unparsed_lines'][:1]}")
(P / "summary.txt").write_text("\n".join(out), encoding="utf-8")
print("ok")
