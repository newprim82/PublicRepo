from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any
from ..common.time_utils import get_current_kst_time


@dataclass
class OutlookScheduleRecord:
    """아웃룩 캘린더 약속/일정 정규화 레코드"""
    entry_id: str                      # 아웃룩 EntryID (고유 식별자)
    worker_name: str                   # 작업자/팀원 이름 (예: 김시우, 홍정표 등)
    worker_team: str = "미배정"         # 소속 팀 (기술 1팀, 기술 2팀 등)
    subject: str = ""                  # 일정 제목
    schedule_type: str = "작업"        # 작업 / 휴가 / 회의 / 교육 / 기타
    start_time: str = ""               # 'YYYY-MM-DD HH:MM:SS'
    end_time: str = ""                 # 'YYYY-MM-DD HH:MM:SS'
    duration_hours: float = 0.0        # 소요/예정 시간 (h)
    is_all_day: bool = False           # '종일' 체크 여부 (종일 시 09:00~18:00 자동 적용)
    is_leave: bool = False             # 휴가/연차/반차 여부
    leave_type: str = ""               # 연차 / 오전반차 / 오후반차 / 휴가 / None
    location: str = ""                 # 고객사 / 장소
    body: str = ""                     # 본문 메모
    color_tag: str = "#0284c7"         # 팀원별 캘린더 대표 색상 (#hex)
    created_by: str = ""               # 주최자 / 등록자
    synced_at: str = field(default_factory=lambda: get_current_kst_time().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환 (DB Upsert 및 JSON 직렬화용)"""
        return asdict(self)
