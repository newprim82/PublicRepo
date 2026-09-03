import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import List, Union, Tuple, Optional
from datetime import datetime

from .email_report_service import EmailReportService

DEFAULT_SENDER = os.getenv("GMAIL_SENDER_EMAIL", "newprim82@gmail.com")
DEFAULT_APP_PWD = os.getenv("GMAIL_APP_PASSWORD", "dlugbvfuhgdozkgr")
DEFAULT_RECIPIENT = os.getenv("DEFAULT_RECIPIENT_EMAIL", "ymmoon@sangsanginworld.co.kr")

class EmailSender:
    @staticmethod
    def send_weekly_report(
        recipient_emails: Optional[Union[str, List[str]]] = None,
        sender_email: Optional[str] = None,
        sender_password: Optional[str] = None,
        target_week_label: Optional[str] = None,
        selected_team: str = "전체"
    ) -> Tuple[bool, str]:
        """
        Gmail SMTP를 통해 주간 Executive Summary 보고서를 발송합니다.
        
        Returns:
            (success: bool, message: str)
        """
        sender = sender_email or os.getenv("GMAIL_SENDER_EMAIL", DEFAULT_SENDER)
        password = sender_password or os.getenv("GMAIL_APP_PASSWORD", DEFAULT_APP_PWD)
        
        if not recipient_emails:
            recipients = [DEFAULT_RECIPIENT]
        elif isinstance(recipient_emails, str):
            recipients = [r.strip() for r in recipient_emails.split(",") if r.strip()]
        else:
            recipients = recipient_emails

        if not recipients:
            return False, "수신자 이메일 주소가 지정되지 않았습니다."

        try:
            # 1. 보고서 HTML 및 엑셀 생성
            subject, html_content, excel_bytes = EmailReportService.generate_weekly_report(
                target_week_label=target_week_label,
                selected_team=selected_team
            )

            # 2. 이메일 메시지 조립
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = f"기술본부 업무관제 시스템 <{sender}>"
            msg["To"] = ", ".join(recipients)

            # HTML 본문 추가
            msg_body = MIMEMultipart("alternative")
            html_part = MIMEText(html_content, "html", "utf-8")
            msg_body.attach(html_part)
            msg.attach(msg_body)

            # 엑셀 파일 첨부
            if excel_bytes:
                excel_attachment = MIMEApplication(excel_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                excel_attachment.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=f"주간_작업실적_요약_{datetime.now().strftime('%Y%m%d')}.xlsx"
                )
                msg.attach(excel_attachment)

            # 3. Gmail SMTP 발송 (TLS 587)
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
            server.quit()

            return True, f"✅ {', '.join(recipients)} (총 {len(recipients)}명)에게 주간 보고서가 성공적으로 발송되었습니다!"

        except smtplib.SMTPAuthenticationError as e:
            return False, f"❌ Gmail 인증 실패: Google 2단계 인증 계정은 16자리 '앱 비밀번호'가 필요합니다. ({e})"
        except Exception as e:
            return False, f"❌ 이메일 발송 실패: {str(e)}"
