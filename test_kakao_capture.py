import os
import sys
import time
from pathlib import Path

# 프로젝트 루트 추가
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.collector.kakao_auto_collector import find_kakao_chat_window, extract_text_from_kakao_window
from src.parser.reply_matcher import WorkLogMatcher
from src.database.supabase_client import db_manager

def main():
    print("="*60)
    print("[KAKAO CAPTURE TEST SCRIPT]")
    print("="*60)

    # 1. 창 찾기
    print("\n[Step 1] Searching for KakaoTalk chat window...")
    target_keyword = "[기술본부] 업무공유방"
    hwnd = find_kakao_chat_window(target_keyword)
    if not hwnd:
        print(f"[-] Chat window with keyword '{target_keyword}' not found.")
        print("Listing all visible windows:")
        import win32gui
        def enum_all(h, _):
            if win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h)
                if t and len(t.strip()) > 0:
                    try:
                        print(f"  - HWND={h} | Title='{t}'")
                    except Exception:
                        pass
            return True
        win32gui.EnumWindows(enum_all, None)
        return

    print(f"[OK] Found window! HWND={hwnd}")

    # 2. 텍스트 추출
    print("\n[Step 2] Extracting text from chat window...")
    text = extract_text_from_kakao_window(hwnd, is_manual=True)
    if not text:
        print("[-] Text extraction failed!")
        return

    print(f"[OK] Text extraction success! (Total {len(text)} chars, {len(text.splitlines())} lines)")
    print("\n[Extracted text last 10 lines]:")
    for line in text.splitlines()[-10:]:
        print("  >", line)

    # 3. 파싱 및 매칭
    print("\n[Step 3] Parsing and matching work logs...")
    records = WorkLogMatcher.parse_and_match_text(text)
    print(f"[OK] Parsing complete: Total {len(records)} records found")

    for r in records[-5:]:
        print(f"  - [{r.start_time.strftime('%H:%M')}] {r.worker_name} | {r.client_name} | {r.task_description[:30]} | {r.status}")

    # 4. Supabase DB 저장
    print("\n[Step 4] Upserting to Supabase Cloud DB...")
    saved = db_manager.save_work_logs(records)
    print(f"[SUCCESS] Total {saved} records synchronized to Supabase!")

if __name__ == "__main__":
    main()
