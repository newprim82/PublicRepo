import os
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.services.email_sender import EmailSender

def main():
    print("==================================================")
    print("📧 [주간 정기 보고] 기술본부 Executive Summary 이메일 자동 발송")
    print("==================================================")
    
    recipients = os.getenv("REPORT_RECIPIENT_EMAILS", "ymmoon@sangsanginworld.co.kr")
    sender = os.getenv("GMAIL_SENDER_EMAIL", "newprim82@gmail.com")
    pwd = os.getenv("GMAIL_APP_PASSWORD", "Rlarudgus1!")
    
    print(f"[*] 발신자: {sender}")
    print(f"[*] 수신자: {recipients}")
    
    success, message = EmailSender.send_weekly_report(
        recipient_emails=recipients,
        sender_email=sender,
        sender_password=pwd,
        selected_team="전체"
    )
    
    print(message)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
