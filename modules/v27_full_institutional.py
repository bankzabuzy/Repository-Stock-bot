
from datetime import datetime, timezone
THEME_MAP={"NVDA":"SEMICONDUCTOR","AMD":"SEMICONDUCTOR","AVGO":"SEMICONDUCTOR","TSM":"SEMICONDUCTOR","MRVL":"SEMICONDUCTOR","SMCI":"SEMICONDUCTOR","AAPL":"MEGA_CAP_TECH","MSFT":"MEGA_CAP_TECH","META":"MEGA_CAP_TECH","GOOGL":"MEGA_CAP_TECH","AMZN":"MEGA_CAP_TECH","TSLA":"EV_HIGH_BETA","PLTR":"AI_SOFTWARE","QQQ":"INDEX","SPY":"INDEX","IWM":"INDEX","GOLD":"GOLD","XAUUSD":"GOLD"}
def now_iso(): return datetime.now(timezone.utc).isoformat()
class AlertAuditLogEngine:
    def build_record(self,payload,decision):
        reasons=decision.get('blocked_reasons') or decision.get('reasons') or []
        if isinstance(reasons,list): reasons=' | '.join(map(str,reasons))
        return {'created_at':now_iso(),'symbol':str(payload.get('symbol',decision.get('symbol',''))).upper(),'decision':'PASS' if decision.get('allow_send') or decision.get('action')=='SEND_LINE' else 'FAIL','score':float(payload.get('score',decision.get('base_score',0)) or 0),'adaptive_score':float(decision.get('adaptive_score',payload.get('adaptive_score',0)) or 0),'conviction_score':float(payload.get('conviction_score',0) or 0),'risk_grade':payload.get('risk_grade',payload.get('conviction_grade','')),'reasons':reasons or 'PASS'}
    def summarize(self,rows):
        total=len(rows); passed=sum(1 for r in rows if str(r.get('decision','')).upper()=='PASS')
        return {'total_scanned':total,'pass':passed,'fail':total-passed,'pass_rate_pct':round((passed/total*100) if total else 0,2)}
class PortfolioHeatCorrelationEngine:
    def __init__(self,max_total_heat_r=6.0,max_theme_heat_r=2.5,max_correlated_positions=1):
        self.max_total_heat_r=max_total_heat_r; self.max_theme_heat_r=max_theme_heat_r; self.max_correlated_positions=max_correlated_positions
    def theme(self,symbol): return THEME_MAP.get(str(symbol).upper(),'OTHER')
    def evaluate(self,candidate,open_positions):
        symbol=str(candidate.get('symbol','')).upper(); theme=self.theme(symbol); risk=float(candidate.get('risk_r',1.0) or 1.0)
        total=sum(float(p.get('risk_r',1.0) or 1.0) for p in open_positions)
        same=[p for p in open_positions if self.theme(p.get('symbol',''))==theme]
        theme_heat=sum(float(p.get('risk_r',1.0) or 1.0) for p in same)
        reasons=[]
        if total+risk>self.max_total_heat_r: reasons.append('PORTFOLIO_HEAT_EXCEEDED')
        if theme_heat+risk>self.max_theme_heat_r: reasons.append('THEME_HEAT_EXCEEDED:'+theme)
        if len(same)>=self.max_correlated_positions: reasons.append('CORRELATED_THEME_ALREADY_OPEN:'+theme)
        return {'ok':not reasons,'symbol':symbol,'theme':theme,'projected_total_heat_r':round(total+risk,2),'projected_theme_heat_r':round(theme_heat+risk,2),'reasons':reasons}
    def select_best_from_theme(self,candidates):
        grouped={}
        for c in candidates: grouped.setdefault(self.theme(c.get('symbol','')),[]).append(c)
        selected=[]; suppressed=[]
        for theme,items in grouped.items():
            best=sorted(items,key=lambda x:(float(x.get('conviction_score',0) or 0),float(x.get('adaptive_score',x.get('score',0)) or 0),float(x.get('rvol',0) or 0)),reverse=True)[0]
            selected.append(best)
            for item in items:
                if item is not best: suppressed.append({'symbol':item.get('symbol'),'theme':theme,'reason':'เลือก '+str(best.get('symbol'))+' เป็นตัวแทนธีม'})
        return {'selected':selected,'suppressed':suppressed}
