# 🚀 Public Repository (PublicRepo)

기술본부 업무 지원 및 자동화 프로젝트 공개 저장소입니다.

---

## 📁 프로젝트 목록 (Projects)

### 1. [work-time-dashboard](./work-time-dashboard/)
- **설명**: 카카오톡 작업/지원 보고 메시지를 기반으로 일별/월별 업무 투입 공수 및 팀원별 업무량을 실시간으로 모니터링하는 인터랙티브 대시보드 시스템
- **주요 기능**:
  - 📊 팀원별/팀별 업무량 분석, 드릴다운 팝업 분석
  - 🚨 과중 근무(주 40h/52h 초과) 실시간 감지 & 원클릭 보상 휴가 등록
  - 🤖 PC 카카오톡 `[기술본부] 업무공유방` 1시간 주기 증분 자동 수집 & 실시간 즉시 긁어오기
  - 💾 독립 로컬 SQLite 고성능 데이터베이스 (`data/worklog.db`) 내장
- **실행 방법**:
  ```bash
  cd work-time-dashboard
  pip install -r requirements.txt
  streamlit run src/dashboard/app.py
  ```
  또는 루트의 `run_dashboard.bat` 더블 클릭!
