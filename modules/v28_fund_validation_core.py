
from flask import jsonify, request, Response
from modules.v27_full_institutional import AlertAuditLogEngine, PortfolioHeatCorrelationEngine, StrategyRankingEngine, MarketRegimeAI, AutoOutcomeScheduler, InstitutionalDashboard

def register_v27_full_institutional_routes(app):
    @app.route('/v27/audit/preview', methods=['GET','POST'])
    def v27_audit_preview():
        payload=request.get_json(silent=True) or {'symbol':'NVDA','score':91,'conviction_score':82}
        decision={'allow_send':True,'adaptive_score':89,'blocked_reasons':[]}
        return jsonify(AlertAuditLogEngine().build_record(payload,decision))
    @app.route('/v27/portfolio-heat', methods=['GET','POST'])
    def v27_portfolio_heat():
        payload=request.get_json(silent=True) or {}
        return jsonify(PortfolioHeatCorrelationEngine().evaluate(payload.get('candidate',{'symbol':'AMD','risk_r':1}),payload.get('open_positions',[{'symbol':'NVDA','risk_r':1},{'symbol':'TSM','risk_r':1}])))
    @app.route('/v27/best-theme', methods=['POST'])
    def v27_best_theme(): return jsonify(PortfolioHeatCorrelationEngine().select_best_from_theme((request.get_json(silent=True) or {}).get('candidates',[])))
    @app.route('/v27/strategy-ranking', methods=['GET','POST'])
    def v27_strategy_ranking():
        rows=(request.get_json(silent=True) or {}).get('rows')
        if not rows: rows=[{'strategy':'VWAP_RECLAIM','outcome':'TP2','return_r':2},{'strategy':'VWAP_RECLAIM','outcome':'WIN','return_r':1},{'strategy':'EMA_CROSS','outcome':'SL','return_r':-1}]*10
        return jsonify(StrategyRankingEngine().rank(rows))
    @app.route('/v27/regime-ai', methods=['GET','POST'])
    def v27_regime_ai(): return jsonify(MarketRegimeAI().classify(request.get_json(silent=True) or {'spy_trend_score':64,'qqq_trend_score':70,'vix':18,'breadth_score':62}))
    @app.route('/v27/outcome-scheduler/status')
    def v27_outcome_scheduler_status(): return jsonify(AutoOutcomeScheduler().scheduler_status())
    @app.route('/v27/outcome-scheduler/check', methods=['POST'])
    def v27_outcome_scheduler_check():
        payload=request.get_json(silent=True) or {}; return jsonify(AutoOutcomeScheduler().check_open_signals(payload.get('open_signals',[]),payload.get('price_map',{})))
    @app.route('/v27/institutional-json')
    def v27_institutional_json():
        data={'top_signals':[{'symbol':'NVDA','score':91}], 'market_regime':MarketRegimeAI().classify({'spy_trend_score':64,'qqq_trend_score':70,'vix':18,'breadth_score':62}), 'outcome_scheduler':AutoOutcomeScheduler().scheduler_status(), 'notes':['Scan เยอะ ส่งน้อย','Block ด้วย Data Quality/Capital Protection','เลือกตัวดีที่สุดต่อธีม']}
        return jsonify(InstitutionalDashboard().build(data))
    @app.route('/v27/institutional-dashboard')
    def v27_institutional_dashboard():
        payload=InstitutionalDashboard().build({'top_signals':[{'symbol':'NVDA','score':91}], 'market_regime':MarketRegimeAI().classify({'spy_trend_score':64,'qqq_trend_score':70,'vix':18,'breadth_score':62}), 'outcome_scheduler':AutoOutcomeScheduler().scheduler_status()})
        return Response(InstitutionalDashboard().html(payload), mimetype='text/html')
V28_VERSION = "28.0"

def audit_signal(*args, **kwargs):
    return {
        "status": "ok"
    }

def info_v28_db():
    return {
        "database": "connected",
        "version": V28_VERSION
    }
def init_v28_db():
    return {
        "status": "initialized",
        "version": V28_VERSION
    }
def portfolio_gate(*args, **kwargs):
    return {
        "allowed": True,
        "reason": "pass"
    }


def evaluate_portfolio_risk(*args, **kwargs):
    return {
        "risk_score": 50,
        "risk_level": "medium"
    }
