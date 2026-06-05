from __future__ import annotations

from flask import jsonify, request

from modules.v34_free_paper_trading_core import (
    V34_VERSION,
    MockBroker,
    evaluate_kill_switch,
    monitoring_report,
    paper_trade_from_signals,
    save_monitoring_json,
    save_trades_csv,
    v34_decision_pack,
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


def register_v34_free_paper_trading_routes(app):
    @app.route('/v34/health')
    def v34_health():
        return jsonify({"ok": True, "version": V34_VERSION, "mode": "free_paper_trading_only"})

    @app.route('/v34/paper-trade', methods=['POST'])
    def v34_paper_trade():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(paper_trade_from_signals(
            prices_by_symbol=payload.get('prices_by_symbol') or payload.get('prices') or {},
            signals_by_symbol=payload.get('signals_by_symbol') or payload.get('signals') or {},
            initial_cash=payload.get('initial_cash', 100000),
            allocation_weights=payload.get('allocation_weights') or payload.get('weights') or None,
            fee_bps=payload.get('fee_bps', 1.0),
            slippage_bps=payload.get('slippage_bps', 2.0),
            max_position_weight=payload.get('max_position_weight', 0.25),
            min_cash_weight=payload.get('min_cash_weight', 0.05),
            max_drawdown_limit_pct=payload.get('max_drawdown_limit_pct', -12.0),
            warning_drawdown_pct=payload.get('warning_drawdown_pct', -7.0),
            hard_daily_loss_pct=payload.get('hard_daily_loss_pct', -2.0),
        ))

    @app.route('/v34/kill-switch', methods=['POST'])
    def v34_kill_switch():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(evaluate_kill_switch(
            equity_curve=payload.get('equity_curve') or [],
            daily_loss_pct=payload.get('daily_loss_pct', 0.0),
            max_drawdown_limit_pct=payload.get('max_drawdown_limit_pct', -12.0),
            warning_drawdown_pct=payload.get('warning_drawdown_pct', -7.0),
            hard_daily_loss_pct=payload.get('hard_daily_loss_pct', -2.0),
            consecutive_loss_limit=int(payload.get('consecutive_loss_limit') or 4),
            realized_pnls=payload.get('realized_pnls') or [],
        ))

    @app.route('/v34/mock-broker/order', methods=['POST'])
    def v34_mock_broker_order():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        broker = MockBroker(
            initial_cash=payload.get('initial_cash', 100000),
            fee_bps=payload.get('fee_bps', 1.0),
            slippage_bps=payload.get('slippage_bps', 2.0),
        )
        # Stateless endpoint: useful for testing one order. Full sequence should use /v34/paper-trade.
        return jsonify(broker.place_order(
            symbol=payload.get('symbol', ''),
            side=payload.get('side', ''),
            quantity=payload.get('quantity'),
            notional=payload.get('notional'),
            price=payload.get('price'),
        ))

    @app.route('/v34/monitoring', methods=['POST'])
    def v34_monitoring():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(monitoring_report(
            broker_snapshot=payload.get('broker_snapshot') or {},
            equity_curve=payload.get('equity_curve') or [],
            trades=payload.get('trades') or [],
            blocked_orders=payload.get('blocked_orders') or [],
        ))

    @app.route('/v34/decision-pack', methods=['POST'])
    def v34_decision_pack_route():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(v34_decision_pack(payload))
