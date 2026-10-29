# Running scores (#9)

The computed layer uses the parser's existing `race.distance_type` unchanged. It
stores norms and one score or explicit exclusion per result and formula version.
No employee matching or rating aggregation is performed here.

## Usage

From the repository root, set `DATABASE_URL` (or use the root `.env`, as with the
parser), then run:

```powershell
python parser_running/scoring.py --seed --recalculate --report
python parser_running/scoring.py --report --result-id 123
python parser_running/scoring.py --recalculate --formula-version run-v2
```

The first command explicitly initializes the scoring schema, inserts any missing
2026 norms, and rebuilds `run-v1` scores. Repeated seeding preserves norms already
maintained in the database. After editing a norm, run `--recalculate` to refresh
the selected formula version. Automatic edit/import hooks belong to later work.
A version is an explicit storage label for the current calculator; changing it
retains previous versions for comparison, and does not select another algorithm.

JSON reports contain total/scored/unscored counts, counts by existing distance
class and exclusion reason, point distribution (min/max/mean and four buckets),
and up to five complete examples. `--result-id` retrieves any full explanation;
a missing result/version returns `null`. Stored and JSON points retain full
floating-point precision; consumers may display them to two decimal places.

## Rules and public interfaces

`parser_running/scoring.py` exposes:

- `calculate(result, race, norms, formula_version='run-v1')`: pure calculator.
  `result` contains stored result columns; `race` supplies `distance_type`,
  `date_begin` as a Python date, and optionally `sport_type`, `race_type`,
  `discipline`. Norms are dictionaries with `year`, `distance_class`, `gender`,
  `value`, `unit`. Returns `points`, `reason`, and `breakdown`.
- `initialize(con)`, `seed_norms(con)`, `load_norms(con)`: idempotent schema
  initialization, insert-missing seed, and persisted normative table.
- `recalculate(con, formula_version='run-v1')`: atomic batched rebuild plus report.
- `get_score(con, result_id, formula_version='run-v1')`,
  `score_report(con, formula_version='run-v1', sample_limit=5)`: inspect the stored layer.

Database functions use the caller's transaction. The CLI commits successful
operations. Recalculation streams rows in batches of 1000; it never loads the
whole result table into memory. The score primary key is
`(result_id, formula_version)`. Deleting/reimporting parser results cascades the
derived scores; recalculate after reimport. History is retained across formula
versions while the source result exists, rather than becoming orphaned on import.

Only FIN, nonduplicate results with M/F gender qualify. A present chip time wins;
only an absent chip time falls back to gun. Nonpositive, malformed or nonfinite
times receive reasons; an invalid chip time never silently falls back to gun.
For each distance class/gender, the calculator selects the exact start year,
otherwise the latest earlier normative year, otherwise the earliest available.
The breakdown includes requested and actual years, normative value/unit,
chip/gun selection, substituted formula, points and version. Scores are uncapped.
Missing date, class, norm, gender, distance or time receive explicit reasons;
non-FIN, duplicates, relays and known nonrunning sports are excluded.

## 2026 seed and G1 boundary

The seed transcribes the customer's original running normative table, referenced
by `docs/scoring-spec.md` (#8). Values are seconds except 24-hour running (km).

| Class | M | F |
|---|---:|---:|
| 60m | 6.84 | 7.5 |
| 100m | 10.62 | 11.75 |
| 200m | 21.65 | 24.4 |
| 400m | 47.9 | 54.8 |
| 800m | 111 | 127 |
| 1000m | 142 | 165 |
| 1500m | 228 | 259 |
| 1mile | 243 | 279 |
| 3000m | 486 | 555 |
| 5000m | 846 | 965 |
| 10000m | 1760 | 2028 |
| half_marathon | 3900 | 4540 |
| marathon | 8400 | 9600 |
| 100km | 24960 | 28800 |
| 24h | 245 | 216 |

The pure calculator supports `race.distance_type='24h'` and an explicit
`result.distance_km` for **achieved kilometres**, using km / norm km × 1000.
The current parser has no achieved-distance column or 24h classification. Both
24h norms are stored and G1-tested, but existing DB results cannot yet supply
that input; if a stored race were assigned 24h it would receive
`missing_distance`. Adding this ingestion/representation belongs to #10.
Race length and time fields are never interpreted as achieved kilometres.
New synonyms (parkrun, etc.) and classifier tolerance/discipline rules also belong
to #10. Existing classes are used as-is, so #9's G1 tests cover all 30 normative
class/gender pairs, the formulas, years and eligibility, not the future classifier.

## Verification

```powershell
$env:SCORING_TEST_DATABASE_URL = 'postgresql://test_user@127.0.0.1:55439/postgres'
python -m unittest discover -s tests -p 'test_scoring*.py' -v
```

Use an expendable PostgreSQL 16+ database. Each database test creates a uniquely
named schema containing only synthetic rows; rollback/drop removes it afterward.
The CLI test commits its isolated fixture for a subprocess to read, then drops
that same schema. Tests never use the production `DATABASE_URL`; they are skipped
unless the explicit test URL is provided. Calculator tests run without a database.
