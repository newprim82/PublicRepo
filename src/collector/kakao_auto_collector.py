import os
import re
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path

from ..config import config
from ..parser.kakao_parser import RawKakaoMessage, KakaoMessageParser
from ..parser.reply_matcher import WorkLogMatcher, WorkLogRecord
from ..database.supabase_client import db_manager

# Windows 전용 모듈 안전 임포트
try:
    import win32gui
    import win32process
    import win32con
    import win32clipboard
    import pythoncom
    import uiautomation as auto
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


def safe_print(msg: str):
    """Windows 콘솔 cp949 인코딩 에러 방지 안전 출력 함수"""
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            print(msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'))
        except Exception:
            pass


def log_trace(msg: str):
    """자동화 동작 상세 로그 파일 기록 (@AutomationLog.txt)"""
    safe_print(msg)
    try:
        log_file = config.BASE_DIR / "@AutomationLog.txt"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


# 글로벌 수집기 상태 추적
COLLECTOR_STATUS = {
    "is_running": False,
    "last_run_time": None,
    "next_run_time": None,
    "last_status": "대기 중",
    "last_result": None,
    "total_cycles": 0,
    "last_log_message": ""
}

_cycle_lock = threading.Lock()
_last_execution_timestamp = 0


def get_collector_countdown_info() -> Dict[str, Any]:
    """
    다음 자동 증분 수집까지 남은 시간(분) 및 예정 시각 정보를 반환
    """
    now = datetime.now()
    next_time = COLLECTOR_STATUS.get("next_run_time")
    last_time = COLLECTOR_STATUS.get("last_run_time")
    
    if not next_time:
        next_time = now + timedelta(seconds=config.COLLECTOR_INTERVAL_SECONDS)
        COLLECTOR_STATUS["next_run_time"] = next_time
        
    remaining_seconds = max(0, int((next_time - now).total_seconds()))
    remaining_minutes = max(1, (remaining_seconds + 59) // 60)
    
    if remaining_seconds <= 0:
        badge_text = "⚡ 증분 수집 대기 중..."
    else:
        badge_text = f"⏳ {remaining_minutes}분 뒤 자동 증분 업데이트"
        
    return {
        "is_running": COLLECTOR_STATUS.get("is_running", False),
        "remaining_minutes": remaining_minutes,
        "remaining_seconds": remaining_seconds,
        "next_run_str": next_time.strftime("%H:%M"),
        "last_run_str": last_time.strftime("%H:%M") if isinstance(last_time, datetime) else (str(last_time).split(" ")[-1][:5] if last_time else "없음"),
        "badge_text": badge_text
    }


def find_kakao_chat_window(chat_title_keyword: str) -> Optional[int]:
    """
    지정된 키워드(예: '[기술본부] 업무공유방')가 포함된 카카오톡 채팅방 창 핸들(HWND)을 검색
    """
    if not WIN32_AVAILABLE:
        log_trace("[탐색 실패] WIN32 모듈이 사용 불가능합니다.")
        return None

    found_hwnd = None
    target_clean = chat_title_keyword.replace("🚩", "").replace("✨", "").replace("🏳️", "").strip().lower()

    def enum_windows_callback(hwnd, _):
        nonlocal found_hwnd
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls_name = win32gui.GetClassName(hwnd)
            if not title:
                return True
                
            title_clean = title.replace("🚩", "").replace("✨", "").replace("🏳️", "").strip().lower()
            
            # 카카오톡 대화방 창 조건
            if ("기술본부" in title_clean or "업무공유" in title_clean or target_clean in title_clean) and title != "카카오톡":
                found_hwnd = hwnd
                return False
        return True

    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception as e:
        log_trace(f"[창 탐색 예외]: {e}")

    if found_hwnd:
        log_trace(f"[✓ 창 감지 성공] HWND={found_hwnd} | 제목='{win32gui.GetWindowText(found_hwnd)}'")
    else:
        log_trace(f"[-] 대상 창 미발견 (키워드: '{chat_title_keyword}')")

    return found_hwnd


def extract_text_from_kakao_window(hwnd: int) -> str:
    """
    열려 있는 카카오톡 창에서 대화 목록을 안전하게 추출
    1순위: 100% 무간섭 UIA 직접 읽기 (창 활성화/키보드 조작 전혀 없음)
    2순위: UIA 실패 시에만 안전 복사 Fallback (대화목록 영역만 타겟팅)
    """
    if not WIN32_AVAILABLE or not hwnd:
        return ""

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    log_trace(f"[추출 시작] HWND={hwnd} 대상 텍스트 추출 시도")

    # 1. 자식 윈도우 중 대화 목록 리스트(EVA_VH_ListControl_RPC) 탐색
    list_hwnd = None
    child_hwnds = []
    
    def enum_child_proc(h, _):
        child_hwnds.append(h)
        return True

    try:
        win32gui.EnumChildWindows(hwnd, enum_child_proc, None)
        for ch in child_hwnds:
            c_name = win32gui.GetClassName(ch)
            if "EVA_VH_ListControl_RPC" in c_name:
                list_hwnd = ch
                break
    except Exception as e:
        log_trace(f"[자식 윈도우 탐색 오류]: {e}")

    # [1단계] 100% 무간섭 UIA 텍스트 추출 (창 활성화 및 포커스 이동 전혀 없음)
    extracted_lines = []
    try:
        target_ctrl_hwnd = list_hwnd if list_hwnd else hwnd
        ctrl = auto.ControlFromHandle(target_ctrl_hwnd)
        if ctrl:
            log_trace("[UIA] 백그라운드 무간섭 텍스트 추출 시도...")
            for c, depth in auto.WalkTree(ctrl, getChildren=auto.GetChildren):
                if depth > 15:
                    continue
                name = c.Name
                if name and len(name.strip()) > 0:
                    s = name.strip()
                    if not any(ign == s for ign in ["최소화", "최대화", "닫기", "전송", "메뉴", "검색", "이모티콘", "파일 보내기", "음성 대화", "페이스톡", "더보기"]):
                        extracted_lines.append(s)
                        
            if len(extracted_lines) >= 3:
                log_trace(f"[✓ UIA 무간섭 추출 성공] 총 {len(extracted_lines)}줄 획득 (화면 간섭 없음)")
                return "\n".join(extracted_lines)
    except Exception as e:
        log_trace(f"[UIA 추출 알림]: {e}")

    # [2단계] UIA로 읽히지 않는 경우에만 안전 복사 Fallback 실행
    try:
        old_clipboard = ""
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                old_clipboard = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        # 대화목록 창(EVA_VH_ListControl_RPC)에만 안전하게 포커스 후 복사
        target_focus = list_hwnd if list_hwnd else hwnd
        if target_focus:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.05)
            
            # 대화 목록 영역 클릭
            win32gui.PostMessage(target_focus, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, (100 << 16) | 100)
            win32gui.PostMessage(target_focus, win32con.WM_LBUTTONUP, 0, (100 << 16) | 100)
            time.sleep(0.05)

        auto.SendKeys('{Ctrl}a{Ctrl}c', waitTime=0.1)
        time.sleep(0.1)

        copied_text = ""
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                copied_text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        # 사용자 기존 클립보드 즉시 복원
        if old_clipboard:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, old_clipboard)
                win32clipboard.CloseClipboard()
            except Exception:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass

        if copied_text and len(copied_text.strip()) > 10:
            lines = copied_text.strip().split("\n")
            log_trace(f"[✓ 클립보드 복사 성공] 총 {len(lines)}줄 ({len(copied_text)}자) 획득")
            return copied_text.strip()
    except Exception as e:
        log_trace(f"[복사 Fallback 예외]: {e}")

    if extracted_lines:
        return "\n".join(extracted_lines)

    log_trace("[-] 텍스트 수집 실패")
    return ""


