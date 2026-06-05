from __future__ import annotations

from flask import jsonify, request

from modules.v32_institutional_risk_core import (
    V32_VERSION,
    position_sizing,
    pretrade_risk_gate,
    backtest_signals,
    walk_forward_report,
)

try:
    from modules.v29_governance_core import require_api_key
except Exception:  # pragma: no cover
    require_api_key = None


def require_v29_api_key():
    if require_api_key is None:
        return None
    ok, reason = require_api_key(request.headers, request.args)
    if not ok:
        return jsonify({"ok": False, "error": reason, "hint": "Send X-API-Key or Authorization: Bearer token"}), 401
    return None


def register_v32_institutional_risk_routes(app):
    @app.route('/v32/health')
    def v32_health():
        return jsonify({"ok": True, "version": V32_VERSION})

    @app.route('/v32/position-size', methods=['POST'])
    def v32_position_size():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(position_sizing(
            equity=payload.get('equity'),
            entry=payload.get('entry'),
            stop=payload.get('stop'),
            risk_per_trade=payload.get('risk_per_trade', None),
            max_position_pct=payload.get('max_position_pct', None),
        ))

    @app.route('/v32/pretrade-gate', methods=['POST'])
    def v32_pretrade_gate():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        ok, detail = pretrade_risk_gate(payload.get('signal') or payload, payload.get('portfolio') or {})
        return jsonify({'ok': True, 'allow': ok, 'detail': detail})

    @app.route('/v32/backtest', methods=['POST'])
    def v32_backtest():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(backtest_signals(
            prices=payload.get('prices') or [],
            signals=payload.get('signals') or [],
            initial_equity=float(payload.get('initial_equity') or 100000),
            fee_bps=float(payload.get('fee_bps') or 2.0),
            slippage_bps=float(payload.get('slippage_bps') or 5.0),
            stop_loss_pct=float(payload.get('stop_loss_pct') or 0.03),
            take_profit_pct=float(payload.get('take_profit_pct') or 0.06),
            risk_per_trade=float(payload.get('risk_per_trade') or 0.005),
        ))

    @app.route('/v32/walk-forward', methods=['POST'])
    def v32_walk_forward():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(walk_forward_report(
            prices=payload.get('prices') or [],
            signals=payload.get('signals') or [],
            folds=int(payload.get('folds') or 4),
            initial_equity=float(payload.get('initial_equity') or 100000),
            fee_bps=float(payload.get('fee_bps') or 2.0),
            slippage_bps=float(payload.get('slippage_bps') or 5.0),
            stop_loss_pct=float(payload.get('stop_loss_pct') or 0.03),
            take_profit_pct=float(payload.get('take_profit_pct') or 0.06),
            risk_per_trade=float(payload.get('risk_per_trade') or 0.005),
        ))
