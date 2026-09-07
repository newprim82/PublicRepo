import os
import sys
import re
import threading
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

# Windows 전용 COM 모듈
try:
    import win32com.client
    import pythoncom
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

from ..config import config
from ..database.outlook_models import OutlookScheduleRecord
from ..database.supabase_client import db_manager
from ..services.team_service import TeamService

def safe_print(msg: str):
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"), flush=True)
        except Exception:
            pass

# 팀원별 아웃룩 탭 컬러 매핑 (아웃룩 UI와 100% 동일)
MEMBER_COLOR_MAP = {
    "문영민": "#84cc16",   # 연두 (문영민 수석)
    "이동우": "#f97316",   # 주황 (이동우 수석)
    "홍정표": "#14b8a6",   # 옥색/청록 (홍정표 과장)
    "전종필": "#eab308",   # 노랑 (전종필 대리)
    "김시우": "#ec4899",   # 핑크 (김시우 사원)
    "김형일": "#06b6d4",   # 하늘 (김형일 수석)
    "김경현": "#f43f5e",   # 코랄핑크 (내 기본 캘린더)
}

# 기본 탐색 대상 팀원 후보 목록 (직급 포함 표시이름)
DEFAULT_TARGET_MEMBERS = [
    "김시우 사원", "문영민 수석", "전종필 대리", "이동우 수석",
    "홍정표 과장", "김형일 수석", "홍정표", "김형일"
]

def clean_worker_name(raw: str) -> str:
    """문자열에서 순수 작업자 이름만 정제 (예: '문영민 수석' -> '문영민', '[김시우]' -> '김시우')"""
    if not raw:
        return ""
    if raw in ["내 캘린더", "내 일정", "Calendar", "내"]:
        return "김경현"
    m = re.search(r"\[([가-힣a-zA-Z0-9]+)\]", raw)
    if m:
        return m.group(1).strip()
    return re.sub(r"\s*(수석|과장|대리|사원|팀장|본부장|부장|차장|이사|상무|전무)$", "", raw).strip()