def run_collection_cycle(is_manual: bool = False) -> Dict[str, Any]:
    """
    1회 증분 수집 사이클 실행: 카톡 창 탐색 -> 텍스트 추출 -> 파싱 -> DB Upsert
    """
    global _last_execution_timestamp
    
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    with _cycle_lock:
        now_ts = time.time()
        # 수동 실행이 아닌 자동 루프의 경우 최소 120초 쿨다운 보장
        if not is_manual and (now_ts - _last_execution_timestamp < 120):
            return {"status": "throttled", "message": "쿨다운 대기 중"}
            
        _last_execution_timestamp = now_ts
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target_chat = config.KAKAO_CHAT_TITLE
        
        COLLECTOR_STATUS["last_run_time"] = now_str
        COLLECTOR_STATUS["total_cycles"] += 1
        COLLECTOR_STATUS["next_run_time"] = datetime.now() + timedelta(seconds=config.COLLECTOR_INTERVAL_SECONDS)
        
        log_trace(f"==================================================")
        log_trace(f"🤖 [카카오톡 증분 수집 ({'⚡ 수동 즉시' if is_manual else '⏳ 10분 자동'})] 대상: '{target_chat}'")
        
        hwnd = find_kakao_chat_window(target_chat)
        if not hwnd:
            msg = f"'{target_chat}' 대화방 창이 PC 화면에 열려있지 않습니다."
            log_trace(f"[-] {msg}")
            COLLECTOR_STATUS["last_status"] = "대화방 창 미열림"
            COLLECTOR_STATUS["last_log_message"] = msg
            return {"status": "window_not_found", "message": msg, "time": now_str}
            
        raw_text = extract_text_from_kakao_window(hwnd)
        if not raw_text or len(raw_text.strip()) == 0:
            msg = "대화창에서 텍스트를 읽지 못했습니다. 카톡 대화방을 마우스로 클릭한 뒤 다시 시도해주세요."
            log_trace(f"[-] {msg}")
            COLLECTOR_STATUS["last_status"] = "텍스트 추출 실패"
            COLLECTOR_STATUS["last_log_message"] = msg
            return {"status": "no_text", "message": msg, "time": now_str}
            
        log_trace(f"[파싱 시작] 텍스트 크기: {len(raw_text)}자")
        records = WorkLogMatcher.parse_and_match_text(raw_text)
        if not records:
            msg = "새로 등록/완료할 작업 보고 메시지가 없습니다."
            log_trace(f"[✓] {msg}")
            COLLECTOR_STATUS["last_status"] = "새 작업 없음"
            COLLECTOR_STATUS["last_log_message"] = msg
            return {"status": "no_records", "message": msg, "time": now_str}
            
        saved = db_manager.save_work_logs(records)
        COLLECTOR_STATUS["last_status"] = f"정상 동기화 ({saved}건 저장/갱신)"
        COLLECTOR_STATUS["last_result"] = {
            "total_records": len(records),
            "saved_records": saved
        }
        COLLECTOR_STATUS["last_log_message"] = f"🎉 {len(records)}건 분석 완료 (DB 저장: {saved}건)"
        
        log_trace(f"[✓] 🎉 {len(records)}건 작업 분석 완료 (DB 저장: {saved}건)")
        return {
            "status": "success",
            "total_records": len(records),
            "saved_records": saved,
            "time": now_str
        }


