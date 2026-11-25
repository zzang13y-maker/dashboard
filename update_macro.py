import csv, io, json, math
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen, Request


def collect(series):
    start = date.today() - timedelta(days=90)
    url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}'
    with urlopen(Request(url, headers={'User-Agent': 'MarketDashboard/1.0'}), timeout=45) as response:
        reader = csv.DictReader(io.StringIO(response.read().decode('utf-8-sig')))
        rows = {}
        for row in reader:
            try:
                d = row.get('observation_date') or row.get('DATE')
                v = float(row[series])
                if date.fromisoformat(d) <= date.today() and math.isfinite(v) and v > 0:
                    rows[d] = v
            except (ValueError, TypeError, KeyError):
                continue
    if len(rows) < 6 or (date.today()-date.fromisoformat(max(rows))).days >= 7:
        raise RuntimeError(f'{series}: insufficient or stale data')
    history = [{'d': d, 'v': rows[d]} for d in sorted(rows)[-30:]]
    return {'date': history[-1]['d'], 'value': history[-1]['v'], 'history': history}


if __name__ == '__main__':
    result = {'vix': collect('VIXCLS'), 'hy': collect('BAMLH0A0HYM2')}
    Path('market_macro.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print('Updated:', result['vix']['date'], result['hy']['date'])
