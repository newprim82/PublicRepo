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

from src.services.email_sender import EmailSender

def main():
    parser = argparse.ArgumentParser(description="Executive Summary 자동 이메일 발송 배치 스크립트")
    parser.add_argument("--type", choices=["weekly", "monthly"], default="weekly", help="발송 주기 (weekly: 주간 자동, monthly: 월간 자동)")
    parser.add_argument("--team", default="기술 1팀", help="대상 팀명 (기본: 기술 1팀)")
    parser.add_argument("--recipients", default="", help="수신자 이메일 목록 (쉼표 구분)")
    args = parser.parse_args()

    dispatch_type = "AUTO_MONTHLY" if args.type == "monthly" else "AUTO_WEEKLY"
    report_title = "월간 자동 보고서" if args.type == "monthly" else "주간 자동 보고서"

    print("==================================================")
    print(f"[{report_title}] Executive Summary Email Sending ({dispatch_type})")
    print("==================================================")
    
    recipients = args.recipients or os.getenv("REPORT_RECIPIENT_EMAILS", "ymmoon@sangsanginworld.co.kr")
    sender = os.getenv("GMAIL_SENDER_EMAIL", "newprim82@gmail.com")
    pwd = os.getenv("GMAIL_APP_PASSWORD", "dlugbvfuhgdozkgr")
    
    print(f"[*] 발신자: {sender}")
    print(f"[*] 수신자: {recipients}")
    print(f"[*] 대상 팀: {args.team}")
    print(f"[*] 발송 유형: {dispatch_type}")
    
    success, message = EmailSender.send_weekly_report(
        recipient_emails=recipients,
        sender_email=sender,
        sender_password=pwd,
        selected_team=args.team,
        dispatch_type=dispatch_type
    )
    
    print(message)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
