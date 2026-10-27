"""E32: стадионные дистанции в метрах и миля не распознавались — разбирались только «км»."""
from protocol import Task

META = {"id": "E32", "title": "дистанции «100 м», «1 миля» не распознаются", "expected": "fix"}
_BLOCK = '''    if m := re.search(num + r"?\\s*(?:миля|мили|миль|mile)", s):
        return round(float((m.group(1) or "1").replace(",", ".")) * MILE_KM, 3)
    # метры: число + «м»/«m», за которым не идёт буква («мин», «муж» без числа сюда не попадут)
    if m := re.search(num + r"\\s*(?:м|m)(?![а-яёa-z])", s):
        return float(m.group(1).replace(",", ".")) / 1000
'''
MUTATIONS = [{"file": "normalize.py", "old": _BLOCK, "new": ""}]
ORACLE = {"action": "patch", "reason": "добавить мили и метры",
          "edits": [{"file": "normalize.py",
                     "old": '        return float(m.group(1).replace(",", "."))\n    return None',
                     "new": '        return float(m.group(1).replace(",", "."))\n' + _BLOCK + "    return None"}]}


def task() -> Task:
    return Task("E32", "runc", "parse", "unknown_distance", "speed_comp_2026_spring/509",
                {"names_without_distance": ["100 м (муж.)", "1 миля (жен.)", "1500 м (муж.)", "60 м (жен.)"],
                 "rows": 1801, "hint": "дистанция не определилась по названию, distance_m = NULL"})


def check(sb):
    from normalize import km_from_name, km_to_m, norm_distance
    got = {n: norm_distance(km_to_m(km_from_name(n))) for n in
           ["100 м (муж.)", "1 миля (жен.)", "1500 м (муж.)", "60 м (жен.)", "600 м (муж.)", "10 км"]}
    exp = {"100 м (муж.)": "100m", "1 миля (жен.)": "1mile", "1500 м (муж.)": "1500m", "60 м (жен.)": "60m",
           "600 м (муж.)": None, "10 км": "10000m"}
    return got == exp, f"получили {got}"