class StrategyRankingEngine:
    def rank(self,rows):
        stats={}
        for r in rows:
            st=str(r.get('strategy','UNKNOWN')).upper(); ret=float(r.get('return_r',0) or 0); outcome=str(r.get('outcome',r.get('result',''))).upper()
            s=stats.setdefault(st,{'trades':0,'wins':0,'losses':0,'total_r':0.0}); s['trades']+=1; s['total_r']+=ret
            if outcome in {'TP1','TP2','TP3','WIN'} or ret>0: s['wins']+=1
            elif outcome in {'SL','LOSS'} or ret<0: s['losses']+=1
        ranked=[]
        for st,s in stats.items():
            wr=s['wins']/s['trades']*100 if s['trades'] else 0; exp=s['total_r']/s['trades'] if s['trades'] else 0
            ranked.append({'strategy':st,'trades':s['trades'],'win_rate_pct':round(wr,2),'expectancy_r':round(exp,3),'strategy_score':round(wr*.6+exp*20,2)})
        ranked.sort(key=lambda x:(x['strategy_score'],x['trades']),reverse=True)
        return {'ranked':ranked,'best_strategy':ranked[0] if ranked else None}
class MarketRegimeAI:
    def classify(self,context):
        spy=float(context.get('spy_trend_score',50) or 50); qqq=float(context.get('qqq_trend_score',50) or 50); vix=float(context.get('vix',0) or 0); breadth=float(context.get('breadth_score',50) or 50); dxy=float(context.get('dxy_trend_score',50) or 50); y10=float(context.get('us10y_trend_score',50) or 50)
        if vix>=30 or breadth<30: regime='PANIC'
        elif breadth>=60 and spy>=60 and qqq>=60 and vix<22: regime='RISK_ON'
        elif breadth<45 or dxy>65 or y10>65: regime='RISK_OFF'
        elif 45<=breadth<=58 and vix<25: regime='RANGE'
        else: regime='TREND'
        policies={'RISK_ON':{'score_adjust':4,'position_multiplier':1.0,'max_alerts':5,'allowed':True},'TREND':{'score_adjust':2,'position_multiplier':.85,'max_alerts':4,'allowed':True},'RANGE':{'score_adjust':-2,'position_multiplier':.6,'max_alerts':2,'allowed':True},'RISK_OFF':{'score_adjust':-6,'position_multiplier':.35,'max_alerts':1,'allowed':True},'PANIC':{'score_adjust':-12,'position_multiplier':0.0,'max_alerts':0,'allowed':False}}
        return {'regime':regime,'policy':policies[regime],'inputs':{'spy':spy,'qqq':qqq,'vix':vix,'breadth':breadth,'dxy':dxy,'us10y':y10}}
class AutoOutcomeScheduler:
    def scheduler_status(self): return {'ok':True,'name':'V27.6 Auto Outcome Scheduler','interval_minutes':15,'purpose':'เช็ค TP/SL อัตโนมัติ'}
    def check_open_signals(self,open_signals,price_map):
        results=[]
        for sig in open_signals:
            symbol=str(sig.get('symbol','')).upper(); price=price_map.get(symbol)
            if price is None: results.append({'symbol':symbol,'ok':False,'reason':'no price'}); continue
            tp1=float(sig.get('tp1',0) or 0); sl=float(sig.get('sl',0) or 0); outcome='OPEN'
            if tp1 and price>=tp1: outcome='TP1'
            elif sl and price<=sl: outcome='SL'
            results.append({'symbol':symbol,'price':price,'outcome':outcome})
        return {'checked_at':now_iso(),'checked':len(results),'results':results}
class InstitutionalDashboard:
    def build(self,data): return {'ok':True,'version':'V27.7 Institutional Dashboard','updated_at':now_iso(),**data}
    def html(self,payload):
        rows=''.join(f'<tr><td><b>{k}</b></td><td><pre>{v}</pre></td></tr>' for k,v in payload.items())
        return '<html><head><title>V27.7 Dashboard</title><style>body{font-family:Arial;background:#0f172a;color:#e5e7eb;padding:24px}td{border:1px solid #334155;padding:10px}h1{color:#38bdf8}</style></head><body><h1>V27.7 Institutional Dashboard</h1><table>'+rows+'</table></body></html>'
