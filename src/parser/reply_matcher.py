import re
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

from .kakao_parser import (
    KakaoMessageParser,
    RawKakaoMessage,
    ParsedTaskStart,
    ParsedTaskEnd,
    WorkerInfo
)

@dataclass
class WorkLogRecord:
    msg_hash: str
    log_type: str
    worker_name: str
    worker_title: str
    worker_team: str
    client_name: str
    task_description: str
    estimated_minutes: int
    actual_minutes: int
    start_time: datetime
    end_time: Optional[datetime]
    status: str                       # 'COMPLETED' or 'PENDING'
    is_night_work: bool
    is_weekend_work: bool
    raw_start_message: str
    raw_end_message: str
    worker_company: str = ""          # 하위 호환용 (DB 저장 및 표출 대상 제외)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['start_time'] = self.start_time.strftime("%Y-%m-%d %H:%M")
        d['end_time'] = self.end_time.strftime("%Y-%m-%d %H:%M") if self.end_time else None
        d.pop('worker_company', None)
        return d


def check_is_night_work(
    start_dt: datetime,
    end_dt: Optional[datetime] = None,
    raw_message: str = "",
    estimated_minutes: int = 0,
    actual_minutes: int = 0
) -> bool:
    """
    사용자 지정 야간 판정 기준:
    1. ★ 시작 보고 시각 조건: 18:00 이후 ~ 익일 06:00 사이에 시작 보고가 시작되어야 함
       - 당일 18:00~23:59:59 또는 자정 넘어 00:00~05:59:59
       - 06:00 이후(예: 06:10, 07:00, 08:30 등) 시작 작업은 주간 작업으로 분류(False)!
    2. ★ 작업 시간 조건: [18:00 ~ 익일 06:00] 야간 윈도우 내에서 일한 시간이 1시간(60분) 이상이어야 함!
       - 18시 이후에 시작했더라도 야간 근무 시간이 1시간 미만(예: 30분, 45분)이면 야간 아님(False)!
    3. ★ 절대 규칙: 'day', 'days', 다일(16시간 이상) 작업은 주간 연속 지원 업무이므로 야간 작업에서 무조건 제외(False)!
    """
    # 0. 타입 및 타임존 안전 정규화 (str / Timestamp / tz-aware -> naive datetime)
    if isinstance(start_dt, str):
        start_dt = pd.to_datetime(start_dt)
    if hasattr(start_dt, "to_pydatetime"):
        start_dt = start_dt.to_pydatetime()
    if getattr(start_dt, "tzinfo", None) is not None:
        start_dt = start_dt.replace(tzinfo=None)

    if end_dt is not None:
        if isinstance(end_dt, str):
            end_dt = pd.to_datetime(end_dt)
        if hasattr(end_dt, "to_pydatetime"):
            end_dt = end_dt.to_pydatetime()
        if getattr(end_dt, "tzinfo", None) is not None:
            end_dt = end_dt.replace(tzinfo=None)

    # 1. day / days 표기 작업 무조건 야간 제외
    if raw_message:
        low = raw_message.lower()
        if any(k in low for k in ["day", "days", "2일", "3일", "4일", "5일"]):
            return False

    # 2. 예정 시간 또는 실제 소요 시간이 16시간 이상인 다일 작업 제외
    if estimated_minutes >= 16 * 60 or actual_minutes >= 16 * 60:
        return False

    # 3. 시작 시각 윈도우 검사 (18시 이후 ~ 익일 06시 이전 시작)
    if not (start_dt.hour >= 18 or start_dt.hour < 6):
        return False

    # 실제 작업 종료 시각 산출 (카톡 늦게 올린 시각이 아닌 실제 작업 소요시간 기준)
    if actual_minutes > 0:
        effective_end_dt = start_dt + timedelta(minutes=actual_minutes)
    elif end_dt and end_dt > start_dt and (end_dt - start_dt).total_seconds() <= 16 * 3600:
        effective_end_dt = end_dt
    elif estimated_minutes > 0:
        effective_end_dt = start_dt + timedelta(minutes=estimated_minutes)
    else:
        effective_end_dt = start_dt

    # 총 소요시간이 16시간을 초과하는 다일 작업 제외
    if (effective_end_dt - start_dt).total_seconds() / 3600.0 > 16.0:
        return False

    # 4. [18:00 ~ 익일 06:00] 야간 윈도우와 작업 시간 겹침 계산
    if start_dt.hour >= 18:
        w_start = start_dt.replace(hour=18, minute=0, second=0, microsecond=0)
        w_end = (start_dt + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
    else:  # start_dt.hour < 6
        w_start = (start_dt - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        w_end = start_dt.replace(hour=6, minute=0, second=0, microsecond=0)

    overlap_start = max(start_dt, w_start)
    overlap_end = min(effective_end_dt, w_end)

    if overlap_end > overlap_start:
        overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60.0
        return overlap_minutes >= 60.0  # 1시간 이상 근무 시 True

    return False


def check_is_weekend_work(
    start_dt: datetime,
    end_dt: Optional[datetime] = None,
    raw_message: str = "",
    estimated_minutes: int = 0,
    actual_minutes: int = 0
) -> bool:
    """
    사용자 지정 주말 판정 기준:
    - 작업 진행 구간 [start_dt ~ effective_end_dt] 중 주말(토/일) 시간이 1시간(60분)이라도 껴있으면 무조건 주말 작업(True)!
    - 예: 금요일 23:00 시작 ~ 토요일 03:00 종료 (토요일에 3시간 근무 ➔ 주말 작업 인정!)
    - 예: 일요일 22:00 시작 ~ 월요일 02:00 종료 (일요일에 2시간 근무 ➔ 주말 작업 인정!)
    """
    # 0. 타입 및 타임존 안전 정규화 (str / Timestamp / tz-aware -> naive datetime)
    if isinstance(start_dt, str):
        start_dt = pd.to_datetime(start_dt)
    if hasattr(start_dt, "to_pydatetime"):
        start_dt = start_dt.to_pydatetime()
    if getattr(start_dt, "tzinfo", None) is not None:
        start_dt = start_dt.replace(tzinfo=None)

    if end_dt is not None:
        if isinstance(end_dt, str):
            end_dt = pd.to_datetime(end_dt)
        if hasattr(end_dt, "to_pydatetime"):
            end_dt = end_dt.to_pydatetime()
        if getattr(end_dt, "tzinfo", None) is not None:
            end_dt = end_dt.replace(tzinfo=None)

    # 실제 작업 종료 시각 산출
    if actual_minutes > 0:
        effective_end_dt = start_dt + timedelta(minutes=actual_minutes)
    elif end_dt and end_dt > start_dt and (end_dt - start_dt).total_seconds() <= 16 * 3600:
        effective_end_dt = end_dt
    elif estimated_minutes > 0:
        effective_end_dt = start_dt + timedelta(minutes=estimated_minutes)
    else:
        effective_end_dt = start_dt + timedelta(minutes=60) if start_dt.weekday() in [5, 6] else start_dt

    cur_date = start_dt.date()
    end_date = effective_end_dt.date()

    weekend_minutes = 0.0
    while cur_date <= end_date:
        if cur_date.weekday() in [5, 6]:  # 토(5) 또는 일(6)
            day_start = datetime.combine(cur_date, datetime.min.time())
            day_end = datetime.combine(cur_date, datetime.max.time())

            overlap_s = max(start_dt, day_start)
            overlap_e = min(effective_end_dt, day_end)
            if overlap_e > overlap_s:
                weekend_minutes += (overlap_e - overlap_s).total_seconds() / 60.0

        cur_date += timedelta(days=1)

    return weekend_minutes >= 60.0


from ..services.client_normalizer import normalize_client_name


def generate_msg_hash(worker_name: str, client_name: str, start_dt: datetime, task_desc: str) -> str:
    norm_client = normalize_client_name(client_name) if client_name else ""
    unique_str = f"{worker_name.strip()}_{norm_client.strip()}_{start_dt.strftime('%Y%m%d_%H%M')}_{task_desc.strip()[:20]}"
    return hashlib.sha256(unique_str.encode('utf-8')).hexdigest()[:16]


def get_pending_timeout_hours(p_start) -> float:
    """
    미완료 시작 보고의 자동 완료 대기 제한 시간(hours) 산출:
    - 기본 일반 당일 작업 (1일 이하, <= 9h): 48.0시간 (2일)
    - 다일(Multi-day) 장기 작업 (1.5days 이상 또는 13.5h 이상):
      공식: max(48.0, (예정일수 * 24.0) + 48.0)  (여유 +48시간 보장)
      예: 3days (27h) -> (3.0 * 24.0) + 48.0 = 120.0시간 (5일 동안 PENDING 대기 유지)
    """
    raw_msg = getattr(p_start, "raw_message", "") or ""
    est_mins = getattr(p_start, "estimated_minutes", 0) or 0

    # 1. 메시지 본문에서 'N days / N일' 패턴 직접 탐색
    m_day = re.search(r'(\d+(?:\.\d+)?)\s*(?:days?|d(?![a-zA-Z])|D|일)', raw_msg, re.IGNORECASE)
    if m_day:
        try:
            est_days = float(m_day.group(1))
        except ValueError:
            est_days = 1.0
    elif est_mins >= 810:  # 1.5일(13.5시간) 이상
        est_days = est_mins / 540.0
    else:
        est_days = 1.0

    if est_days >= 1.5:
        return max(48.0, (est_days * 24.0) + 48.0)
    return 48.0


class WorkLogMatcher:
    @classmethod
    def match_messages(cls, raw_messages: List[RawKakaoMessage]) -> List[WorkLogRecord]:
        sorted_msgs = sorted(raw_messages, key=lambda m: m.timestamp)
        
        pending_starts: List[ParsedTaskStart] = []
        matched_records: List[WorkLogRecord] = []
        
        for msg in sorted_msgs:
            # 1. 시작 보고 파싱
            task_starts = KakaoMessageParser.parse_task_starts(msg)
            if task_starts:
                for ts in task_starts:
                    # 시작 메시지 자체에 '완료' 또는 '소요'가 직접 적힌 경우 즉시 COMPLETED 생성
                    if ts.is_direct_completed and ts.direct_actual_minutes > 0:
                        msg_hash = generate_msg_hash(ts.worker_name, ts.client_name, ts.timestamp, ts.task_description)
                        is_night = check_is_night_work(ts.timestamp, ts.timestamp, ts.raw_message, ts.estimated_minutes, ts.direct_actual_minutes)
                        is_weekend = check_is_weekend_work(ts.timestamp, ts.timestamp, ts.raw_message, ts.estimated_minutes, ts.direct_actual_minutes)
                        matched_records.append(WorkLogRecord(
                            msg_hash=msg_hash,
                            log_type=ts.log_type,
                            worker_name=ts.worker_name,
                            worker_company=ts.worker_info.company,
                            worker_title=ts.worker_info.title,
                            worker_team=ts.worker_info.team,
                            client_name=ts.client_name,
                            task_description=ts.task_description,
                            estimated_minutes=ts.estimated_minutes,
                            actual_minutes=ts.direct_actual_minutes,
                            start_time=ts.timestamp,
                            end_time=ts.timestamp,
                            status="COMPLETED",
                            is_night_work=is_night,
                            is_weekend_work=is_weekend,
                            raw_start_message=ts.raw_message,
                            raw_end_message=ts.raw_message
                        ))
                    else:
                        # 1. 동일 작업자의 기존 대기 중인 시작 보고 확인
                        duplicate_target = None
                        prev_different_starts = []
                        for existing in pending_starts:
                            if existing.worker_name == ts.worker_name:
                                is_same_task = (
                                    existing.client_name == ts.client_name and
                                    existing.task_description == ts.task_description
                                )
                                if is_same_task and (ts.timestamp - existing.timestamp).total_seconds() <= 48 * 3600:
                                    duplicate_target = existing
                                    break
                                else:
                                    # ★ 사용자 지정 규칙: 동일 작업자가 완료보고 없이 다른 새 작업을 시작하면
                                    # 첫 번째 시작 보고의 예정 시간대로 완료 처리!
                                    prev_different_starts.append(existing)
                                
                        if duplicate_target:
                            # 기존 시작 보고의 group_id를 그대로 상속하여 완료 보고 매칭 시 최초 시작일시로 귀속되도록 함
                            ts.task_group_id = duplicate_target.task_group_id
                            ts.timestamp = duplicate_target.timestamp
                            pending_starts.remove(duplicate_target)
                            pending_starts.append(ts)
                        else:
                            # 이전 미완료 작업들을 예정시간 기준으로 자동 완료 전환
                            for prev in prev_different_starts:
                                pending_starts.remove(prev)
                                if prev.estimated_minutes > 0:
                                    auto_actual = prev.estimated_minutes
                                else:
                                    # 예정시간이 생략된 경우: (다음 시작 보고 시각 - 이전 시작 보고 시각)
                                    diff_mins = int((ts.timestamp - prev.timestamp).total_seconds() / 60.0)
                                    if 10 <= diff_mins <= 16 * 60:
                                        auto_actual = diff_mins
                                    else:
                                        auto_actual = 60
                                auto_end_time = prev.timestamp + timedelta(minutes=auto_actual)
                                
                                msg_hash = generate_msg_hash(
                                    prev.worker_name,
                                    prev.client_name,
                                    prev.timestamp,
                                    prev.task_description
                                )
                                is_night = check_is_night_work(prev.timestamp, auto_end_time, prev.raw_message, prev.estimated_minutes, auto_actual)
                                is_weekend = check_is_weekend_work(prev.timestamp, auto_end_time, prev.raw_message, prev.estimated_minutes, auto_actual)
                                
                                matched_records.append(WorkLogRecord(
                                    msg_hash=msg_hash,
                                    log_type=prev.log_type,
                                    worker_name=prev.worker_name,
                                    worker_company=prev.worker_info.company,
                                    worker_title=prev.worker_info.title,
                                    worker_team=prev.worker_info.team,
                                    client_name=prev.client_name,
                                    task_description=prev.task_description,
                                    estimated_minutes=prev.estimated_minutes,
                                    actual_minutes=auto_actual,
                                    start_time=prev.timestamp,
                                    end_time=auto_end_time,
                                    status="COMPLETED",
                                    is_night_work=is_night,
                                    is_weekend_work=is_weekend,
                                    raw_start_message=prev.raw_message,
                                    raw_end_message="[자동완료] 다음 시작 보고 수신으로 이전 작업 예정시간 기준 완료 처리"
                                ))
                            
                            pending_starts.append(ts)
                continue
                
            # 2. 완료 보고 파싱
            task_end = KakaoMessageParser.parse_task_end(msg)
            if task_end:
                matched_group_id = None
                
                # A. 답장 인용문(Reply content)이 있는 경우 매칭
                if task_end.reply_target_content:
                    reply_text = task_end.reply_target_content
                    for i in range(len(pending_starts) - 1, -1, -1):
                        p_start = pending_starts[i]
                        if (p_start.client_name in reply_text or 
                            p_start.task_description in reply_text or 
                            p_start.worker_name in reply_text):
                            matched_group_id = p_start.task_group_id
                            break
                            
                # B. 인용문이 없거나 매칭 실패 시 작업자 이름 기준 가장 최근 시작 보고 매칭 (최대 120시간/5일 이내)
                if not matched_group_id:
                    target_name = task_end.worker_info.name
                    possible_names = [target_name]
                    if task_end.worker_specific_minutes:
                        possible_names.extend(task_end.worker_specific_minutes.keys())

                    end_mins = task_end.actual_minutes

                    for i in range(len(pending_starts) - 1, -1, -1):
                        p_start = pending_starts[i]
                        if (p_start.worker_name in possible_names or 
                            p_start.worker_info.name in possible_names or 
                            any(pn in p_start.worker_info.full_profile for pn in possible_names)):
                            
                            # 작업자별 개별 시간이 있는 경우
                            worker_end_mins = end_mins
                            if task_end.worker_specific_minutes and p_start.worker_name in task_end.worker_specific_minutes:
                                worker_end_mins = task_end.worker_specific_minutes[p_start.worker_name]

                            # ★ 사용자 지정 규칙: 단순 완료 보고 시 완료시간과 예정시간의 괴리가 과도하면 오매칭 방지를 위해 건너뜀 ★
                            # 1) 상한 가드: 완료시간이 (예정시간 + 2시간/120분)을 초과하는 경우 (예: 4시간 예정에 18시간/2day 완료)
                            # 2) 하한 가드: 3days(27h) 등 다일(Day) 대형 작업에 단발성 5.5시간 등 현격히 작은 완료 보고가 묶이는 것 방지
                            if p_start.estimated_minutes > 0 and worker_end_mins > 0:
                                is_too_large = worker_end_mins > (p_start.estimated_minutes + 120)
                                is_too_small = (p_start.estimated_minutes >= 8 * 60) and (worker_end_mins < p_start.estimated_minutes * 0.6)
                                if is_too_large or is_too_small:
                                    if not p_start.client_name or p_start.client_name not in task_end.raw_message:
                                        continue

                            adj_end_time = task_end.timestamp
                            if adj_end_time < p_start.timestamp and (p_start.timestamp - adj_end_time).total_seconds() < 24 * 3600:
                                adj_end_time += timedelta(days=1)
                                task_end.timestamp = adj_end_time

                            time_diff = (task_end.timestamp - p_start.timestamp).total_seconds()
                            match_timeout_hours = max(120.0, get_pending_timeout_hours(p_start))
                            if 0 <= time_diff <= match_timeout_hours * 3600:
                                matched_group_id = p_start.task_group_id
                                break
                                
                # C. 해당 그룹(공동 작업 인원 전체) 매칭 및 완료 처리
                # ★ COMPLETED 레코드의 start_time은 무조건 원래 시작 보고 시각(Pending 시각)으로 고정! ★
                if matched_group_id:
                    group_starts = [p for p in pending_starts if p.task_group_id == matched_group_id]
                    pending_starts = [p for p in pending_starts if p.task_group_id != matched_group_id]
                    
                    for p_start in group_starts:
                        adj_end_time = task_end.timestamp
                        if adj_end_time < p_start.timestamp and (p_start.timestamp - adj_end_time).total_seconds() < 24 * 3600:
                            adj_end_time += timedelta(days=1)

                        calc_minutes = 0
                        if task_end.worker_specific_minutes and p_start.worker_name in task_end.worker_specific_minutes:
                            calc_minutes = task_end.worker_specific_minutes[p_start.worker_name]
                        elif task_end.actual_minutes > 0:
                            calc_minutes = task_end.actual_minutes
                        else:
                            # 시간 미기재 완료 시 (완료시각 - 시작시각) 또는 원래 시작 보고의 예정시간
                            elapsed_diff = (adj_end_time - p_start.timestamp).total_seconds() / 60.0
                            if 10 <= elapsed_diff <= 24 * 60:
                                calc_minutes = int(elapsed_diff)
                            elif p_start.estimated_minutes > 0:
                                calc_minutes = p_start.estimated_minutes
                            else:
                                calc_minutes = 60

                        # 고유 해시 생성 (원래 시작 시각 기준)
                        msg_hash = generate_msg_hash(
                            p_start.worker_name,
                            p_start.client_name,
                            p_start.timestamp, # 최초 시작 일시 고정
                            p_start.task_description
                        )
                        
                        is_night = check_is_night_work(p_start.timestamp, adj_end_time, p_start.raw_message, p_start.estimated_minutes, calc_minutes)
                        is_weekend = check_is_weekend_work(p_start.timestamp, adj_end_time, p_start.raw_message, p_start.estimated_minutes, calc_minutes)
                        
                        record = WorkLogRecord(
                            msg_hash=msg_hash,
                            log_type=p_start.log_type,
                            worker_name=p_start.worker_name,
                            worker_company=p_start.worker_info.company,
                            worker_title=p_start.worker_info.title,
                            worker_team=p_start.worker_info.team,
                            client_name=p_start.client_name,
                            task_description=p_start.task_description,
                            estimated_minutes=p_start.estimated_minutes,
                            actual_minutes=calc_minutes,
                            start_time=p_start.timestamp, # ★ 원래 시작 시각(Pending 시각) ★
                            end_time=adj_end_time,
                            status="COMPLETED",
                            is_night_work=is_night,
                            is_weekend_work=is_weekend,
                            raw_start_message=p_start.raw_message,
                            raw_end_message=task_end.raw_message
                        )
                        matched_records.append(record)
                        
        # 3. 잔여 미완료 시작 보고들 처리 (기본 48시간, 다일 작업은 (예정일수*24h)+48h 경과 시 COMPLETED 자동 전환)
        latest_ref_time = max([m.timestamp for m in raw_messages]) if raw_messages else datetime.now()
        
        for p_start in pending_starts:
            msg_hash = generate_msg_hash(
                p_start.worker_name,
                p_start.client_name,
                p_start.timestamp,
                p_start.task_description
            )
            is_night = check_is_night_work(p_start.timestamp, None, p_start.raw_message, p_start.estimated_minutes, p_start.estimated_minutes)
            is_weekend = check_is_weekend_work(p_start.timestamp, None, p_start.raw_message, p_start.estimated_minutes, p_start.estimated_minutes)
            
            time_diff_hours = (latest_ref_time - p_start.timestamp).total_seconds() / 3600.0
            threshold_hours = get_pending_timeout_hours(p_start)
            
            if time_diff_hours >= threshold_hours:
                # 대기 타임아웃 경과: 시작 보고 내용(예정시간) 기준으로 COMPLETED 자동 전환
                auto_actual = p_start.estimated_minutes if p_start.estimated_minutes > 0 else 60
                auto_end_time = p_start.timestamp + timedelta(minutes=auto_actual)
                
                record = WorkLogRecord(
                    msg_hash=msg_hash,
                    log_type=p_start.log_type,
                    worker_name=p_start.worker_name,
                    worker_company=p_start.worker_info.company,
                    worker_title=p_start.worker_info.title,
                    worker_team=p_start.worker_info.team,
                    client_name=p_start.client_name,
                    task_description=p_start.task_description,
                    estimated_minutes=p_start.estimated_minutes,
                    actual_minutes=auto_actual,
                    start_time=p_start.timestamp,
                    end_time=auto_end_time,
                    status="COMPLETED",
                    is_night_work=is_night,
                    is_weekend_work=is_weekend,
                    raw_start_message=p_start.raw_message,
                    raw_end_message=f"[자동완료] {int(threshold_hours)}시간 경과로 시작보고 기준 완료 처리"
                )
            else:
                # 대기 타임아웃 이내: 현재 진행 중(PENDING) 유지
                record = WorkLogRecord(
                    msg_hash=msg_hash,
                    log_type=p_start.log_type,
                    worker_name=p_start.worker_name,
                    worker_company=p_start.worker_info.company,
                    worker_title=p_start.worker_info.title,
                    worker_team=p_start.worker_info.team,
                    client_name=p_start.client_name,
                    task_description=p_start.task_description,
                    estimated_minutes=p_start.estimated_minutes,
                    actual_minutes=0,
                    start_time=p_start.timestamp,
                    end_time=None,
                    status="PENDING",
                    is_night_work=is_night,
                    is_weekend_work=is_weekend,
                    raw_start_message=p_start.raw_message,
                    raw_end_message=""
                )
            matched_records.append(record)
            
        return matched_records

    @classmethod
    def parse_and_match_text(cls, full_text: str) -> List[WorkLogRecord]:
        raw_msgs = KakaoMessageParser.parse_raw_text_to_messages(full_text)
        return cls.match_messages(raw_msgs)
