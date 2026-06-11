import sqlite3, json
from pathlib import Path
from datetime import datetime
from dataclasses import asdict, is_dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders(
  order_id TEXT PRIMARY KEY,
  intent_hash TEXT,
  symbol TEXT,
  side TEXT,
  qty REAL,
  status TEXT,
  payload TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS fills(
  fill_id TEXT PRIMARY KEY,
  order_id TEXT,
  symbol TEXT,
  side TEXT,
  qty REAL,
  price REAL,
  payload TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS pnl_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT,
  realized_pnl REAL,
  unrealized_pnl REAL,
  payload TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS tax_lot_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT,
  side TEXT,
  qty REAL,
  price REAL,
  fee REAL DEFAULT 0,
  tax_hint TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT,
  payload TEXT,
  created_at TEXT
);
"""
class FundDB:
    def __init__(self, path="phase9_fund_ops.db"):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
    def log(self, event_type, payload):
        if is_dataclass(payload):
            payload = asdict(payload)
        self.conn.execute("INSERT INTO audit_log(event_type,payload,created_at) VALUES(?,?,?)",
                          (event_type, json.dumps(payload, ensure_ascii=False, default=str), datetime.utcnow().isoformat()))
        self.conn.commit()
    def close(self):
        self.conn.close()
