import os
import re
import sys
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from pathlib import Path

from ..config import config
from ..parser.kakao_parser import RawKakaoMessage, KakaoMessageParser
from ..parser.reply_matcher import WorkLogMatcher, WorkLogRecord
from ..database.supabase_client import db_manager

# Windows 전용 모듈 안전 임포트
import ctypes
import urllib.request

try:
    import win32gui
    import win32process
    import win32con
    import win32clipboard
    import win32api
    import pythoncom
    import uiautomation as auto
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

# Windows 전원 관리 절전 방지 플래그
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040

def enable_windows_keep_alive():
    """대시보드 및 카톡 수집기가 실행되는 동안 Windows 시스템이 절전 모드(Sleep)로 진입하는 것을 차단"""
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
            log_trace("[🛡️ 절전 방지 활성화] Windows 시스템 절전 모드 진입이 원천 차단되었습니다. (24시간 상시 가동)")
    except Exception as e:
        log_trace(f"[절전 방지 설정 알림]: {e}")

def ping_streamlit_cloud_app():
    """10분마다 Streamlit Cloud 웹사이트로 가벼운 HTTP Ping을 전송하여 슬립 모드 진입을 원천 차단"""
    app_url = config.STREAMLIT_APP_URL
    if not app_url:
        return
    try:
        req = urllib.request.Request(
            app_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WorkLogCollector KeepAlive/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.getcode()
            log_trace(f"[🌐 Streamlit Cloud Keep-Alive] URL '{app_url}' 핑 성공 (상태 코드: {status})")
    except Exception as e:
        log_trace(f"[🌐 Streamlit Cloud 핑 알림]: {e}")



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

# 현재 활성 스레드 ID 관리 및 동기화 락
_ACTIVE_THREAD_TOKEN = 0
_cycle_lock = threading.Lock()
_last_execution_timestamp = 0

# 한국 표준시 (KST, UTC+9) 기준 정의
KST_TIMEZONE = timezone(timedelta(hours=9))

def get_current_kst_time() -> datetime:
    """OS 타임존(UTC 등)과 관계없이 항상 한국 표준시(KST)를 반환"""
    try:
        # UTC 기준 현재 시각을 KST로 변환 후 naive datetime으로 반환
        return datetime.now(timezone.utc).astimezone(KST_TIMEZONE).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def get_collector_countdown_info() -> Dict[str, Any]:
    """
    다음 자동 증분 수집까지 남은 시간(분) 및 예정 시각 정보를 한국 표준시(KST) 기준으로 계산하여 반환
    """
    now = get_current_kst_time()
    interval = max(600, config.COLLECTOR_INTERVAL_SECONDS) # 10분 (600초)
    next_time = COLLECTOR_STATUS.get("next_run_time")
    last_time = COLLECTOR_STATUS.get("last_run_time")
    
    # next_time이 없거나 현재 시각보다 과거인 경우 현재 시각 기준으로 미래 시각 재계산
    if not next_time or next_time <= now:
        next_time = now + timedelta(seconds=interval)
        COLLECTOR_STATUS["next_run_time"] = next_time
        
    remaining_seconds = max(0, int((next_time - now).total_seconds()))
    remaining_minutes = max(1, (remaining_seconds + 59) // 60)
    
    if remaining_seconds <= 0:
        badge_text = "⚡ 증분 수집 진행 중..."
    else:
        badge_text = f"⏳ {remaining_minutes}분 뒤 자동수집"
        
    return {
        "is_running": COLLECTOR_STATUS.get("is_running", False),
        "remaining_minutes": remaining_minutes,
        "remaining_seconds": remaining_seconds,
        "target_timestamp": int(next_time.timestamp()),
        "next_run_str": next_time.strftime("%H:%M"),
        "last_run_str": last_time.strftime("%H:%M") if isinstance(last_time, datetime) else (str(last_time).split(" ")[-1][:5] if last_time else "없음"),
        "badge_text": badge_text
    }


def find_kakao_chat_window(chat_title_keyword: str) -> Optional[int]:
    """
    지정된 키워드(예: '[기술본부] 업무공유방')가 포함된 카카오톡 채팅방 창 핸들(HWND)을 정밀 검색
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
            if not title:
                return True
                
            title_clean = title.replace("🚩", "").replace("✨", "").replace("🏳️", "").strip().lower()
            
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


def extract_text_from_kakao_window(hwnd: int, is_manual: bool = False) -> str:
    """
    열려 있는 카카오톡 창에서 대화 목록을 4중 다층 안전 엔진으로 추출
    1. UIAutomation 전체 트리 심층 순회
    2. Windows API 네이티브 포커스 획득 & 클립보드 안전 복사 (AttachThreadInput)
    3. UIAutomation SendKeys 복사
    """
    if not WIN32_AVAILABLE or not hwnd:
        return ""

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    log_trace(f"[추출 시작] HWND={hwnd} 대상 텍스트 다층 추출 가동 (is_manual={is_manual})")

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
    except Exception:
        pass

    # [1단계] UIAutomation 전체 트리 재귀 탐색 (화면 간섭 전혀 없음)
    extracted_lines = []
    try:
        # list_hwnd 우선, 없으면 hwnd 전체 탐색
        target_ctrls = []
        if list_hwnd:
            c1 = auto.ControlFromHandle(list_hwnd)
            if c1:
                target_ctrls.append(c1)
        c2 = auto.ControlFromHandle(hwnd)
        if c2:
            target_ctrls.append(c2)

        for target_ctrl in target_ctrls:
            for c, depth in auto.WalkTree(target_ctrl, getChildren=auto.GetChildren):
                if depth > 20:
                    continue
                name = c.Name
                if name and len(name.strip()) > 0:
                    s = name.strip()
                    if not any(ign == s for ign in ["최소화", "최대화", "닫기", "전송", "메뉴", "검색", "이모티콘", "파일 보내기", "음성 대화", "페이스톡", "더보기", "이전 대화 보기"]):
                        extracted_lines.append(s)
            if len(extracted_lines) >= 3:
                break
                
        if len(extracted_lines) >= 3:
            log_trace(f"[✓ UIA 텍스트 추출 성공] 총 {len(extracted_lines)}줄 획득")
            return "\n".join(extracted_lines)
    except Exception as e:
        log_trace(f"[UIA 추출 알림]: {e}")

    # [2단계] 포커스 강제 획득 & Windows 네이티브 키 이벤트 복사 (Ctrl+A -> Ctrl+C)
    log_trace("[2단계 네이티브 복사 엔진 가동]")
    try:
        # 기존 클립보드 백업
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

        # Windows 10/11 포커스 강제 전환 기법 (AttachThreadInput)
        try:
            fore_h = win32gui.GetForegroundWindow()
            if fore_h and fore_h != hwnd:
                fore_tid, _ = win32process.GetWindowThreadProcessId(fore_h)
                kakao_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
                win32process.AttachThreadInput(fore_tid, kakao_tid, True)
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                win32gui.BringWindowToTop(hwnd)
                win32process.AttachThreadInput(fore_tid, kakao_tid, False)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.1)
        except Exception as e:
            log_trace(f"[포커스 전환 알림]: {e}")

        # 대화목록 영역 클릭하여 포커스 부여
        target_focus = list_hwnd if list_hwnd else hwnd
        if target_focus:
            rect = win32gui.GetClientRect(target_focus)
            click_x = max(10, rect[2] // 2)
            click_y = max(10, min(150, rect[3] // 2))
            lparam = (click_y << 16) | click_x
            win32gui.PostMessage(target_focus, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            win32gui.PostMessage(target_focus, win32con.WM_LBUTTONUP, 0, lparam)
            time.sleep(0.08)

        # 네이티브 키 이벤트로 Ctrl+A -> Ctrl+C 전송
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord('A'), 0, 0, 0)
        time.sleep(0.05)
        win32api.keybd_event(ord('A'), 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)
        win32api.keybd_event(ord('C'), 0, 0, 0)
        time.sleep(0.05)
        win32api.keybd_event(ord('C'), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.15)

        # 클립보드 읽기
        copied_text = ""
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                copied_text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except Exception as e:
            log_trace(f"[클립보드 읽기 오류]: {e}")
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        # 사용자 클립보드 원상 복구
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
            log_trace(f"[✓ 네이티브 복사 성공] 총 {len(lines)}줄 ({len(copied_text)}자) 획득")
            return copied_text.strip()
    except Exception as e:
        log_trace(f"[네이티브 복사 예외]: {e}")

    # [3단계] UIAutomation SendKeys Fallback
    try:
        log_trace("[3단계 UIAutomation SendKeys 시도]")
        auto.SendKeys('{Ctrl}a{Ctrl}c', waitTime=0.15)
        time.sleep(0.15)
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

        if copied_text and len(copied_text.strip()) > 10:
            log_trace(f"[✓ UIA SendKeys 복사 성공] {len(copied_text)}자 획득")
            return copied_text.strip()
    except Exception as e:
        log_trace(f"[UIA SendKeys 예외]: {e}")

    if extracted_lines:
        return "\n".join(extracted_lines)

    log_trace("[-] 모든 다층 추출 방식 실패")
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
        if not is_manual and (now_ts - _last_execution_timestamp < 120):
            return {"status": "throttled", "message": "쿨다운 대기 중"}
            
        _last_execution_timestamp = now_ts
        kst_now = get_current_kst_time()
        now_str = kst_now.strftime("%Y-%m-%d %H:%M:%S")
        target_chat = config.KAKAO_CHAT_TITLE
        
        COLLECTOR_STATUS["last_run_time"] = now_str
        COLLECTOR_STATUS["total_cycles"] += 1
        COLLECTOR_STATUS["next_run_time"] = kst_now + timedelta(seconds=config.COLLECTOR_INTERVAL_SECONDS)
        
        log_trace(f"==================================================")
        log_trace(f"🤖 [카카오톡 증분 수집 ({'⚡ 수동 즉시' if is_manual else '⏳ 10분 정기'})] 대상: '{target_chat}'")
        
        hwnd = find_kakao_chat_window(target_chat)
        if not hwnd:
            msg = f"'{target_chat}' 대화방 창이 PC 화면에 열려있지 않습니다."
            log_trace(f"[-] {msg}")
            COLLECTOR_STATUS["last_status"] = "대화방 창 미열림"
            COLLECTOR_STATUS["last_log_message"] = msg
            return {"status": "window_not_found", "message": msg, "time": now_str}
            
        raw_text = extract_text_from_kakao_window(hwnd, is_manual=is_manual)
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


def background_collector_loop(token: int):
    """
    백그라운드에서 10분(600초)마다 1회씩만 정확히 실행되는 상시 데몬 루프
    """
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    # Windows OS 시스템 절전 방지 활성화
    enable_windows_keep_alive()

    COLLECTOR_STATUS["is_running"] = True
    interval = max(600, config.COLLECTOR_INTERVAL_SECONDS)  # 10분 (600초)
    COLLECTOR_STATUS["next_run_time"] = datetime.now() + timedelta(seconds=interval)
    
    log_trace(f"🚀 [10분 자동 수집 데몬 기동] 토큰={token} | {interval}초(10분)마다 1회씩 실행합니다.")
    
    # 기동 시 즉시 Streamlit Cloud Keep-Alive 핑 1회 전송
    ping_streamlit_cloud_app()

    while True:
        if token != _ACTIVE_THREAD_TOKEN:
            log_trace(f"[스레드 종료] 이전 수집기 스레드(토큰={token})가 안전하게 종료되었습니다.")
            break
            
        time.sleep(interval)
        
        if token != _ACTIVE_THREAD_TOKEN:
            break
            
        try:
            enable_windows_keep_alive()
            run_collection_cycle(is_manual=False)
            ping_streamlit_cloud_app()
        except Exception as e:
            log_trace(f"[수집기 데몬 대기 예외]: {e}")


def start_background_collector():
    """
    프로세스 전체에서 단 1개의 백그라운드 수집기 스레드만 실행되도록 토큰 기반 싱글톤 보장
    """
    global _ACTIVE_THREAD_TOKEN
    
    _ACTIVE_THREAD_TOKEN += 1
    current_token = _ACTIVE_THREAD_TOKEN
    
    thread = threading.Thread(
        target=background_collector_loop,
        args=(current_token,),
        daemon=True,
        name=f"KakaoAutoCollectorThread_{current_token}"
    )
    thread.start()
    log_trace(f"[✓] 카카오톡 10분 자동 수집 데몬(토큰={current_token})이 단독 기동되었습니다.")
    return True
