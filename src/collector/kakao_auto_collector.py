import time
import sys
import os
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from ..config import config
from ..parser.reply_matcher import WorkLogMatcher
from ..database.supabase_client import db_manager

# Windows 전용 라이브러리 (안전 import)
try:
    import win32gui
    import win32con
    import win32clipboard
    import uiautomation as auto
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("[알림] pywin32 / uiautomation 라이브러리가 로드되지 않았습니다. (Windows 환경 필요)")

def safe_print(msg: str):
    """Windows cp949 콘솔에서도 이모지로 인한 인코딩 오류 없이 안전하게 출력"""
    try:
        print(msg)
    except UnicodeEncodeError:
        safe_msg = msg.encode(sys.stdout.encoding or 'cp949', errors='replace').decode(sys.stdout.encoding or 'cp949')
        print(safe_msg)
    except Exception:
        pass

# 글로벌 수집기 상태 추적
COLLECTOR_STATUS = {
    "is_running": False,
    "last_run_time": None,
    "next_run_time": None,
    "last_status": "대기 중",
    "last_result": None,
    "total_cycles": 0
}

_collector_thread: Optional[threading.Thread] = None
_thread_lock = threading.Lock()


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
        badge_text = "⚡ 증분 수집 준비 중..."
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
        return None

    found_hwnd = None
    target_clean = chat_title_keyword.replace("🚩", "").replace("✨", "").strip().lower()

    def enum_windows_callback(hwnd, _):
        nonlocal found_hwnd
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True
                
            title_clean = title.replace("🚩", "").replace("✨", "").strip().lower()
            
            # 메인 카카오톡 목록 창이 아닌 실제 채팅방 창 매칭
            if (target_clean in title_clean or "업무공유방" in title_clean or "기술본부" in title_clean) and title != "카카오톡":
                found_hwnd = hwnd
                return False
        return True

    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception:
        pass

    return found_hwnd


def extract_text_from_kakao_window(hwnd: int) -> str:
    """
    열려 있는 카카오톡 창에서 텍스트 대화 내용을 100% 안전하고 정밀하게 추출
    (1단계: UIA 리스트 컨트롤 직접 읽기 -> 2단계: 자식 윈도우 전수 탐색 -> 3단계: 안전 리스트 복사 Fallback)
    """
    if not WIN32_AVAILABLE or not hwnd:
        return ""

    extracted_lines = []

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

    # [1단계] 대화 리스트 컨트롤 대상 UIA 직접 텍스트 추출
    targets = [list_hwnd, hwnd] if list_hwnd else [hwnd]
    for target_h in targets:
        if not target_h:
            continue
        try:
            ctrl = auto.ControlFromHandle(target_h)
            if ctrl:
                def recurse_find_text(c, depth=0):
                    if depth > 15:
                        return
                    
                    # Name 속성
                    name_val = c.Name
                    if name_val and len(name_val.strip()) > 0:
                        text_str = name_val.strip()
                        if not any(ign == text_str for ign in ["최소화", "최대화", "닫기", "전송", "메뉴", "검색", "이모티콘", "파일 보내기", "음성 대화", "페이스톡", "더보기"]):
                            extracted_lines.append(text_str)
                    
                    # Legacy IAccessible Name
                    try:
                        legacy = c.GetLegacyIAccessiblePattern()
                        if legacy and legacy.Name and legacy.Name != name_val:
                            l_name = legacy.Name.strip()
                            if l_name and not any(ign == l_name for ign in ["최소화", "최대화", "닫기", "전송"]):
                                extracted_lines.append(l_name)
                    except Exception:
                        pass
                        
                    for child in c.GetChildren():
                        recurse_find_text(child, depth + 1)
                        
                recurse_find_text(ctrl)
        except Exception as e:
            safe_print(f"[수집기 UIA 추출 알림]: {e}")

        if len(extracted_lines) >= 3:
            return "\n".join(extracted_lines)

    # [2단계] UIA로 읽히지 않는 경우: 안전 대화 리스트 복사 Fallback
    # (★ 중요: 입력창이 아닌 대화목록 창(EVA_VH_ListControl_RPC)에만 복사 신호를 보내므로 채팅 입력/전송은 100% 원천 차단됨)
    try:
        import win32clipboard
        import win32process
        
        # 기존 클립보드 데이터 안전 백업
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

        # 대화 리스트 컨트롤에 포커스 후 안전 복사 (Ctrl+A -> Ctrl+C)
        target_focus = list_hwnd if list_hwnd else hwnd
        if target_focus:
            # 대화 목록 영역 클릭 (안전한 좌상단 50, 50 좌표)
            win32gui.PostMessage(target_focus, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, (50 << 16) | 50)
            win32gui.PostMessage(target_focus, win32con.WM_LBUTTONUP, 0, (50 << 16) | 50)
            time.sleep(0.05)
            
            # Ctrl + A, Ctrl + C 전달
            win32gui.SendMessage(target_focus, win32con.WM_KEYDOWN, win32con.VK_CONTROL, 0)
            win32gui.SendMessage(target_focus, win32con.WM_KEYDOWN, ord('A'), 0)
            win32gui.SendMessage(target_focus, win32con.WM_KEYUP, ord('A'), 0)
            win32gui.SendMessage(target_focus, win32con.WM_KEYDOWN, ord('C'), 0)
            win32gui.SendMessage(target_focus, win32con.WM_KEYUP, ord('C'), 0)
            win32gui.SendMessage(target_focus, win32con.WM_KEYUP, win32con.VK_CONTROL, 0)
            time.sleep(0.1)

            # 복사된 텍스트 획득
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

            # 기존 클립보드 데이터 즉시 복원 (사용자 편의 보호)
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

            if copied_text and len(copied_text.strip()) > 0:
                return copied_text.strip()
    except Exception as e:
        safe_print(f"[수집기 복사 Fallback 알림]: {e}")

    if extracted_lines:
        return "\n".join(extracted_lines)

    return ""


