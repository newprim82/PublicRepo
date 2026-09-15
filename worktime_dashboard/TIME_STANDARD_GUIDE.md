# ⏰ 기술본부 대시보드 영구 시간 표준 가이드 (Permanent Time Standard)

> **[CRITICAL DIRECTIVE / 불변 원칙]**  
> 본 프로젝트의 모든 시간 연산, 실시간 관제 시계, 수집 로그, 알림 및 타임스탬프는  
> **`time.bora.net` (LGU+ NTP 타임서버)** 기반의 **한국 표준시(KST, UTC+09:00)**를 단일 진실 소스(Single Source of Truth)로 영구 고정합니다.  
> 이 원칙은 본 프로젝트가 끝날 때까지 절대 변경되지 않으며, 모든 모듈과 서브시스템에 동일하게 적용됩니다.

---

## 1. 표준 시간 정의 및 원칙

| 항목 | 표준 규격 | 세부 내용 |
| :--- | :--- | :--- |
| **타임 서버 (NTP)** | `time.bora.net` | 대한민국 LGU+ 공식 NTP 서버 (UDP 포트 123) |
| **타임존 (Timezone)** | **KST (UTC+09:00)** | 대한민국 표준시 (Asia/Seoul) |
| **시간 객체 원칙** | **KST 기준 Tz-Naive** | Pandas/SQLite/Supabase 컬럼 뺄셈 연산 시 `TypeError: Cannot subtract tz-naive and tz-aware` 방지를 위해 기본 반환형을 KST naive datetime으로 단일화 |
| **시간 유틸 모듈** | `src.common.time_utils` | 프로젝트 전역 공용 표준 모듈 |

---

## 2. 모듈별 표준 함수 사용법

모든 파이썬 코드에서 `datetime.now()` 또는 `datetime.utcnow()`의 직접 호출을 지양하고, 반드시 `src.common.time_utils`를 임포트하여 사용합니다.

```python
from src.common.time_utils import get_current_kst_time, to_naive_kst, get_current_kst_time_aware

# 1. 현재 KST 시각 조회 (기본: naive datetime, Pandas 연산 최적화)
now_kst = get_current_kst_time()  # 예: datetime(2026, 9, 8, 21, 30, 0)

# 2. 임의의 날짜/시간 값(문자열, 타임스탬프, aware/naive)을 안전하게 KST naive로 정규화
clean_dt = to_naive_kst(record["start_time"])

# 3. 시간 차이 연산 (TypeError 원천 차단)
elapsed = now_kst - clean_dt

# 4. 외부 API 연동 등 타임존 메타데이터가 명시적으로 필요한 경우에만 aware 사용
now_aware = get_current_kst_time_aware()  # tzinfo=timezone(timedelta(hours=9))
```

---

## 3. 동기화 및 캐싱 매커니즘

1. **소켓 기반 고속 NTP 동기화**:
   - `time.bora.net` 서버로 직접 48바이트 NTP UDP 패킷을 송수신하여 0.1초 미만의 고정밀 타임스탬프를 획득합니다.
2. **오프셋 캐싱 (1시간 주기)**:
   - 과도한 외부 네트워크 트래픽 및 지연을 방지하기 위해 로컬 머신 시계와의 오차(Offset)를 1시간 동안 메모리에 캐싱합니다.
3. **무중단 폴백 (Fail-safe)**:
   - 외부망 차단 또는 NTP 서버 일시 미응답 시 시스템 시계에 KST(+9시간)를 보정한 값으로 자동 폴백되어 서비스 중단이 발생하지 않습니다.

---

## 4. 적용 완료 모듈 현황

- `src/common/time_utils.py`: 표준 NTP 소켓 클라이언트 및 KST 변환 코어
- `src/dashboard/common/ui_helpers.py`: 대시보드 UI 전역 시간 헬퍼 연동
- `src/dashboard/common/dialogs.py`: 24시간 초과 미마감 모달 등 시간 계산
- `src/dashboard/views/home_view.py`: 실시간 LIVE 관제 타이머 및 방치 작업 감지
- `src/collector/kakao_auto_collector.py`: 카카오톡 수집기 다음 주기 계산 및 로깅
- `src/collector/outlook_auto_collector.py`: 아웃룩 캘린더 동기화 주기 및 기간 필터링
- `src/parser/kakao_parser.py`: 대화 파싱 기준 시점
- `src/parser/reply_matcher.py`: 미완료 건 자동 완료 전환 시점 판정
- `src/parser/multiday_splitter.py`: 다일 작업 분할 기준 시점
- `src/database/supabase_client.py`: DB 레코드 만료 판정
- `src/services/collector_status_service.py`: 수집기 헬스체크 타임스탬프
