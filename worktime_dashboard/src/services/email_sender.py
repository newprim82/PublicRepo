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
from .authorized_recipient_service import AuthorizedRecipientService

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
        team_mappings_override: Optional[dict] = None,
        dispatch_type: str = "MANUAL_IMMEDIATE",
        **kwargs
    ) -> Tuple[bool, str]:
        """
        Gmail SMTP를 통해 주간/월간 업무 실적 Summary 보고서를 발송합니다.
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

        # 🔒 보안 통제: 수신자를 비용산정 승인 그룹(auth)과 일반 그룹(unauth)으로 자동 분리
        auth_recipients = AuthorizedRecipientService.get_authorized_in_list(recipients)
        unauth_recipients = AuthorizedRecipientService.get_unauthorized_recipients(recipients)

        # 발송 작업 목록 구성 [(수신자목록, include_cost)]
        dispatch_tasks = []
        if auth_recipients:
            dispatch_tasks.append((auth_recipients, True))
        if unauth_recipients:
            dispatch_tasks.append((unauth_recipients, False))

        try:
            today_str = datetime.now().strftime("%Y%m%d")

            for group_recipients, include_cost in dispatch_tasks:
                report_res = EmailReportService.generate_weekly_report(
                    target_week_label=target_week_label,
                    selected_team=selected_team,
                    df_active_override=df_active_override,
                    prev_df_override=prev_df_override,
                    ai_briefing_override=ai_briefing_override,
                    current_period_label_override=current_period_label_override,
                    available_weeks_override=available_weeks_override,
                    df_scope_override=df_scope_override,
                    team_mappings_override=team_mappings_override,
                    include_cost_estimation=include_cost,
                    return_cost_excel=True,
                    **kwargs
                )
                if len(report_res) == 4:
                    subject, html_content, excel_bytes, cost_excel_bytes = report_res
                else:
                    subject, html_content, excel_bytes = report_res
                    cost_excel_bytes = None

                # 2. 이메일 메시지 조립 (기업 스팸 필터 통과를 위한 RFC 표준 헤더 완비)
                msg = MIMEMultipart("mixed")
                msg["Subject"] = Header(subject, "utf-8")
                from_name_b64 = base64.b64encode("기술본부 업무관제 시스템".encode("utf-8")).decode("ascii")
                msg["From"] = f"=?UTF-8?B?{from_name_b64}?= <{sender}>"
                msg["To"] = ", ".join(group_recipients)
                msg["Date"] = formatdate(localtime=True)
                msg["Message-ID"] = make_msgid(domain="gmail.com")
                msg["Reply-To"] = sender
                msg["X-Mailer"] = "WorkTime Dashboard Summary Reporter v2.0"

                # HTML 본문 추가
                msg_body = MIMEMultipart("alternative")
                html_part = MIMEText(html_content, "html", "utf-8")
                msg_body.attach(html_part)
                msg.attach(msg_body)

                # 엑셀 파일 첨부 (표준 인코딩 파일명)
                if excel_bytes:
                    excel_attachment = MIMEApplication(excel_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    excel_attachment.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=f"Work_Summary_{today_str}.xlsx"
                    )
                    msg.attach(excel_attachment)

                # 🔒 사전 등록 수신자일 경우: 예상 비용산정 전용 엑셀(첫 탭 요약표, 2번째 탭부터 개인장표) 추가 첨부
                if include_cost and cost_excel_bytes:
                    cost_attachment = MIMEApplication(cost_excel_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    cost_attachment.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=f"Estimated_Cost_Report_{today_str}.xlsx"
                    )
                    msg.attach(cost_attachment)

                # 3. Gmail SMTP 발송 (SSL 465 시도 -> TLS 587 Fallback)
                try:
                    server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15)
                    server.login(sender, password)
                    server.sendmail(sender, group_recipients, msg.as_string())
                    server.quit()
                except Exception:
                    server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
                    server.starttls()
                    server.login(sender, password)
                    server.sendmail(sender, group_recipients, msg.as_string())
                    server.quit()

                # DB 발송 이력 기록
                try:
                    from .email_dispatch_service import EmailDispatchService
                    EmailDispatchService.record_dispatch(
                        dispatch_type=dispatch_type,
                        recipient_emails=", ".join(group_recipients),
                        sender_email=sender,
                        selected_team=selected_team,
                        period_label=current_period_label_override or target_week_label or f"{selected_team} 서머리",
                        subject=subject,
                        status="SUCCESS"
                    )
                except Exception as log_err:
                    print(f"[EmailSender] DB 로깅 알림: {log_err}")

            # 완료 알림 메시지 구성
            if auth_recipients and unauth_recipients:
                success_msg = (
                    f"✅ 총 {len(recipients)}명에게 권한별 맞춤 발송 완료! "
                    f"(💰 비용산정 포함 {len(auth_recipients)}명: {', '.join(auth_recipients)} / "
                    f"📋 실적만 포함 {len(unauth_recipients)}명: {', '.join(unauth_recipients)})"
                )
            elif auth_recipients:
                success_msg = f"✅ {', '.join(auth_recipients)} (총 {len(auth_recipients)}명)에게 주간 보고서가 성공적으로 발송되었습니다! (💰 예상 비용산정 대시보드 및 정산 엑셀 안전 포함)"
            else:
                success_msg = f"✅ {', '.join(unauth_recipients)} (총 {len(unauth_recipients)}명)에게 주간 보고서가 성공적으로 발송되었습니다! (📋 일반 업무 실적 보고서)"

            return True, success_msg

        except smtplib.SMTPAuthenticationError as e:
            err_msg = f"❌ Gmail 인증 실패: 구글 앱 비밀번호를 확인해주세요. ({e})"
            try:
                from .email_dispatch_service import EmailDispatchService
                EmailDispatchService.record_dispatch(
                    dispatch_type=dispatch_type,
                    recipient_emails=", ".join(recipients) if 'recipients' in locals() else str(recipient_emails or ''),
                    sender_email=sender,
                    selected_team=selected_team,
                    period_label=current_period_label_override or target_week_label or f"{selected_team} 서머리",
                    subject=locals().get('subject', '업무 실적 Summary 보고서'),
                    status="FAILED",
                    error_message=err_msg
                )
            except Exception:
                pass
            return False, err_msg
        except Exception as e:
            err_msg = f"❌ 이메일 발송 실패: {str(e)}"
            try:
                from .email_dispatch_service import EmailDispatchService
                EmailDispatchService.record_dispatch(
                    dispatch_type=dispatch_type,
                    recipient_emails=", ".join(recipients) if 'recipients' in locals() else str(recipient_emails or ''),
                    sender_email=sender,
                    selected_team=selected_team,
                    period_label=current_period_label_override or target_week_label or f"{selected_team} 서머리",
                    subject=locals().get('subject', '업무 실적 Summary 보고서'),
                    status="FAILED",
                    error_message=err_msg
                )
            except Exception:
                pass
            return False, err_msg
