# Active Context (기준 시점: 2026-10-17 / v2.6.3)

## 1. 최근 완료된 핵심 작업 내역 (2026-10-08 ~ 2026-10-17)

- **전체 앱 2차 종합 개선: 체감 속도 혁신, 아웃룩 일정 전수 페이지네이션, 월간 자동발송 복구 및 장기 구동 안정화 (`5afe8fb`)**:
  - **다중 시트 엑셀 사전 생성 병목 제거**: `summary_view.py`, `cost_estimation_view.py`, `monthly_worklog_dispatch_view.py`에서 화면 진입/클릭 시마다 무거운 `openpyxl` 엑셀 파일을 매번 새로 생성하던 병목을 `@st.cache_data` 캐싱으로 제거하여 화면 전환 및 셀 클릭 반응 속도 대폭 향상.
  - **수집기 상태 조회 30초 메모리 캐시 적용**: `collector_status_service.py`에 30초 인메모리 캐시(`CACHE_TTL = 30.0`)를 도입하여 매 클릭마다 발생하던 Supabase 네트워크 왕복 지연(200~400ms) 제거.
  - **아웃룩 일정 1,000건 초과 시 최신 일정 증발 버그 수정**: `supabase_client.py`의 `fetch_outlook_schedules` 및 삭제 동기화에 1,000건 단위 연속 조회(Pagination) 루프를 적용하고, 월말~월초 걸친 일정 누락 방지를 위해 기간 필터를 `start_time` 기준으로 통일.
  - **매월 1일 08:00 전월 업무원장 자동 발송 워크플로우 신설 및 개인정보 보호**: `.github/workflows/monthly_team_worklog.yml`을 신설하여 매달 1일 오전 8시(KST) 무인 자동 발송 파이프라인을 완결하고, `monthly_worklog_service.py`에서도 다중 수신자 개별 발송(`_send_to_all`) 적용.
  - **표준 시간(NTP) UDP 소켓 리소스 누수 해결**: `time_utils.py`에서 `with socket.socket(...) as client:` 컨텍스트 매니저를 적용하여 `ResourceWarning: unclosed <socket.socket>` 누수 원천 해소.
  - **로컬 SQLite 동시성(WAL) 및 타임아웃 강화**: `supabase_client.py`의 로컬 DB 초기화 시 `PRAGMA journal_mode=WAL;` 및 `timeout=15.0`을 적용하여 백그라운드 수집기와 웹 화면 간 동시 쓰기 잠금(`database is locked`) 방지.

- **보안 자격증명 격리, 런타임 안정화, 개인정보 보호 및 파서 결함 전수 해결 (`b3f31f9`)**:
  - **자격증명 하드코딩 제거**: `config.py`, `send_weekly_report.py`, `weekly_email_report.yml` 내 실제 Gmail 앱 비밀번호 하드코딩 완전 제거 및 환경변수/GitHub Secrets 단독 참조로 유출 위험 원천 차단.
  - **최고 관리자 기본 비밀번호 환경변수화**: `auth_manager.py`의 `DEFAULT_SUPER_ADMIN_PWD`를 `SUPER_ADMIN_INITIAL_PWD` 환경변수로 격리.
  - **클라우드 데몬 수집기 상태 플래핑 차단**: `kakao_auto_collector.py`에 Non-Windows(리눅스/클라우드) 감지 즉시 안전 반환 가드를 적용하여, 사내 윈도우 수집기의 정상 `ONLINE` 상태를 클라우드가 `ERROR`로 덮어쓰는 플래핑 현상 해결.
  - **URL 세션 토큰 노출 방어**: `auth_manager.py`에서 로그인 및 세션 복원 즉시 브라우저 주소창(`st.query_params`)에서 `session_token`을 자동 제거하여 화면 캡처 및 링크 공유로 인한 세션 하이재킹 원천 차단.
  - **단체 메일 발송 수신자 개인정보 보호**: `email_sender.py`에서 다중 수신자 발송 시 1회의 SMTP 연결 세션 내에서 각 수신자별 개별 발송(`_send_to_all`) 처리하여 타인의 이메일 주소 노출 방어.
  - **카카오톡 소요시간 단위 생략 오인식 방어**: `kakao_parser.py`에서 "방화벽 1 완료", "스위치 1대 완료", "서버 1차 완료" 등 식별자/차수/수량이 근무시간으로 오인식되지 않도록 문맥 필터 강화 및 단위 테스트 6건 보강.

- **제로-트러스트 비용 보안 금고 (Zero-Knowledge Encryption Vault) 구축 및 고도화 (`47a622a` ~ `821d2e2`)**:
  - `src/services/cost_vault_service.py`: 군사 표준 PBKDF2(600,000회) + AES-256-GCM 기반 영지식 보안 금고 엔진 구축.
  - 서버 PC 및 Supabase 클라우드 DB가 통째로 탈취당해도 단가 및 청구 금액이 노출되지 않도록 브라우저 RAM 상에서만 일회성 복호화.
  - 무차별 대입(Brute-Force) 방어: 연속 5회 비밀번호 오입력 시 세션 단위 즉각 잠금 및 지연 시간 적용.
  - 최고 관리자(`newprim`) 전용 권한 격리: `AuthManager.is_super_admin()` 로직을 오직 `is_authenticated()` 및 ID 일치로 엄격화하여 일반 관리자(`ADMIN`)나 미인증(`GUEST`) 상태에서 금고 초기화 UI 노출을 원천 차단 (`1cdbafb`).
  - 비용산정 상단 헤더 액션 바 다이나믹 자동 확장 (`821d2e2`): 3컬럼 직분할(`[3.5, 2.7, 3.8]`) 및 인라인 스타일(`width: 100% !important; min-width: max-content !important; white-space: nowrap !important;`) 적용으로 좁은 창에서도 자물쇠 버튼 말줄임(`...`) 및 요약 박스 `(8명)` 줄바꿈 원천 해결.

