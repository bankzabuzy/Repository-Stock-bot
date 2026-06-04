from datetime import datetime, timezone

class ForwardTestEngine:
    def create_signal(self, payload):
        return {
            "ok": True,
            "symbol": str(payload.get("symbol", "")).upper(),
            "side": str(payload.get("side", "CALL")).upper(),
            "entry": float(payload.get("entry", 0) or 0),
            "tp1": float(payload.get("tp1", 0) or 0),
            "tp2": float(payload.get("tp2", 0) or 0),
            "tp3": float(payload.get("tp3", 0) or 0),
            "sl": float(payload.get("sl", 0) or 0),
            "score": float(payload.get("score", 0) or 0),
            "conviction": str(payload.get("conviction", "UNKNOWN")),
            "strategy": str(payload.get("strategy", "UNKNOWN")),
            "regime": str(payload.get("regime", "UNKNOWN")),
            "status": "OPEN",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def summarize(self, rows):
        total = len(rows)
        wins = sum(1 for r in rows if str(r.get("outcome", "")).upper() in {"TP1","TP2","TP3","WIN"})
        losses = sum(1 for r in rows if str(r.get("outcome", "")).upper() in {"SL","LOSS"})
        closed = wins + losses
        return {
            "total_signals": total,
            "wins": wins,
            "losses": losses,
            "closed": closed,
            "open": total - closed,
            "win_rate_pct": round((wins / closed * 100) if closed else 0, 2),
        }
