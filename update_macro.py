import csv, io, json, math, time, os
from urllib.parse import urlencode
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request

PATH = Path('market_macro.json')
TODAY = datetime.now(timezone.utc).date()
START = TODAY - timedelta(days=90)


def fetch(url, column, cboe=False):
    print('Fetching:', url, flush=True)
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/csv,*/*'}), timeout=35) as response:
        content = response.read().decode('utf-8-sig')
    rows = {}
    for row in csv.DictReader(io.StringIO(content)):
        try:
            raw = row.get('observation_date') or row.get('DATE')
            d = datetime.strptime(raw.strip(), '%m/%d/%Y').date() if cboe else date.fromisoformat(raw.strip())
            v = float(row[column])
            if START <= d <= TODAY and math.isfinite(v) and v > 0:
                rows[d.isoformat()] = v
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    if len(rows) < 6 or (TODAY-date.fromisoformat(max(rows))).days >= 7:
        raise RuntimeError('Insufficient or stale observations')
    history = [{'d': d, 'v': rows[d]} for d in sorted(rows)[-30:]]
    return {'date': history[-1]['d'], 'value': history[-1]['v'], 'history': history}


def fred(series):
    key = os.environ.get('FRED_API_KEY', '').strip()
    if not key:
        raise RuntimeError('FRED_API_KEY secret missing')
    params = urlencode({'series_id': series, 'api_key': key,
                        'file_type': 'json', 'observation_start': START.isoformat()})
    print(f'Fetching FRED API: {series}', flush=True)
    try:
        with urlopen(Request('https://api.stlouisfed.org/fred/series/observations?' + params,
                             headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}), timeout=35) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'FRED HTTP {exc.code}') from None
    except Exception as exc:
        raise RuntimeError(f'FRED connection/read failure: {type(exc).__name__}') from None
    rows = {}
    for row in payload.get('observations', []):
        try:
            d = date.fromisoformat(row['date'])
            v = float(row['value'])
            if START <= d <= TODAY and math.isfinite(v) and v > 0:
                rows[d.isoformat()] = v
        except (ValueError, TypeError, KeyError):
            continue
    if len(rows) < 6 or (TODAY-date.fromisoformat(max(rows))).days >= 7:
        raise RuntimeError('Insufficient or stale FRED observations')
    history = [{'d': d, 'v': rows[d]} for d in sorted(rows)[-30:]]
    return {'date': history[-1]['d'], 'value': history[-1]['v'], 'history': history}


def collect(key):
    sources = ([('Cboe', lambda: fetch('https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv', 'CLOSE', True)), ('FRED', lambda: fred('VIXCLS'))] if key == 'vix' else [('FRED', lambda: fred('BAMLH0A0HYM2'))])
    for attempt in range(2):
        for name, fn in sources:
            try:
                result = fn()
                print(f'{key}: {name} OK ({result["date"]})', flush=True)
                return result
            except Exception as exc:
                print(f'{key}: {name} attempt {attempt+1}: {type(exc).__name__}: {exc}', flush=True)
        if attempt == 0:
            time.sleep(3)
    print(f'::warning::{key} collection failed; retaining existing data if available', flush=True)
    return None


def main():
    old = json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else {}
    result = dict(old)
    with ThreadPoolExecutor(max_workers=2) as pool:
        updates = dict(zip(('vix', 'hy'), pool.map(collect, ('vix', 'hy'))))
    for key, value in updates.items():
        if value is not None and value['date'] >= old.get(key, {}).get('date', ''):
            result[key] = value
    if not any(updates.values()):
        raise SystemExit('Both sources failed; existing JSON left unchanged.')
    tmp = PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    tmp.replace(PATH)
    print('Saved:', ', '.join(result), flush=True)

if __name__ == '__main__':
    main()
