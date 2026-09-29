# System Patterns & Architecture

## 1. 시스템 구조 (Architecture)
- **모노레포 서브디렉토리 분리**: 실제 대시보드 및 수집기 코드는 `worktime_dashboard/` 하위에 위치.
- **루트 진입점 프록시**: 리포지토리 루트의 `app.py` 및 `src/dashboard/app.py`에서 `worktime_dashboard`를 동적 로드하며, 파이썬 모듈 캐시(`sys.modules`)를 무효화하여 최신 코드 즉각 로드 보장.
- **데이터베이스 이원화**:
  - 로컬/기본: SQLite (`data/worklog.db`)
  - 클라우드 동기화: Supabase PostgreSQL 실시간 연동
- **아웃룩 일정 삭제 동기화 패턴**:
  - 수집 범위(동기화 대상 기간 및 실제 캘린더 접근에 성공한 대상 작업자) 내에서, 아웃룩에서 가져온 `entry_id` 목록에 없는 과거 레코드를 감지하여 로컬 SQLite 및 Supabase 양쪽에서 안전하게 자동 삭제(3중 안전 가드: 빈 레코드 시 삭제 금지, 대상 작업자 한정, 수집 기간 한정).


## 2. UI/UX 디자인 원칙
- **버튼 규격 일원화**:
  - 주요 액션 버튼(`📥 엑셀 리포트`, `📧 메일 발송`, `🔄 AI 재분석`)은 너비 약 140px, 높이 38px로 100% 동일 규격 유지.
  - 수평 기준선: `vertical_alignment="bottom"` 또는 `vertical_alignment="center"`로 계단식 어긋남 방지.
  - 텍스트 줄바꿈 방지: `white-space: nowrap !important`
- **컬러 팔레트**: Cisco ACI 스타일 딥 네이비 블루(`#004060` ~ `#005073` 그라데이션) 테마 일관 적용.

## 3. 영구 관찰 규칙 (Task Observer 관찰 신호)
- **금지 어휘**: '경영진' 단어 일체 사용 금지.
- **응답 스타일 (ADHD-Friendly)**:
  - 첫 줄에 사용자가 바로 실행할 명령/코드/경로부터 제시 (서론/사족 없음).
  - 다단계 작업은 번호 목록(1, 2, 3)으로 정리.
  - 미사여구 배제, 답변 끝에는 2분 이내 단일 다음 행동으로 종료.
