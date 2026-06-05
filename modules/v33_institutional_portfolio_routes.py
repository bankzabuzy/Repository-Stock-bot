from __future__ import annotations

from flask import jsonify, request

from modules.v33_institutional_portfolio_core import (
    V33_VERSION,
    drawdown_control,
    institutional_decision_pack,
    portfolio_allocation,
    relative_strength_ranking,
    walk_forward_validation,
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


def register_v33_institutional_portfolio_routes(app):
    @app.route('/v33/health')
    def v33_health():
        return jsonify({"ok": True, "version": V33_VERSION})

    @app.route('/v33/relative-strength', methods=['POST'])
    def v33_relative_strength():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(relative_strength_ranking(
            assets=payload.get('assets') or {},
            benchmark=payload.get('benchmark') or [],
            lookbacks=payload.get('lookbacks') or (20, 60, 120),
        ))

    @app.route('/v33/drawdown-control', methods=['POST'])
    def v33_drawdown_control():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(drawdown_control(
            equity_curve=payload.get('equity_curve') or [],
            daily_loss_pct=payload.get('daily_loss_pct', 0.0),
            max_drawdown_limit_pct=payload.get('max_drawdown_limit_pct', -12.0),
            warning_drawdown_pct=payload.get('warning_drawdown_pct', -7.0),
            hard_daily_loss_pct=payload.get('hard_daily_loss_pct', -2.0),
        ))

    @app.route('/v33/portfolio-allocation', methods=['POST'])
    def v33_portfolio_allocation():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(portfolio_allocation(
            candidates=payload.get('candidates') or [],
            total_equity=payload.get('total_equity', 100000),
            max_weight=payload.get('max_weight', 0.25),
            min_weight=payload.get('min_weight', 0.02),
            cash_floor=payload.get('cash_floor', 0.10),
            drawdown_state=payload.get('drawdown_state') or None,
        ))

    @app.route('/v33/walk-forward-validation', methods=['POST'])
    def v33_walk_forward_validation():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(walk_forward_validation(
            prices_by_symbol=payload.get('prices_by_symbol') or {},
            signals_by_symbol=payload.get('signals_by_symbol') or {},
            folds=int(payload.get('folds') or 4),
            initial_equity=float(payload.get('initial_equity') or 100000),
            fee_bps=float(payload.get('fee_bps') or 2.0),
            slippage_bps=float(payload.get('slippage_bps') or 5.0),
            stop_loss_pct=float(payload.get('stop_loss_pct') or 0.03),
            take_profit_pct=float(payload.get('take_profit_pct') or 0.06),
            risk_per_trade=float(payload.get('risk_per_trade') or 0.005),
        ))

    @app.route('/v33/decision-pack', methods=['POST'])
    def v33_decision_pack():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(institutional_decision_pack(payload))
