from pathlib import Path
from typing import List
from ..parser.reply_matcher import WorkLogMatcher, WorkLogRecord

def create_sample_records() -> List[WorkLogRecord]:
    sample_file = Path(__file__).resolve().parent / "sample_kakao_chat.txt"
    if sample_file.exists():
        with open(sample_file, "r", encoding="utf-8") as f:
            text = f.read()
        return WorkLogMatcher.parse_and_match_text(text)
    return []
