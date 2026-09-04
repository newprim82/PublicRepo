import os
import smtplib
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import make_msgid, formatdate
from email.header import Header
from typing import List, Union, Tuple, Optional
from datetime import datetime

from .email_report_service import EmailReportService

def get_secret(key: str, default: str = "") -> str:
    """Streamlit secrets 또는 OS 환경변수에서 안전하게 설정값을 가져옵니다."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            val = str(st.secrets[key]).strip()
            if val:
                return val
    except Exception:
        pass
    val = os.getenv(key, "").strip()
    return val if val else default

DEFAULT_SENDER = "newprim82@gmail.com"
DEFAULT_APP_PWD = "dlugbvfuhgdozkgr"
DEFAULT_RECIPIENT = "ymmoon@sangsanginworld.co.kr"

class EmailSender:
    @staticmethod
    def send_weekly_report(
        recipient_emails: Optional[Union[str, List[str]]] = None,
        sender_email: Optional[str] = None,
        sender_password: Optional[str] = None,
        target_week_label: Optional[str] = None,
        selected_team: str = "기술 1팀",
        df_active_override: Optional[Any] = None,
        prev_df_override: Optional[Any] = None,
        ai_briefing_override: Optional[Dict[str, Any]] = None,
        current_period_label_override: Optional[str] = None,
        available_weeks_override: Optional[List[str]] = None,
        df_scope_override: Optional[Any] = None,
        team_mappings_override: Optional[dict] = None
    ) -> Tuple[bool, str]:
        """
        Gmail SMTP를 통해 주간/월간 Executive Summary 보고서를 발송합니다.
        대시보드 화면에서 보고 있는 데이터셋(df_active) 및 AI 브리핑을 온전히 전달받아 동기화 발송합니다.
        
        Returns:
            (success: bool, message: str)
        """
        sender = "newprim82@gmail.com"
        # 🛡️ 구글에서 발급된 16자리 앱 비밀번호 직통 적용 (Secrets 오염 완전 방어)
        password = "dlugbvfuhgdozkgr"
        if sender_password:
            clean_input_pwd = str(sender_password).replace(" ", "").strip()
            if len(clean_input_pwd) == 16 and clean_input_pwd.isalpha():
                password = clean_input_pwd
        
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
                selected_team=selected_team,
                df_active_override=df_active_override,
                prev_df_override=prev_df_override,
                ai_briefing_override=ai_briefing_override,
                current_period_label_override=current_period_label_override,
                available_weeks_override=available_weeks_override,
                df_scope_override=df_scope_override,
                team_mappings_override=team_mappings_override
            )

            # 2. 이메일 메시지 조립 (기업 스팸 필터 통과를 위한 RFC 표준 헤더 완비)
            msg = MIMEMultipart("mixed")
            msg["Subject"] = Header(subject, "utf-8")
            from_name_b64 = base64.b64encode("기술본부 업무관제 시스템".encode("utf-8")).decode("ascii")
            msg["From"] = f"=?UTF-8?B?{from_name_b64}?= <{sender}>"
            msg["To"] = ", ".join(recipients)
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain="gmail.com")
            msg["Reply-To"] = sender
            msg["X-Mailer"] = "WorkTime Dashboard Executive Reporter v2.0"

            # HTML 본문 추가
            msg_body = MIMEMultipart("alternative")
            html_part = MIMEText(html_content, "html", "utf-8")
            msg_body.attach(html_part)
            msg.attach(msg_body)

            # 엑셀 파일 첨부 (표준 인코딩 파일명)
            if excel_bytes:
                excel_attachment = MIMEApplication(excel_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                today_str = datetime.now().strftime("%Y%m%d")
                excel_attachment.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=f"Weekly_Report_{today_str}.xlsx"
                )
                msg.attach(excel_attachment)

            # 3. Gmail SMTP 발송 (SSL 465 시도 -> TLS 587 Fallback)
            try:
                server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15)
                server.login(sender, password)
                server.sendmail(sender, recipients, msg.as_string())
                server.quit()
            except Exception:
                server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
                server.starttls()
                server.login(sender, password)
                server.sendmail(sender, recipients, msg.as_string())
                server.quit()

            return True, f"✅ {', '.join(recipients)} (총 {len(recipients)}명)에게 주간 보고서가 성공적으로 발송되었습니다!"

        except smtplib.SMTPAuthenticationError as e:
            return False, f"❌ Gmail 인증 실패: 구글 앱 비밀번호를 확인해주세요. ({e})"
        except Exception as e:
            return False, f"❌ 이메일 발송 실패: {str(e)}"