def extract_outlook_schedules(months_ahead: int = 2) -> List[OutlookScheduleRecord]:
    """
    PC B의 Outlook 데스크톱 앱에서 내 일정 및 공유 캘린더 일정을 안전하게 추출
    - '종일' 체크 시 09:00~18:00 (8.0h) 자동 시간 보정
    - 휴가/연차/반차 자동 감지
    """
    if not WIN32_AVAILABLE:
        safe_print("[-] Windows COM 모듈이 지원되지 않는 환경입니다.")
        return []

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
    except Exception as e:
        safe_print(f"[-] Outlook MAPI 연결 실패: {e}")
        return []

    cal_folders = []

    # 1. 내 기본 캘린더 연동 (Calendar)
    try:
        def_cal = namespace.GetDefaultFolder(9)
        my_name = "김경현 수석"
        cal_folders.append((my_name, def_cal))
        safe_print(f"[✓] Outlook 내 기본 캘린더 연결 성공: '{my_name}' (항목: {def_cal.Items.Count})")
    except Exception as e:
        safe_print(f"[-] 기본 캘린더 접근 실패: {e}")

    # 2. 공유 캘린더 직접 연동 (STA 메인 스레드 안전 호출)
    team_members_info = TeamService.get_team_members_info()
    target_names = [
        "문영민 수석", "이동우 수석", "홍정표 과장", "전종필 대리", "김형일 수석", "김시우 사원",
        "문영민", "이동우", "홍정표", "전종필", "김형일", "김시우"
    ]

    for name in target_names:
        clean_target = clean_worker_name(name)
        if clean_target == "김경현":
            continue
        # 이미 연동된 멤버면 중복 건너뛰기
        if any(clean_worker_name(f[0]) == clean_target for f in cal_folders):
            continue

        try:
            recip = namespace.CreateRecipient(name)
            folder = namespace.GetSharedDefaultFolder(recip, 9)
            if folder:
                cal_folders.append((name, folder))
                safe_print(f"[✓] Outlook 공유 캘린더 연결 성공: '{name}' (항목: {folder.Items.Count})")
        except Exception as e_sh:
            pass

    # 3. 날짜 필터링 범위 (현재 달 1일 ~ N개월 후 말일)
    now = datetime.now()
    cur_year = now.year
    cur_month = now.month
    start_date_str = f"{cur_year:04d}-{cur_month:02d}-01 00:00"

    # N개월 후 계산
    future_month = cur_month + months_ahead
    future_year = cur_year + (future_month - 1) // 12
    future_month = ((future_month - 1) % 12) + 1
    import calendar
    last_day = calendar.monthrange(future_year, future_month)[1]
    end_date_str = f"{future_year:04d}-{future_month:02d}-{last_day:02d} 23:59"

    restriction = f"[Start] >= '{start_date_str}' AND [End] <= '{end_date_str}'"

    records = []
    seen_ids = set()

    for owner_name, folder in cal_folders:
        try:
            try:
                items = folder.Items
            except Exception as e_items:
                safe_print(f"[i] 공유 캘린더 '{owner_name}': 사서함 세부 일정 접근 권한이 없어 건너뜁니다.")
                continue

            try:
                items.IncludeRecurrences = True
                items.Sort("[Start]")
            except Exception:
                pass

            try:
                flt = items.Restrict(restriction)
            except Exception:
                flt = items

            item = flt.GetFirst()
            while item:
                try:
                    entry_id = getattr(item, "EntryID", "")
                    if not entry_id:
                        entry_id = f"{owner_name}_{getattr(item, 'Subject', '')}_{getattr(item, 'Start', '')}"

                    if entry_id in seen_ids:
                        item = flt.GetNext()
                        continue
                    seen_ids.add(entry_id)

                    subject = str(getattr(item, "Subject", "") or "").strip()
                    if not subject:
                        item = flt.GetNext()
                        continue

                    # 작업자 이름 식별
                    w_name = ""
                    m = re.search(r"\[([가-힣a-zA-Z0-9]+)\]", subject)
                    if m:
                        cand = m.group(1).strip()
                        if cand in team_members_info or any(t in cand for t in ["팀", "본부"]):
                            w_name = cand
                    if not w_name or any(t in w_name for t in ["팀", "본부"]):
                        w_name = clean_worker_name(owner_name)
                    if not w_name or w_name in ["내 캘린더", "내 일정", "Calendar", "내"]:
                        w_name = "김경현"

                    # 휴가 / 연차 / 반차 식별
                    is_leave = False
                    leave_type = ""
                    sched_type = "작업"
                    for lk in ["연차", "반차", "오전반차", "오후반차", "휴가", "공가", "보상휴가"]:
                        if lk in subject:
                            is_leave = True
                            leave_type = lk
                            sched_type = "휴가"
                            break

                    if not is_leave:
                        if any(k in subject for k in ["교육", "세미나", "실습", "학습"]):
                            sched_type = "교육"
                        elif any(k in subject for k in ["회의", "미팅", "1on1", "주간"]):
                            sched_type = "회의"

                    # 시간 처리: 종일 또는 다일(Multi-day) 일정 분할 처리
                    allday = bool(getattr(item, "AllDayEvent", False))
                    raw_st = getattr(item, "Start", None)
                    raw_ed = getattr(item, "End", None)

                    team_info = team_members_info.get(w_name, {})
                    w_team = team_info.get("team", "기술 1팀" if w_name in ["문영민", "이동우", "홍정표", "전종필", "김시우", "김형일", "김경현", "양금희"] else "미배정")
                    color = MEMBER_COLOR_MAP.get(w_name, "#0284c7")
                    loc = str(getattr(item, "Location", "") or "").strip()

                    if allday:
                        # 종일 일정: 날짜 범위 계산 (예: 9/8~9/10 지원 -> Start: 9/8 00:00, End: 9/11 00:00)
                        if hasattr(raw_st, "date"):
                            st_date = raw_st.date()
                        else:
                            st_date = datetime.strptime(str(raw_st)[:10], "%Y-%m-%d").date()

                        if hasattr(raw_ed, "date"):
                            ed_date_raw = raw_ed.date()
                        else:
                            ed_date_raw = datetime.strptime(str(raw_ed)[:10], "%Y-%m-%d").date()

                        # 아웃룩 종일 일정의 End가 다음날 자정(00:00)이면 마지막 날짜는 하루 전날
                        if hasattr(raw_ed, "hour") and raw_ed.hour == 0 and raw_ed.minute == 0 and ed_date_raw > st_date:
                            real_end_date = ed_date_raw - timedelta(days=1)
                        else:
                            real_end_date = ed_date_raw

                        # 시작일부터 종료일까지 매일매일 09:00~18:00 (8.0h) 분할 레코드 생성!
                        curr_d = st_date
                        while curr_d <= real_end_date:
                            d_val = curr_d.strftime("%Y-%m-%d")
                            sub_id = f"{entry_id}_{d_val}" if curr_d != st_date else entry_id
                            rec = OutlookScheduleRecord(
                                entry_id=sub_id,
                                worker_name=w_name,
                                worker_team=w_team,
                                subject=subject,
                                schedule_type=sched_type,
                                start_time=f"{d_val} 09:00:00",
                                end_time=f"{d_val} 18:00:00",
                                duration_hours=8.0,
                                is_all_day=True,
                                is_leave=is_leave,
                                leave_type=leave_type,
                                location=loc,
                                body="",
                                color_tag=color,
                                created_by=owner_name
                            )
                            records.append(rec)
                            curr_d += timedelta(days=1)
                    else:
                        st_str = raw_st.strftime("%Y-%m-%d %H:%M:%S") if hasattr(raw_st, "strftime") else str(raw_st)[:19]
                        ed_str = raw_ed.strftime("%Y-%m-%d %H:%M:%S") if hasattr(raw_ed, "strftime") else str(raw_ed)[:19]
                        try:
                            s_dt = datetime.strptime(st_str[:19], "%Y-%m-%d %H:%M:%S")
                            e_dt = datetime.strptime(ed_str[:19], "%Y-%m-%d %H:%M:%S")
                            dur_h = round(max(0.5, (e_dt - s_dt).total_seconds() / 3600.0), 1)
                        except Exception:
                            dur_h = 1.0

                        rec = OutlookScheduleRecord(
                            entry_id=entry_id,
                            worker_name=w_name,
                            worker_team=w_team,
                            subject=subject,
                            schedule_type=sched_type,
                            start_time=st_str,
                            end_time=ed_str,
                            duration_hours=dur_h,
                            is_all_day=False,
                            is_leave=is_leave,
                            leave_type=leave_type,
                            location=loc,
                            body="",
                            color_tag=color,
                            created_by=owner_name
                        )
                        records.append(rec)
                except Exception:
                    pass
                item = flt.GetNext()
        except Exception as e:
            print(f"[-] 캘린더 폴더 '{owner_name}' 일정 처리 오류: {e}")

    return records


def run_outlook_collection_cycle() -> Dict[str, Any]:
    """10분 정기 아웃룩 스케줄 동기화 사이클 실행"""
    safe_print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📅 아웃룩 캘린더 동기화 가동...")
    records = extract_outlook_schedules(months_ahead=2)
    if not records:
        safe_print("[-] 아웃룩에서 수집된 일정이 없습니다.")
        return {"success": False, "count": 0}

    # DB 저장 (로컬 SQLite 및 Supabase)
    saved = db_manager.save_outlook_schedules(records)
    safe_print(f"[✓] 아웃룩 스케줄 총 {len(records)}건 추출 완료 (DB 저장: {saved}건)")
    from collections import Counter
    counts = Counter([r.worker_name for r in records])
    for w, c in counts.items():
        is_me = " (내 일정)" if w == "김경현" else ""
        safe_print(f"    • {w}{is_me}: {c}건")
    return {"success": True, "count": len(records), "saved": saved}


if __name__ == "__main__":
    res = run_outlook_collection_cycle()
    safe_print(f"실행 결과: {res}")
