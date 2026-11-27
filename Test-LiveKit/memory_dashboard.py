"""Read-only memory table counts and history metadata for the local dashboard."""
import json
import os
from datetime import date, datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env', override=False)
url = os.getenv('DATABASE_URL', '').replace('postgresql+psycopg://', 'postgresql://', 1)
if not url:
    raise SystemExit(1)
with psycopg.connect(url, connect_timeout=5) as conn:
    with conn.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        counts = {}
        for name in ('users', 'conversations', 'memories', 'memory_history'):
            cur.execute('SELECT count(*) FROM ' + name)
            counts[name] = cur.fetchone()[0]
        cur.execute('SELECT action, created_at FROM memory_history ORDER BY created_at DESC LIMIT 30')
        history = [{'action': action, 'created_at': timestamp.isoformat()} for action, timestamp in cur.fetchall()]
print(json.dumps({'counts': counts, 'history': history}))
