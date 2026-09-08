import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd

DAY_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(?:days?|d(?![a-zA-Z])|D|일)', re.IGNORECASE)

def is_multiday_record(record: Dict[str, Any]) -> bool:
    """해당 레코드가 2일 이상(1.5days 이상)의 다일 작업인지 판별"""
    try:
        act_m = int(record.get("actual_minutes") or 0)
    except (ValueError, TypeError):
        act_m = 0
    raw_s = str(record.get("raw_start_message") or "")
    raw_e = str(record.get("raw_end_message") or "")
    
    m_s = DAY_PATTERN.search(raw_s)
    m_e = DAY_PATTERN.search(raw_e)
    
    val_s = float(m_s.group(1)) if m_s else 0.0
    val_e = float(m_e.group(1)) if m_e else 0.0
    
    # 1.5일(13.5시간 / 810분) 이상이면 다일 분할 대상
    if max(val_s, val_e) >= 1.5:
        return True
    if act_m >= 810 and (m_s or m_e or "day" in raw_s.lower() or "day" in raw_e.lower()):
        return True
    # 18시간(1080분) 이상이면서 IM뱅크 등 장기 지원 업무
    if act_m >= 1080:
        return True
        
    return False

def split_multiday_record(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    단일 다일 작업 레코드를 일자별 9시간 단위의 복수 레코드로 분할 (달력 연속 기준: 단순 +1일).
    작업 내용(task_description)은 일차 표기 없이 원본 그대로 유지.
    """
    if not is_multiday_record(record):
        return [record]

    st_raw = record.get("start_time")
    if isinstance(st_raw, str):
        st_dt = pd.to_datetime(st_raw).to_pydatetime()
    elif isinstance(st_raw, (pd.Timestamp, datetime)):
        st_dt = st_raw.to_pydatetime() if hasattr(st_raw, "to_pydatetime") else st_raw
    else:
        return [record]

    # 기본 1일당 9시간(540분)
    STANDARD_DAY_MINUTES = 540

    raw_s = str(record.get("raw_start_message") or "")
    raw_e = str(record.get("raw_end_message") or "")
    m_s = DAY_PATTERN.search(raw_s)
    m_e = DAY_PATTERN.search(raw_e)
    val_s = float(m_s.group(1)) if m_s else 0.0
    val_e = float(m_e.group(1)) if m_e else 0.0
    day_val = max(val_s, val_e)

    if day_val >= 1.0:
        total_minutes = int(day_val * STANDARD_DAY_MINUTES)
    else:
        total_minutes = max(int(record.get("actual_minutes") or 0), int(record.get("estimated_minutes") or 0))

    if total_minutes <= 0:
        return [record]
    
    import math
    total_days = max(1, math.ceil(total_minutes / STANDARD_DAY_MINUTES))
    remaining_minutes = total_minutes
    sub_records = []
    day_idx = 0

    orig_hash = str(record.get("msg_hash") or f"gen_{record.get('id', 'temp')}")
    orig_desc = str(record.get("task_description") or "").strip()
    # 기존에 혹시 붙어있던 (N/M일차) 패턴이 있다면 정리
    orig_desc = re.sub(r'\s*\(\d+/\d+일차\)$', '', orig_desc)
    orig_est_m = int(record.get("estimated_minutes") or total_minutes)
    is_pending = (str(record.get("status", "")).upper() == "PENDING")

    while remaining_minutes > 0:
        curr_day_minutes = min(remaining_minutes, STANDARD_DAY_MINUTES)
        curr_day_hours = round(curr_day_minutes / 60.0, 1)
        
        # 달력 연속 기준 (단순 +1일)
        curr_st = st_dt + timedelta(days=day_idx)
        curr_ed = curr_st + timedelta(minutes=curr_day_minutes)
        
        is_weekend = (curr_st.weekday() in [5, 6])
        
        # 분할 레코드 생성
        sub_rec = dict(record)
        # ID는 신규 insert 시 DB에서 자동 생성되거나 기존 유지
        if "id" in sub_rec and day_idx > 0:
            del sub_rec["id"]
            
        # 1일차는 원본 레코드의 msg_hash를 그대로 유지하여 DB의 27h 등 통짜 데이터를 일일 9.0h로 제자리 덮어쓰기 보장
        sub_rec["msg_hash"] = orig_hash if day_idx == 0 else f"{orig_hash}_d{day_idx + 1}"
        sub_rec["estimated_minutes"] = min(curr_day_minutes, STANDARD_DAY_MINUTES)
        sub_rec["estimated_hours"] = round(sub_rec["estimated_minutes"] / 60.0, 1)
        sub_rec["total_hours"] = sub_rec["estimated_hours"]
        # 🌟 원래 작업 내용 유지 + 괄호 일차 표기 (예: "업무지원 (1/3일차)")
        sub_rec["task_description"] = f"{orig_desc} ({day_idx + 1}/{total_days}일차)"
        sub_rec["is_night_work"] = False  # 주간 다일 작업
        sub_rec["is_weekend_work"] = is_weekend

        now_dt = datetime.now()
        if is_pending:
            if curr_ed <= now_dt:
                # 9시간 작업 시간이 이미 종료된 일차 -> 자동 완료(COMPLETED)
                sub_rec["start_time"] = curr_st.isoformat()
                sub_rec["end_time"] = curr_ed.isoformat()
                sub_rec["actual_minutes"] = curr_day_minutes
                sub_rec["actual_hours"] = curr_day_hours
                sub_rec["status"] = "COMPLETED"
            elif curr_st <= now_dt < curr_ed:
                # 당일 현재 근무 시간대 진행 중
                sub_rec["start_time"] = curr_st.isoformat()
                sub_rec["end_time"] = None
                sub_rec["actual_minutes"] = 0
                sub_rec["actual_hours"] = 0.0
                sub_rec["status"] = "PENDING"
            else:
                # 미래 일차 (내일 이후)
                next_st = curr_st.replace(hour=9, minute=0, second=0, microsecond=0)
                next_ed = curr_st.replace(hour=18, minute=0, second=0, microsecond=0)
                sub_rec["start_time"] = next_st.isoformat()
                sub_rec["end_time"] = next_ed.isoformat()
                sub_rec["actual_minutes"] = 0
                sub_rec["actual_hours"] = 0.0
                sub_rec["status"] = "SCHEDULED"
        else:
            sub_rec["start_time"] = curr_st.isoformat()
            sub_rec["end_time"] = curr_ed.isoformat()
            sub_rec["actual_minutes"] = curr_day_minutes
            sub_rec["actual_hours"] = curr_day_hours
            sub_rec["status"] = "COMPLETED"
        
        sub_records.append(sub_rec)
        
        remaining_minutes -= curr_day_minutes
        day_idx += 1

    return sub_records
