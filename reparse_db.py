import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"c:\Python\work-time-dashboard")
from src.config import config
from src.parser.reply_matcher import WorkLogMatcher
from src.database.supabase_client import db_manager

def reparse_and_clean_database():
    db_path = config.LOCAL_DB_PATH
    if not db_path.exists():
        print("로컬 DB가 존재하지 않습니다.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 1. 기존 DB의 모든 원본 메시지 수집
    cursor.execute("SELECT raw_start_message, raw_end_message, start_time FROM work_logs WHERE raw_start_message IS NOT NULL AND raw_start_message != ''")
    rows = cursor.fetchall()
    
    if not rows:
        print("재정제할 원본 메시지가 없습니다.")
        conn.close()
        return

    print(f"기존 DB에서 {len(rows)}건의 원본 메시지를 읽어왔습니다. 재파싱 시작...")

    # 가상 대화 텍스트 재구성
    raw_texts = []
    for r_start, r_end, s_time in rows:
        raw_texts.append(r_start)
        if r_end:
            raw_texts.append(r_end)

    combined_text = "\n".join(raw_texts)
    
    # 새로운 파서로 파싱
    new_records = WorkLogMatcher.parse_and_match_text(combined_text)
    print(f"개인별로 분리 파싱된 레코드 건수: {len(new_records)}건")

    # 기존 테이블 데이터 클리어 후 재적재
    cursor.execute("DELETE FROM work_logs")
    conn.commit()
    conn.close()

    saved = db_manager.save_work_logs(new_records)
    print(f"성공적으로 {saved}건의 개인별 작업 기록이 DB에 재적재되었습니다.")

if __name__ == "__main__":
    reparse_and_clean_database()
