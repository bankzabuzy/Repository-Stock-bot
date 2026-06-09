from flask import jsonify
from modules.v41_top5_institutional_core import (
    V41_VERSION,
    rank_top5_institutional,
    format_top5_line_message
)

def register_v41_top5_routes(app):

    def get_latest_signals():
        try:
            # ใช้ฟังก์ชันเดิมของระบบ ถ้ามี
            from main import get_latest_signal_rows
            return get_latest_signal_rows(limit=100)
        except Exception:
            pass

        try:
            # fallback จาก database เดิม
            import sqlite3
            conn = sqlite3.connect("signals.db")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY id DESC LIMIT 100"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    @app.route("/v41/top5-buy", methods=["GET"])
    @app.route("/api/top5-buy", methods=["GET"])
    def v41_top5_buy():
        signals = get_latest_signals()
        picks = rank_top5_institutional(signals, limit=5)

        return jsonify({
            "ok": True,
            "version": V41_VERSION,
            "count": len(picks),
            "top5": picks,
            "line_message": format_top5_line_message(picks)
        })

    @app.route("/v41/top5-line", methods=["GET"])
    def v41_top5_line():
        signals = get_latest_signals()
        picks = rank_top5_institutional(signals, limit=5)

        return format_top5_line_message(picks), 200, {
            "Content-Type": "text/plain; charset=utf-8"
        }