def background_collector_loop():
    """
    백그라운드에서 10분(600초)마다 1회씩만 정확히 실행되는 상시 데몬 루프
    """
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    COLLECTOR_STATUS["is_running"] = True
    interval = max(600, config.COLLECTOR_INTERVAL_SECONDS)  # 10분 (600초)
    COLLECTOR_STATUS["next_run_time"] = datetime.now() + timedelta(seconds=interval)
    
    log_trace(f"🚀 [10분 자동 수집 데몬 정상 기동] {interval}초(10분)마다 1회씩 백그라운드에서 실행합니다.")
    
    while True:
        try:
            # ★ 10분(600초)을 온전히 대기
            time.sleep(interval)
            run_collection_cycle(is_manual=False)
        except Exception as e:
            log_trace(f"[수집기 데몬 대기 예외]: {e}")
            time.sleep(interval)


def start_background_collector():
    """
    프로세스 전체에서 단 1개의 백그라운드 수집기 스레드만 실행되도록 싱글톤 보장
    """
    if hasattr(sys, "_kakao_collector_thread_running") and sys._kakao_collector_thread_running:
        return False
        
    sys._kakao_collector_thread_running = True
    thread = threading.Thread(
        target=background_collector_loop,
        daemon=True,
        name="KakaoAutoCollectorThread"
    )
    thread.start()
    log_trace("[✓] 카카오톡 10분 자동 수집 백그라운드 데몬이 단독 기동되었습니다.")
    return True
