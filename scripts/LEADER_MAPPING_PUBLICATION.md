# 주도주 장중 맵 게시 조건

2026-11-03 사용자 요청에 따라 저녁 2단계 완료를 장중 맵의 필수조건에서 분리했습니다.

- 필수: 당일 원본 엑셀 내용·중복·결측·운영 표본 누락·실제 해시, KRX 거래일, 누적 파일 내용 검증.
- 저녁 지수 종가·신고가 캐시·14단계는 장중 원본의 필수 입력이 아닙니다. 실패하거나 오래되면 보조층만 제외합니다.
- 생성기 검증이 없으면 종가 확정이나 원시봉 검증 완료로 승격하지 않습니다. 화면에 실제 파일 생성시각과 종가 확정 미검증을 표시합니다.
- 통합기의 status=OK와 data_status를 별도로 기록합니다. 소비자 검증은 leader-mapping/validation_latest.json이며 생성기 증명을 대체하지 않습니다.
- build_leader_mapping.py는 날짜·행수·시장별 TOP5·대표종목을 입력에서 구합니다. 원래 상대강도 산식은 leader_mapping_data.py에 보존하며 추천·현금비중을 변경하지 않습니다.
- 당일 V2만 교차 표시하고 역사 파일은 날짜별 한 번 집계합니다. 스팩을 사업섹터에서 제외하고 원본 분류와 보완분류를 섞지 않습니다.
- 공개 DOM 검증 및 Pages 성공 전 완료로 보고하지 않습니다. 원본·검증파일 조작, 배치 재실행과 과거 값을 오늘 값으로 대체하는 것은 금지합니다.

실행: Python scripts/build_leader_mapping.py --trade-date YYYYMMDD --source-root 원천폴더 --integration-dir 통합후처리폴더 --calendar KRX검증JSON

별도 최신 원격 main 작업 폴더에서 생성하고 index.html, leader-mapping/validation_latest.json 및 변경한 주도주 스크립트만 게시합니다.