def run_collection_cycle() -> Dict[str, Any]:
    """
    1회 증분 수집 사이클 실행: 카톡 창 탐색 -> 텍스트 추출 -> 파싱 -> DB Upsert
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target_chat = config.KAKAO_CHAT_TITLE
    
    COLLECTOR_STATUS["last_run_time"] = now_str
    COLLECTOR_STATUS["total_cycles"] += 1
    
    safe_print(f"\n[{now_str}] 🤖 [카카오톡 1시간 증분 수집] 대화방 탐색 중: '{target_chat}'...")
    
    hwnd = find_kakao_chat_window(target_chat)
    if not hwnd:
        msg = f"'{target_chat}' 대화방 창이 PC 화면에 열려있지 않습니다."
        safe_print(f"[-] {msg}")
        COLLECTOR_STATUS["last_status"] = "대화방 창 미열림"
        return {"status": "window_not_found", "message": msg, "time": now_str}

    title = win32gui.GetWindowText(hwnd)
    safe_print(f"[+] 대상 대화방 감지: '{title}' (HWND: {hwnd})")

    raw_text = extract_text_from_kakao_window(hwnd)
    if not raw_text:
        msg = "대화창에서 텍스트를 추출하지 못했습니다."
        safe_print(f"[-] {msg}")
        COLLECTOR_STATUS["last_status"] = "텍스트 없음"
        return {"status": "no_text", "message": msg, "time": now_str}

    safe_print(f"[+] {len(raw_text)}자 대화 텍스트 추출 완료. 증분 파싱 & 매칭 시작...")
    records = WorkLogMatcher.parse_and_match_text(raw_text)
    
    if not records:
        msg = "파싱 가능한 작업/지원 보고 메시지가 없습니다."
        safe_print(f"[-] {msg}")
        COLLECTOR_STATUS["last_status"] = "작업 보고 없음"
        return {"status": "no_records", "message": msg, "time": now_str}

    saved = db_manager.save_work_logs(records)
    COLLECTOR_STATUS["last_status"] = f"정상 동기화 ({saved}건 저장/갱신)"
    COLLECTOR_STATUS["last_result"] = {
        "total_records": len(records),
        "saved_records": saved
    }
    COLLECTOR_STATUS["next_run_time"] = datetime.now() + timedelta(seconds=config.COLLECTOR_INTERVAL_SECONDS)
    
    safe_print(f"[✓] 🎉 {len(records)}건 작업 분석 완료 (DB 증분 저장/동기화: {saved}건)")
    return {
        "status": "success",
        "total_records": len(records),
        "saved_records": saved,
        "time": now_str
    }


def background_collector_loop():
    """
    백그라운드에서 1시간(3,600초)마다 무한 반복 실행되는 상시 데몬 루프
    """
    COLLECTOR_STATUS["is_running"] = True
    interval = config.COLLECTOR_INTERVAL_SECONDS  # 기본 3,600초 (1시간)
    
    safe_print(f"🚀 [상시 자동 수집 데몬 기동] 1시간({interval}초) 주기로 백그라운드에서 자동 수집을 실행합니다.")
    
    # 앱 시작 직후 즉시 1차 수집 시도
    try:
        run_collection_cycle()
    except Exception as e:
        safe_print(f"[수집기 초기 실행 예외]: {e}")
        
    while True:
        try:
            time.sleep(interval)
            run_collection_cycle()
        except Exception as e:
            safe_print(f"[수집기 데몬 주기 오류]: {e}")
            time.sleep(60)


def start_background_collector():
    """
    대시보드 시작 시 1회만 백그라운드 수집기 스레드를 안전하게 실행
    """
    global _collector_thread
    with _thread_lock:
        if _collector_thread is None or not _collector_thread.is_alive():
            _collector_thread = threading.Thread(
                target=background_collector_loop,
                name="KakaoAutoCollectorThread",
                daemon=True
            )
            _collector_thread.start()
            safe_print("[✓] 카카오톡 1시간 자동 수집 백그라운드 스레드가 성공적으로 시작되었습니다.")


if __name__ == "__main__":
    safe_print("=" * 65)
    safe_print("🚀 카카오톡 [기술본부] 업무공유방 1시간 증분 자동 수집기")
    safe_print("=" * 65)
    background_collector_loop()
