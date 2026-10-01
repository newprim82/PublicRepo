# -*- coding: utf-8 -*-
import os
import sys
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.services.monthly_worklog_service import MonthlyWorklogService


def main():
    parser = argparse.ArgumentParser(description="팀 전월 카톡/아웃룩 엑셀 원장 정기 메일 발송 배치 스크립트")
    parser.add_argument("--team", default="기술 1팀", help="발송 대상 팀명 (기본: 기술 1팀)")
    parser.add_argument("--email", default="", help="수신 팀 대표 이메일 (지정 안할 시 설정값 사용)")
    parser.add_argument("--month", default="", help="대상 월 (예: 2026-09, 기본값: 전월)")
    args = parser.parse_args()

    team_name = args.team
    target_month = args.month or MonthlyWorklogService.get_previous_month()
    
    cfg = MonthlyWorklogService.get_team_config(team_name)
    if not cfg.get("is_active", True) and not args.email:
        print(f"[{team_name}] 월간 자동 발송 설정이 비활성화(OFF)되어 있어 발송을 건너뜁니다.")
        return

    recipient_email = args.email or cfg.get("team_email", "GE101@sangsanginworld.co.kr")

    print("==================================================")
    print(f"[월간 정기 배치] {team_name} {target_month} 전월 엑셀 원장 발송")
    print("==================================================")
    print(f"[*] 대상 팀: {team_name}")
    print(f"[*] 대상 기간: {target_month} (전월)")
    print(f"[*] 수신 팀메일: {recipient_email}")

    success, message = MonthlyWorklogService.send_monthly_team_report(
        team_name=team_name,
        recipient_email=recipient_email,
        month_str=target_month,
        dispatch_type="AUTO_MONTHLY"
    )

    print(message)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
