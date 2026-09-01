# 📊 카카오톡 작업/지원 시간 분석 및 업무량 모니터링 대시보드

카카오톡 특정 단체방에 올라오는 작업 시작/완료 메시지를 파싱하여, 팀원별 투입 공수(시간), 야간/주말 작업 비중, 고객사별 지원 시간 통계를 실시간으로 집계·시각화하는 대시보드 시스템입니다.

---

## 🌟 주요 기능

1. **카카오톡 메시지 완벽 자동 파싱**:
   - **시작 보고**: `구분 / 담당자 / 고객사 / 상세 작업내용 / N시간 예정` (예: `작업 / 김시우 / KDB생명 / 아시아나 IT동 OS 업그레이드 / 4시간 예정`)
   - **완료 보고**: `N시간 N분 완료` (예: `5시간 30분 완료`)
   - 발화자 프로필(`상상인 김시우 사원 / 기술 1팀`)에서 회사명, 이름, 직급, 소속팀 자동 분리
   - 심야(자정을 넘기는 철야 작업) 및 주말 작업 자동 판별
2. **10분 주기 PC 카카오톡 자동 수집기 (`run_collector.bat`)**:
   - PC 카카오톡이 로그인되어 있고 지정된 채팅방 창이 열려 있으면 10분마다 백그라운드에서 자동 스크래핑 & DB 동기화
3. **Supabase Cloud DB & 로컬 SQLite 하이브리드 지원**:
   - Supabase를 통한 클라우드 데이터 영구 저장 및 다중 환경 공유
   - Supabase 설정 전이어도 로컬 SQLite 모드로 즉시 동작
4. **인터랙티브 웹 대시보드 (`run_dashboard.bat`)**:
   - **핵심 KPI 메트릭**: 총 지원 시간, 총 건수, 1인당 평균 공수, 야간/주말 작업 건수, 예정 대비 초과율
   - **팀원별 업무량 분석**: 누가 가장 많이 일하는지, 야간작업 편중 여부 확인
   - **월별 / 일별 추이 차트**: 시계열 공수 변화 모니터링
   - **고객사별 공수 점유율**: 도넛 차트 및 순위표
   - **예정 vs 실제 시간 편차 산점도**: 과다 소요 작업 원인 분석
   - **엑셀(.xlsx) / CSV 원클릭 내보내기** 및 과거 대화 텍스트 파일 드래그&드롭 일괄 업로드

---

## 🚀 빠른 시작 가이드

### 1. Supabase 연동 설정 (선택 사항 - 클라우드 DB 사용 시)
1. [Supabase 대시보드](https://supabase.com)에 로그인 후 프로젝트를 생성합니다.
2. 좌측 메뉴 **[SQL Editor]**로 이동하여 본 프로젝트의 `supabase_schema.sql` 파일 내용을 붙여넣고 **[Run]**을 실행합니다.
3. 프로젝트 설정(**Project Settings > API**)에서 `Project URL`과 `anon/public API Key`를 복사합니다.
4. `.env` 파일을 열고 아래와 같이 입력합니다:
   ```env
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_KEY=your-supabase-anon-key
   KAKAO_CHAT_TITLE=기술 1팀
   COLLECTOR_INTERVAL_SECONDS=600
   ```

*(※ `.env`를 수정하지 않아도 로컬 SQLite DB로 바로 작동합니다.)*

---

### 2. 웹 대시보드 실행
- `run_dashboard.bat`을 더블 클릭하여 실행합니다.
- 웹 브라우저(`http://localhost:8501`)가 열리며 대시보드가 나타납니다.

---

### 3. PC 카카오톡 10분 자동 수집기 실행
- `run_collector.bat`을 더블 클릭하여 실행합니다.
- PC 카카오톡에서 대상 채팅방 창을 열어두시면 10분마다 자동으로 새 대화를 읽어와 DB에 저장합니다.

---

## 📁 프로젝트 구조

```text
c:\Python\work-time-dashboard\
├── .env                     # Supabase 접속 정보 및 수집기 설정
├── supabase_schema.sql      # Supabase 테이블 및 뷰 생성 쿼리
├── requirements.txt         # 종속성 패키지 목록
├── run_dashboard.bat        # [원클릭] 대시보드 실행 파일
├── run_collector.bat        # [원클릭] 10분 자동 수집기 실행 파일
├── src/
│   ├── config.py            # 환경 설정 로더
│   ├── parser/
│   │   ├── kakao_parser.py  # 카톡 텍스트 & 정규식 파서
│   │   └── reply_matcher.py # 시작/완료 매칭 및 야간/주말 판별 엔진
│   ├── collector/
│   │   └── kakao_auto_collector.py # Windows UI Automation 10분 수집 데몬
│   ├── database/
│   │   └── supabase_client.py # Supabase & SQLite 통합 DB 관리자
│   ├── analytics/
│   │   └── stats_service.py # 월별/팀원별/고객사별 통계 집계 엔진
│   └── dashboard/
│       └── app.py           # Streamlit 인터랙티브 대시보드 UI
└── sample_data/
    ├── sample_kakao_chat.txt # 예시 카카오톡 대화 데이터
    └── generate_sample.py    # 샘플 데이터 생성 유틸리티
```