- **보안 취약점 15종 종합 패치 및 방어벽 구축 (`67a8eb4`, `faff9e0`, `d6e20fd`)**:
  - SMTP 인증 정보 하드코딩 완전 제거 (환경변수화 및 Supabase 클라우드 DB 실시간 동기화).
  - Git 추적 파일에서 계정 및 로컬 백업 잔여 데이터 완전 제거.
  - 세션 상태 변조 방지 해시 검증 도입, XSS 취약점 차단 및 HTML 이스케이프 안전망 적용.
  - 단위 테스트 격리: 테스트 스위트 실행 시 프로덕션 클라우드 DB 및 로컬 보안 금고 파일 오염 방지 모킹(Mocking) 적용.

- **전 화면 단일 셀 클릭 기반 즉각 드릴다운 팝업 모달 UX 표준화 (`17ff86c` ~ `aaa7770`)**:
  - 대시보드 전체 테이블(`dataframe`)에 `selection_mode="single-cell"`을 적용하여 마우스 클릭 즉시 상세 작업 팝업 다이얼로그 연동.
  - `@st.fragment` 적용으로 테이블 행/셀 클릭 시 전체 페이지 리로드 없이 모달만 0ms 체감 속도로 즉각 팝업.
  - 다이얼로그 닫기 시 동적 키 버전 업 및 세션 리셋을 통해 동일 셀 재클릭 및 반복 팝업 동작 보장.

- **아웃룩 동기화 결합도 분리 및 캘린더 위젯 고도화 (`4ed5460`, `82d43ff`, `d502589`)**:
  - 카카오톡 윈도우 창 활성 상태와 아웃룩 일정 동기화의 결합도를 완전히 분리하여, 카카오톡 창이 닫혀 있어도 아웃룩 단독 일정 동기화 정상 수행.
  - 사이드바의 팀 및 팀원 필터 선택 시 아웃룩 캘린더 위젯이 실시간으로 상호 연동되어 동기화되도록 바인딩.

- **주간 무인 자동 이메일 리포트 복구 (`b6accbb`)**:
  - GitHub Actions 워크플로우(`weekly_email_report.yml`) 복구 및 신규 수신자 Supabase 클라우드 동기화 파이프라인 정상화.

- **UI/UX 정렬 및 레이아웃 결함 개선 (`711f116`, `512530a`)**:
  - Dataframe 및 Plotly 차트에 레이아웃 왜곡을 주던 CSS zoom 속성 제거.
  - 비용산정 화면의 좌측 요약 테이블과 우측 차트 박스의 상단 및 하단 높이를 1:1 완벽 정렬.

- **작업 유형(Work Type) 10대 카테고리 및 8대 기술 도메인 태깅 엔진 완성 (`34eeab6` ~ `3093663`)**:
  - `교육 / 세미나` 독립 카테고리 신설 (총 10대 작업 유형 체계).
  - 8대 기술/장비 도메인 자동 분류 및 Summary 화면 다차원 교차 분석표 상시 노출.

- **단위 테스트 스위트 확장 및 품질 보증**:
  - 보안 금고, 인증 매니저, 일정 동기화, 카톡 파서, 필터 캐싱 등 **총 38개 단위 테스트 100% 통과 (`Ran 38 tests in ~3s, OK`)**.

---

## 2. 현재 시스템 상태 (Current State)

- **애플리케이션 버전**: `v2.6.3`
- **단일 진실 소스 시간**: LGU+ 공식 NTP `time.bora.net` (KST Naive datetime, UDP 소켓 자동 종료 보장)
- **보안 상태**: 자격증명 완전 환경변수화, 제로-트러스트 영지식 암호화 금고 가동 (AES-256 / PBKDF2), URL 세션 토큰 노출 차단, 주간·월간 이메일 개별 전송 프라이버시 보호
- **런타임 및 성능 상태**: 클라우드 데몬 플래핑 원천 차단, 다중 엑셀 생성 `@st.cache_data` 캐싱, 수집기 상태 30초 메모리 캐싱, 아웃룩 일정 전수 페이지네이션, SQLite WAL 동시성 모드 가동
- **자동화 파이프라인**: 매주 월요일 주간 리포트(`weekly_email_report.yml`) + 매월 1일 08:00 전월 업무원장(`monthly_team_worklog.yml`) 무인 발송 완비
- **화면 구성**: 12대 메뉴 (역할 기반 접근 제어: 일반 관제 / 관리자 / 최고관리자)
- **테스트 현황**: 38/38 Tests Passing (100% 통과, OK, 리소스 누수 경고 0건)
- **Git 브랜치**: `main` (최신 커밋: `5afe8fb`)

---

## 3. 진행 중 및 향후 계획 (Next Steps)

1. **클라우드 호스팅 모니터링**:
   - Streamlit Community Cloud 상에서의 실시간 배포 및 제로-트러스트 보안 금고 정상 작동 상태 지속 점검.
2. **차기 인프라 전환 준비**:
   - 사내 리눅스 VM 환경 Docker 전환 및 안드로이드 공기계(메신저봇R) 수집 파이프라인 수립 검토.

