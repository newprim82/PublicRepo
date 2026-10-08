# PublicRepo

엔터프라이즈 업무 자동화 및 관제 대시보드 모노레포(Monorepo) 저장소입니다.

---

## 📁 프로젝트 목록

### 📊 [worktime_dashboard (v2.5.5)](./worktime_dashboard)
- **기술본부 업무량 & 현장 지원 시간 실시간 관제 대시보드 (Cisco ACI / Catalyst Center 테마)**
- 카카오톡 실시간 업무 보고와 Microsoft Outlook / Teams 캘린더 일정을 10분마다 자동 수집/연동하여 과거-현재-미래 3단계 시간축 모니터링을 제공하는 웹 포털
- **주요 기능**:
  - **LIVE 관제 (현재시)**: 09:00 정각 LIVE 승격, 카톡/아웃룩 중복 배제, 18:00 휴가 카드 자동 이동
  - **KPI & 과중근무 모니터링 (과거시)**: 주 40h/52h 2단계 알림 배너, 교육/휴가 법정 근로시간 자동 공제
  - **통합 캘린더 (미래시)**: 전 팀원 미래 일정 고대비 7색 스펙트럼 캘린더
  - **초고속 페이지 전환**: `@st.cache_data` 기반 필터 캐싱 및 관리자 페이지 지연 연산 (0ms 즉시 반환)
  - **12대 특화 화면**: 분석, 관리, 비용산정, 시스템 설정 등 역할 기반 화면 분리
  - **단위 테스트 스위트**: 25개 핵심 비즈니스 로직 테스트 100% 통과 상시 보장

#### 🚀 빠른 실행
- **대시보드 업데이트 및 실행 (권장)**:
  ```cmd
  update_and_run.bat
  ```
- **대시보드 단독 실행**:
  ```cmd
  run_dashboard.bat
  ```
- **카톡 수집기 단독 실행**:
  ```cmd
  run_collector.bat
  ```
- **단위 테스트 실행**:
  ```cmd
  cd worktime_dashboard && python -m unittest discover tests
  ```
