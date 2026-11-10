# 리포트 갱신 (2026-11-10)

오전 08:40에는 당일 리포트뿐 아니라 누적 리포트 검색과 목표주가 상향·하향을 함께 갱신한다. DAJU 오후 20:00 작업은 유지한다.

1. 최신 main의 깨끗한 checkout과 기존 파일을 확보한다. 배치 4종은 실행하지 않는다.
2. `scripts/collect_hankyung_daily.py --root <checkout> --archive <telegram-archive/data/hankyung/runs>`를 프로젝트 가상환경 Python으로 실행한다. 최근 5일 기본 조회이며 긴 누락은 마지막 확보일 다음 날부터 `--start YYYY-MM-DD --end YYYY-MM-DD`로 복구한다.
3. DAJU `collect.py`를 실행하고 실행별 validation, 원본 해시, 중복 ID를 검사한다. 공개 미리보기 범위이며 전체 이력 전수 수집이 아니다.
4. 같은 checkout에서 `scripts/merge_hankyung_reports.py --run <이번 한경 run> --messages <DAJU messages.json> --apply`를 실행한다. 한경 원본 해시와 재파싱을 검사하고 기존 행을 보존한다. 목표가 0원·결측·방향 충돌은 보류한다. 감사 결과는 해당 run의 `report_merge` 아래에 보존한다.
5. 전체 리포트 요약을 재계산한다. 분기는 명시된 실적 분기와 공시 요약 시각으로만 분류한다. 분기 미확인 자료는 별도 보관하고, 발표 당일 전후 미확인과 실적 대상 분기/발표 이후 구간을 구분한다. 회사별 공시 원문 독립 검증을 했다고 표현하지 않는다.
6. 사용자 제공 QA 인증을 실행 환경 `JS_DASHBOARD_QA_PASSWORD`로만 전달한다. `node scripts/verify_report_dashboard.cjs local <QA폴더>`와 `node scripts/verify_daily_reports.cjs local <QA폴더>`로 PC·모바일 검색·최고가·분기·상하향·펼치기·오류를 확인한다. 인증 미확보 또는 검증 실패는 게시 보류하고 구체적으로 보고한다.
7. 의미 있는 변경이 있을 때만 `report_data.json`, `report_signal_data.json`, `report-periods/data.json`, `daily-reports/latest.json`을 명시해 스테이징한다. 코드 변경은 별도 검토한 대상만 포함한다. 기존 행 보존·JSON·6자리 코드·중복·최신 날짜·git diff 확인 후 commit/push한다.
8. 해당 SHA Pages 성공 후 두 검증기에 `https://jsinvest.github.io/dashboard/`를 전달해 공개 DOM을 재검증한다. 카카오 후보가 없어도 대시보드 갱신은 수행한다. 카카오 전송은 별도 검증된 전달 절차를 통과한 경우에만 하며 이 병합기가 발송하지는 않는다.

2026-11-10 복구: 2026-08-26부터 11-10까지 한경 상향·하향 목록. 이는 모든 증권사 전체 리포트 수집이 아니다. SEIBro·NAVER·IRGO는 별도 실제 수집/필드 검증 전 자동 원천으로 표시하지 않는다.
