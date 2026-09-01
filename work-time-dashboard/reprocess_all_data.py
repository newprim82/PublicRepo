import sys
import sqlite3
from datetime import datetime
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.config import config
from src.parser.kakao_parser import KakaoMessageParser, RawKakaoMessage
from src.parser.reply_matcher import WorkLogMatcher
from src.database.supabase_client import db_manager

# 1. DB에서 모든 원본 메시지 추출
conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
cursor = conn.cursor()
cursor.execute("SELECT raw_start_message, raw_end_message, start_time, end_time, worker_name FROM work_logs ORDER BY start_time ASC")
rows = cursor.fetchall()
conn.close()

print(f"기존 DB 원본 레코드 수: {len(rows)}건")

# 원본 메시지들을 시간순 RawKakaoMessage 리스트로 재구성
raw_msgs = []
for r in rows:
    start_msg = r[0]
    end_msg = r[1]
    st_time_str = r[2]
    
    if st_time_str:
        try:
            st_dt = datetime.fromisoformat(st_time_str)
        except Exception:
            continue
            
        if start_msg:
            raw_msgs.append(RawKakaoMessage(
                raw_text=start_msg,
                sender_profile=f"상상인 {r[4]} / 기술 1팀",
                timestamp=st_dt,
                content=start_msg,
                body_content=start_msg
            ))
            
        if end_msg:
            # 완료 보고는 끝난 시각
            end_dt = st_dt
            if r[3]:
                try:
                    end_dt = datetime.fromisoformat(r[3])
                except Exception:
                    pass
            raw_msgs.append(RawKakaoMessage(
                raw_text=end_msg,
                sender_profile=f"상상인 {r[4]} / 기술 1팀",
                timestamp=end_dt,
                content=end_msg,
                body_content=end_msg
            ))

print(f"재구성된 메시지 수: {len(raw_msgs)}건")

# 2. 최신 매처 엔진으로 매칭 실행
new_records = WorkLogMatcher.match_messages(raw_msgs)
print(f"최신 엔진으로 정밀 매칭된 레코드 수: {len(new_records)}건")

# 3. DB 초기화 후 재적재
db_manager.clear_all_data()
db_manager.save_work_logs(new_records)

# 4. 한화손보 VPN 실사 결과 확인
df = db_manager.fetch_all_work_logs()
hanhwa_vpn = df[df["client_name"].str.contains("한화", na=False) & df["task_description"].str.contains("VPN", na=False)]
print(f"\n[한화손보 VPN 실사 매칭 결과 총 {len(hanhwa_vpn)}건]:")
for idx, r in hanhwa_vpn.iterrows():
    print(f"  [{r['status']}] {r['start_time']} | {r['worker_name']} | {r['client_name']} | 예정: {r['estimated_hours']}h | 소요: {r['actual_hours']}h")

