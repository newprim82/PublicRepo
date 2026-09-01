import time
import sys
import os
from datetime import datetime
from typing import Optional, List

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
    print("[경고] pywin32 / uiautomation 라이브러리가 설치되지 않았거나 비-Windows 환경입니다.")


def find_kakao_chat_window(chat_title_keyword: str) -> Optional[int]:
    """
    지정된 키워드가 포함된 카카오톡 채팅방 창 핸들(HWND)을 검색
    """
    if not WIN32_AVAILABLE:
        return None

    found_hwnd = None

    def enum_windows_callback(hwnd, _):
        nonlocal found_hwnd
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            
            # 카카오톡 메인 창이 아닌 대화방 창 클래스(#32770 or EVA_Window 등) 및 제목 매칭
            if chat_title_keyword.lower() in title.lower() and "카카오톡" not in title:
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
    열려 있는 카카오톡 창에서 텍스트 대화 내용을 추출
    """
    if not WIN32_AVAILABLE or not hwnd:
        return ""

    extracted_text = ""

    # 방법 1: UI Automation을 통한 직접 텍스트 추출 (클립보드 방해 없음)
    try:
        control = auto.ControlFromHandle(hwnd)
        if control:
            # 채팅 메시지 리스트 컨트롤 탐색
            items = control.GetChildren()
            texts = []
            
            def recurse_find_text(ctrl, depth=0):
                if depth > 6:
                    return
                # TextControl 또는 Name 속성 수집
                name_val = ctrl.Name
                if name_val and len(name_val.strip()) > 1:
                    texts.append(name_val.strip())
                for child in ctrl.GetChildren():
                    recurse_find_text(child, depth + 1)
                    
            recurse_find_text(control)
            if texts:
                extracted_text = "\n".join(texts)
    except Exception as e:
        print(f"[수집 디버그] UIA 직접 추출 시도 중 알림: {e}")

    # 방법 2: 만약 UIA 추출 텍스트가 부족하다면 안전한 창 복사(Ctrl+A/Ctrl+C) 시도
    # (선택적으로 보조)
    return extracted_text


def run_collection_cycle() -> int:
    """
    1회 수집 사이클 실행: 카톡 창 탐색 -> 텍스트 추출 -> 파싱 -> DB Upsert
    """
    target_chat = config.KAKAO_CHAT_TITLE
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 카카오톡 대화방 검색 중: '{target_chat}'...")
    
    hwnd = find_kakao_chat_window(target_chat)
    if not hwnd:
        print(f"[-] '{target_chat}' 카카오톡 채팅방 창을 찾을 수 없습니다.")
        print("    💡 카카오톡 PC 버전에서 해당 대화방 창을 열어두었는지 확인해주세요.")
        return 0

    title = win32gui.GetWindowText(hwnd)
    print(f"[+] 대상 채팅방 창 감지됨: '{title}' (HWND: {hwnd})")

    raw_text = extract_text_from_kakao_window(hwnd)
    if not raw_text:
        print("[-] 채팅창에서 추출된 텍스트가 없습니다.")
        return 0

    print(f"[+] {len(raw_text)}자 텍스트 추출 완료. 파싱 시작...")
    records = WorkLogMatcher.parse_and_match_text(raw_text)
    
    if not records:
        print("[-] 파싱 가능한 작업/지원 보고 메시지가 없습니다.")
        return 0

    saved = db_manager.save_work_logs(records)
    print(f"[✓] 총 {len(records)}건의 작업 기록 분석 완료 (DB 저장/동기화: {saved}건)")
    return saved


def start_collector_daemon():
    """
    10분(설정된 주기)마다 자동으로 수집을 반복하는 데몬 프로세스
    """
    interval = config.COLLECTOR_INTERVAL_SECONDS
    print("=" * 65)
    print("🚀 카카오톡 작업 지원 시간 자동 수집 데몬 (PC 카카오톡 연동)")
    print(f"• 대상 대화방 키워드: {config.KAKAO_CHAT_TITLE}")
    print(f"• 수집 주기: {interval}초 ({interval // 60}분 단위)")
    print(f"• DB 모드: {'Supabase Cloud' if db_manager.use_supabase else 'Local SQLite'}")
    print("=" * 65)

    while True:
        try:
            run_collection_cycle()
        except Exception as e:
            print(f"[오류 발생] 수집 주기 실행 중 예외: {e}")

        print(f"⏳ 다음 수집까지 {interval // 60}분 대기합니다... (종료: Ctrl + C)")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 수집기 데몬을 종료합니다.")
            break


if __name__ == "__main__":
    start_collector_daemon()
