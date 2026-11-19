"""Publish already-validated cash producer outputs to the four dashboard files.

No collection, model calculation, Git operation, messaging or orders. Historical
producer records are merged once by source date; market views keep their date.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,re
from datetime import date,timedelta
from pathlib import Path

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def verified_day(source,day):
    mp=source/'monthly'/day/f'cash_weight_signal_{day}.json'
    mv=read(source/'monthly'/day/'validation.json')
    sp=source/'staged'/day/f'staged_weekly_cash_{day}.json'
    sv=read(source/'staged'/day/f'validation_{day}.json')
    monthly,staged=read(mp),read(sp)
    assert all(x['status']=='OK' and x['trade_date']==day for x in (monthly,staged,mv,sv))
    assert mv['exit_code']==0
    provenance=mv['provenance'];book=provenance['workbook']
    assert sha(book['path'])==book['sha256'] and book['last_date'].replace('-','')==day
    assert book['columns']==28 and book['duplicate_date_rows']==0 and book['missing_numeric_cells']==0
    assert book['latest_row_complete'] and book['latest_row_all_positive']
    assert sha(provenance['runner_file'])==provenance['runner_sha256']
    assert sha(provenance['strategy_file'])==provenance['strategy_sha256']
    for key,path in provenance['module_files'].items():assert sha(path)==provenance['module_sha256'][key]
    for item in sv['inputs'].values():assert sha(item['path'])==item['sha256']
    assert sv['workbook']['sha256']==book['sha256']
    assert sv['inputs']['monthly_ma10_policy_module']['sha256']==provenance['module_sha256']['monthly_ma10_policy']
    assert monthly['policy_version']=='cash-weight-reference-v1.2.0-ma10-ma3-reentry'
    primary,decision=monthly['primary'],staged['decision']
    for child,parent in [('monthly_raw_model_cash_pct','raw_model_target_cash_pct'),('monthly_ma10_target_cash_pct','target_cash_pct'),('monthly_ma3_reentry_pending','ma3_reentry_pending'),('monthly_ma3_reentry_event','ma3_reentry_event')]:assert decision[child]==primary[parent]
    return monthly,staged,mv,sv,mp,sp

def refresh(root,source,trade_date):
    latest_path=root/'cash-management/latest.json';history_path=root/'cash-management/history.json'
    latest,history=read(latest_path),read(history_path)
    old_history=copy.deepcopy(history['records'])
    first=str(history.get('updated_through') or latest['as_of']).replace('-','')
    dates=sorted(p.name for p in (source/'monthly').iterdir() if p.is_dir() and re.fullmatch(r'\d{8}',p.name) and first<p.name<=trade_date)
    if first==trade_date and latest.get('validation',{}).get('publication_scope')=='VALIDATED_CASH_ONLY_RECOVERY':
        dates=latest['validation'].get('backfilled_dates',dates)
    if trade_date not in dates:dates.append(trade_date);dates.sort()
    if first<trade_date:
        calendars=sorted((source.parent/'eod_admin_task').glob('*/calendar_validation_*.json'),reverse=True)
        proof=next((read(p) for p in calendars if read(p).get('status')=='VERIFIED' and read(p).get('calendar_year')==int(trade_date[:4])),None)
        assert proof is not None,'Official calendar is required to verify history coverage'
        assert sha(proof['raw_path'])==proof['raw_sha256']
        holidays={x['calnd_dd'] for x in read(proof['raw_path'])['block1']}
        cursor=date.fromisoformat(first);end=date.fromisoformat(trade_date);required=[]
        while cursor<end:
            cursor+=timedelta(days=1)
            if cursor.weekday()<5 and cursor.isoformat() not in holidays:required.append(cursor.strftime('%Y%m%d'))
        assert set(dates)==set(required),'Missing dated model outputs: '+','.join(sorted(set(required)-set(dates)))
    verified={day:verified_day(source,day) for day in dates}
    monthly,staged,mv,sv,mp,sp=verified[trade_date]
    wise_path=source/'wise_daily/wise_final_latest.json';wise=read(wise_path)
    assert wise['status']=='OK' and wise['signal_class']=='EOD_CONFIRMED' and wise['trade_date'].replace('-','')==trade_date
    assert wise['sources']['wise_official_closes']['count']==26
    assert set(wise['sources']['wise_official_closes']['response_dates'])=={wise['trade_date']}
    assert wise['sources']['kiwoom_kospi']['response_date']==trade_date
    assert wise['sources']['kiwoom_kospi']['dated_report_crosscheck']['status']=='MATCH'
    assert wise['workbook_update']['after_sha256']==mv['provenance']['workbook']['sha256']
    primary,decision=monthly['primary'],staged['decision']
    final_cash=max(primary['target_cash_pct'],decision['target_cash_pct'])
    final_risky=min(primary['target_risky_pct'],decision['target_risky_pct'])
    iso=wise['trade_date'];cash_note=(f'현금비중 기준 {iso}: 월간 PRIMARY {primary["target_cash_pct"]:g}%·단계형 {decision["target_cash_pct"]:g}% → 최종 참고 현금 {final_cash:g}% / 위험자산 한도 {final_risky:g}%. '
        f'확정 WISE 26업종과 날짜 일치 KOSPI 일봉을 검증했습니다. 월간 MA10 단계형·MA3 재진입 정책을 적용한 참고 한도이며 실제 포지션·신규매수·자동주문을 뜻하지 않습니다. 월간 신호일 {primary["signal_date"]}의 지표와 현재 확정 종가를 구분합니다.')
    records={x['as_of']:x for x in history['records']};recent={x['as_of']:x for x in latest['history']}
    for day,(m,s,*_) in verified.items():
        p,d=m['primary'],s['decision'];cash=max(p['target_cash_pct'],d['target_cash_pct']);risky=min(p['target_risky_pct'],d['target_risky_pct'])
        daily=m['research_diagnostics']['latest_daily_snapshot']
        row={'as_of':m['as_of'],'daily_model_cash_pct':daily['target_cash_pct'],'daily_model_mode':daily['mode'],
             'monthly_primary_cash_pct':p['target_cash_pct'],'monthly_raw_model_cash_pct':p['raw_model_target_cash_pct'],'monthly_sizing_rule':p['sizing_rule'],
             'monthly_ma3_reentry_pending':p['ma3_reentry_pending'],'monthly_ma3_reentry_event':p['ma3_reentry_event'],'staged_cash_pct':d['target_cash_pct'],
             'applied_cash_pct':cash,'applied_risky_pct':risky,'action':d['action_today'],'action_label':f'현금 {cash:g}% · {d["action_today"]}','state':d['state']}
        records[row['as_of']]=row;recent[row['as_of']]={k:v for k,v in row.items() if k!='state'}
    history['records']=[records[k] for k in sorted(records)];history['updated_through']=iso
    assert all(records[x['as_of']]==x for x in old_history if x['as_of'].replace('-','')<min(dates))
    latest.update(as_of=iso,trade_date=trade_date,source_generated_at={'monthly':monthly['generated_at'],'staged_weekly':staged['generated_at']},history=[recent[k] for k in sorted(recent)])
    latest['combined_guidance'].update(target_cash_pct=final_cash,target_risky_pct=final_risky,action=decision['action_today'],action_label=f'현금 {final_cash:g}% · {decision["action_today"]}',state=f'월간·주간 현금 {final_cash:g}% · 위험자산 한도 {final_risky:g}%',reason=cash_note)
    for key in latest['monthly_primary']:
        if key in primary:latest['monthly_primary'][key]=primary[key]
    for dest,src in {'kospi_close_on_signal_date':'kospi_close','kospi_ma10_on_signal_date':'kospi_ma10','kospi_ma3_on_signal_date':'kospi_ma3','action':'action_on_trade_date','effective_date':'source_effective_date'}.items():latest['monthly_primary'][dest]=primary[src]
    for key in latest['staged_weekly']:
        if key in decision:latest['staged_weekly'][key]=decision[key]
    for dest,src in {'action':'action_today','signal_date':'weekly_signal_date','effective_date':'weekly_effective_date','accepted_rule':'latest_schedule_rule'}.items():latest['staged_weekly'][dest]=decision[src]
    for name,source_name,trigger in [('x3','x3_model_risk_off_watch','new_cross_on_latest_close'),('rv','rv40_dd3_tail_alert','new_trigger_on_latest_close')]:
        alert=monthly['alerts'][source_name];latest['alerts'][name].update(watch=alert['watch'],status=alert['status'],new_trigger=alert[trigger])
    for key in ('raw_entry_condition','rv20_annualized_pct'):latest['alerts']['rv'][key]=monthly['alerts']['rv40_dd3_tail_alert'][key]
    latest['alerts']['interpretation']='X3·RV는 수동 위험 검토용이며 월간·단계형 최종 목표를 자동 변경하지 않습니다.'
    latest['next_check']['if_not_confirmed']=f'현금 {final_cash:g}%·위험자산 한도 {final_risky:g}% 참고비중 유지'
    book=mv['provenance']['workbook'];prov=mv['provenance']
    latest['validation'].update(monthly_status='OK',staged_weekly_status='OK',workbook_last_date=book['last_date'],workbook_rows=book['rows'],workbook_columns=book['columns'],duplicate_date_rows=book['duplicate_date_rows'],missing_numeric_cells=book['missing_numeric_cells'],latest_row_complete=book['latest_row_complete'],workbook_sha256=book['sha256'],monthly_policy_version=monthly['policy_version'],monthly_ma10_policy_sha256=prov['module_sha256']['monthly_ma10_policy'],monthly_runner_sha256=prov['runner_sha256'],strategy_sha256=prov['strategy_sha256'],staged_runner_sha256=sv['inputs']['runner']['sha256'],staged_policy_sha256=sv['inputs']['policy_module']['sha256'],monthly_result_sha256=sha(mp),staged_result_sha256=sha(sp),monthly_validation_sha256=sha(source/'monthly'/trade_date/'validation.json'),staged_validation_sha256=sha(source/'staged'/trade_date/f'validation_{trade_date}.json'),wise_result_sha256=sha(wise_path),publication_scope='VALIDATED_CASH_ONLY_RECOVERY',full_evening_analysis_completed=False,backfilled_dates=dates,dated_kospi_crosscheck='ka20006_and_ka20009_MATCH')
    analysis_path=root/'market-analysis/analysis_latest.json';analysis=read(analysis_path);before=copy.deepcopy(analysis)
    old_cash=analysis['data_validation'].get('cash_weight',{}).get('note')
    old_weight=analysis['data_validation'].get('cash_weight',{})
    analysis['data_validation']['cash_weight']={'trade_date':trade_date,'status':'OK','monthly_cash_pct':primary['target_cash_pct'],'staged_cash_pct':decision['target_cash_pct'],'final_cash_pct':final_cash,'final_risky_pct':final_risky,'automatic_order':False,'note':cash_note,'previous_publication_commit':old_weight.get('source_commit') or old_weight.get('previous_publication_commit'),'workbook_sha256':book['sha256'],'backfilled_dates':dates}
    analysis['risk_flags']=[cash_note if x==old_cash else x for x in analysis['risk_flags']]
    if cash_note not in analysis['risk_flags']:analysis['risk_flags'].append(cash_note)
    analysis['trading_rule']=str(analysis['trading_rule']).split('현금',1)[0]+cash_note
    analysis['source_note']=str(analysis['source_note']).split('\n현금비중 별도 갱신:',1)[0]+f'\n현금비중 별도 갱신: {iso}. 시장분석 기준일 {analysis["as_of"]}은 보존하고 현금 부분만 검증·갱신했습니다.'
    analysis['executive_summary']=[cash_note if ('월간PRIMARY' in text or '월간 PRIMARY' in text) and '현금' in text else text for text in analysis['executive_summary']]
    for key in before:
        if key not in {'data_validation','risk_flags','trading_rule','source_note','executive_summary'}:assert analysis[key]==before[key]
    for key in before['data_validation']:
        if key!='cash_weight':assert analysis['data_validation'][key]==before['data_validation'][key]
    md_path=root/'market-analysis/analysis_latest.md';markdown=md_path.read_text(encoding='utf-8')
    if old_cash:markdown=markdown.replace(old_cash,cash_note)
    markdown='\n'.join(cash_note if line.startswith('월간PRIMARY') and '현금' in line else line for line in markdown.splitlines())
    markdown=markdown.split('\n## 현금비중 별도 갱신 —',1)[0].rstrip()+f'\n\n## 현금비중 별도 갱신 — {iso}\n\n{cash_note}\n\n복원한 거래일: '+', '.join(dates)+'. 시장·추천 내용의 기존 기준일은 변경하지 않았습니다.\n'
    write(latest_path,latest);write(history_path,history);write(analysis_path,analysis);md_path.write_text(markdown,encoding='utf-8')
    return {'status':'LOCAL_CASH_UPDATED_NOT_YET_PUBLISHED','trade_date':trade_date,'backfilled_dates':dates,'history_rows':len(history['records']),'cash_pct':final_cash,'risky_cap_pct':final_risky,'market_analysis_date_preserved':analysis['as_of']}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--cash-root',type=Path,default=Path.home()/'Desktop/trading_strength/output/cash_management');parser.add_argument('--trade-date',required=True);args=parser.parse_args()
    print(json.dumps(refresh(args.root,args.cash_root,args.trade_date),ensure_ascii=False))
