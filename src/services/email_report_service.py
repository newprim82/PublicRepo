import io
from datetime import datetime, timedelta, timezone
import pandas as pd
from typing import Dict, Any, Tuple, Optional

from ..database.supabase_client import DatabaseManager
from ..services.team_service import TeamService, UNASSIGNED_TEAM
from ..services.client_normalizer import normalize_client_name
from ..services.ai_briefing_service import FactExtractor, AIBriefingService

KST = timezone(timedelta(hours=9))

class EmailReportService:
    @staticmethod
    def generate_weekly_report(
        target_week_label: Optional[str] = None,
        selected_team: str = "전체"
    ) -> Tuple[str, str, bytes]:
        db = DatabaseManager()
        df_raw = db.fetch_all_work_logs()
        
        if df_raw.empty:
            return "📊 [주간 업무 보고] 데이터 없음", "<p>조회된 업무 내역이 없습니다.</p>", b""
            
        df = df_raw.copy()
        df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
        df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
        
        # 🏢 고객사명 대소문자/띄어쓰기 표준화
        if "client_name" in df.columns:
            df["client_name"] = df["client_name"].apply(normalize_client_name)
            
        team_mappings = TeamService.get_team_mappings()
        df["worker_team"] = df["worker_name"].map(team_mappings).fillna(df["worker_team"]).fillna(UNASSIGNED_TEAM)
        
        # 멀티데이 중복 배제
        if "task_description" in df.columns:
            split_mask = df["task_description"].astype(str).str.contains(r"\(\d+/\d+일차\)", regex=True)
            if split_mask.any():
                splits = df[split_mask]
                dup_origin_indices = []
                for idx, r in df[~split_mask].iterrows():
                    st_t = r.get("start_time")
                    et_t = r.get("end_time")
                    if pd.notna(st_t) and pd.notna(et_t) and st_t.date() != et_t.date():
                        m_splits = splits[
                            (splits["worker_name"] == r["worker_name"]) &
                            (splits["client_name"] == r["client_name"]) &
                            (pd.to_datetime(splits["start_time"]) >= st_t.floor("D")) &
                            (pd.to_datetime(splits["start_time"]) <= et_t.ceil("D"))
                        ]
                        if not m_splits.empty:
                            dup_origin_indices.append(idx)
                if dup_origin_indices:
                    df = df.drop(index=dup_origin_indices).reset_index(drop=True)

        def get_week_label(dt):
            if pd.isna(dt):
                return ""
            mon = dt - timedelta(days=dt.weekday())
            sun = mon + timedelta(days=6)
            week_of_month = (mon.day - 1) // 7 + 1
            return f"{mon.strftime('%Y-%m')} {week_of_month}주차 ({mon.strftime('%m/%d')}~{sun.strftime('%m/%d')})"

        df["week_label"] = df["start_time"].apply(get_week_label)
        available_weeks = sorted(df["week_label"].dropna().unique())
        if not available_weeks:
            return "📊 [주간 업무 보고] 데이터 없음", "<p>주차 데이터가 없습니다.</p>", b""
            
        current_week = target_week_label if (target_week_label and target_week_label in available_weeks) else available_weeks[-1]
        
        df_active = df[df["week_label"] == current_week].copy()
        if selected_team != "전체":
            df_active = df_active[df_active["worker_team"] == selected_team]
            
        cur_min_dt = df_active["start_time"].min() if not df_active.empty else None
        prev_df = pd.DataFrame()
        if cur_min_dt is not None:
            cur_monday = cur_min_dt - pd.Timedelta(days=cur_min_dt.weekday())
            cur_monday_start = cur_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            prev_monday_start = cur_monday_start - pd.Timedelta(days=7)
            prev_sunday_end = cur_monday_start - pd.Timedelta(seconds=1)
            
            raw_dt = df["start_time"]
            prev_df = df[(raw_dt >= prev_monday_start) & (raw_dt <= prev_sunday_end)].copy()
            if selected_team != "전체" and not prev_df.empty:
                prev_df = prev_df[prev_df["worker_team"] == selected_team]

        tot_hours = round(df_active["actual_hours"].sum(), 1) if not df_active.empty else 0.0
        tot_cnt = len(df_active)
        tot_workers = df_active["worker_name"].nunique() if not df_active.empty else 0
        tot_clients = df_active["client_name"].nunique() if not df_active.empty else 0
        avg_hours = round(tot_hours / tot_workers, 1) if tot_workers > 0 else 0.0
        
        est_df = df_active[df_active["estimated_hours"] > 0] if not df_active.empty else pd.DataFrame()
        if not est_df.empty:
            on_time_cnt = (est_df["actual_hours"] <= est_df["estimated_hours"]).sum()
            overdue_cnt = (est_df["actual_hours"] > est_df["estimated_hours"]).sum()
            on_time_rate = round((on_time_cnt / len(est_df)) * 100, 1)
        else:
            on_time_rate = 100.0
            overdue_cnt = 0

        prev_tot_hours = round(prev_df["actual_hours"].sum(), 1) if not prev_df.empty else None
        prev_avg_hours = round(prev_tot_hours / prev_df["worker_name"].nunique(), 1) if (not prev_df.empty and prev_df["worker_name"].nunique() > 0) else None
        prev_tot_clients = prev_df["client_name"].nunique() if not prev_df.empty else None

        def calc_delta(cur, prev):
            if prev is None or prev == 0:
                return "전주 비교불가"
            diff = cur - prev
            pct = (diff / prev) * 100
            sign = "+" if diff > 0 else ""
            return f"{sign}{diff:.1f} ({sign}{pct:.1f}% vs 전주)"

        delta_hours_str = calc_delta(tot_hours, prev_tot_hours)
        delta_avg_str = calc_delta(avg_hours, prev_avg_hours)
        delta_clients_str = calc_delta(tot_clients, prev_tot_clients)

        danger_names, caution_names, safe_names = [], [], []
        worker_hours = df_active.groupby("worker_name")["actual_hours"].sum().to_dict() if ("worker_name" in df_active.columns and not df_active.empty) else {}
        if not df_active.empty:
            all_active = list(df_active["worker_name"].dropna().unique())
            wk_agg = df_active.groupby(["worker_name", "week_label"])["actual_hours"].sum().reset_index()
            danger_workers = wk_agg[wk_agg["actual_hours"] > 52]["worker_name"].unique()
            caution_workers = wk_agg[(wk_agg["actual_hours"] > 40) & (wk_agg["actual_hours"] <= 52)]["worker_name"].unique()
            danger_names = sorted(list(danger_workers), key=lambda w: worker_hours.get(w, 0.0), reverse=True)
            caution_names = sorted([w for w in caution_workers if w not in danger_names], key=lambda w: worker_hours.get(w, 0.0), reverse=True)
            safe_names = sorted([w for w in all_active if w not in danger_names and w not in caution_names], key=lambda w: worker_hours.get(w, 0.0), reverse=True)

        client_agg = df_active.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(5) if not df_active.empty else pd.Series()
        top_clients_summary = ", ".join([f"{cn}({round(ch,1)}h)" for cn, ch in client_agg.head(3).items()]) if not client_agg.empty else "없음"
        top3_share = round((client_agg.head(3).sum() / tot_hours) * 100, 1) if tot_hours > 0 else 0.0

        night_hours = round(df_active[df_active["is_night_work"] == True]["actual_hours"].sum(), 1) if ("is_night_work" in df_active.columns and not df_active.empty) else 0.0
        wknd_hours = round(df_active[df_active["is_weekend_work"] == True]["actual_hours"].sum(), 1) if ("is_weekend_work" in df_active.columns and not df_active.empty) else 0.0
        night_pct = round((night_hours / tot_hours) * 100, 1) if tot_hours > 0 else 0.0
        wknd_pct = round((wknd_hours / tot_hours) * 100, 1) if tot_hours > 0 else 0.0

        worker_agg = df_active.groupby("worker_name")["actual_hours"].sum().sort_values(ascending=False).head(5) if not df_active.empty else pd.Series()

        subject = f"📊 [주간 업무 실적 요약] {selected_team} - {current_week}"

        client_rows_html = ""
        for rank, (c_name, c_h) in enumerate(client_agg.items(), 1):
            c_share = round((c_h / tot_hours) * 100, 1) if tot_hours > 0 else 0.0
            sub_c = df_active[df_active["client_name"] == c_name]
            tasks = ", ".join(sub_c["task_description"].dropna().unique()[:2])
            client_rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 9px 12px; font-weight: bold; color: #005073; text-align: center;">{rank}위</td>
                <td style="padding: 9px 12px; font-weight: bold; color: #0f172a;">{c_name}</td>
                <td style="padding: 9px 12px; text-align: right; color: #0284c7; font-weight: bold;">{c_h:.1f}h</td>
                <td style="padding: 9px 12px; text-align: right; color: #64748b;">{c_share}%</td>
                <td style="padding: 9px 12px; color: #475569;">{tasks}</td>
            </tr>
            """

        worker_rows_html = ""
        for rank, (w_name, w_h) in enumerate(worker_agg.items(), 1):
            sub_w = df_active[df_active["worker_name"] == w_name]
            w_team = sub_w["worker_team"].iloc[0] if "worker_team" in sub_w.columns else UNASSIGNED_TEAM
            w_cnt = len(sub_w)
            top_c = sub_w.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(2)
            top_c_str = ", ".join([f"{cn}({round(ch,1)}h)" for cn, ch in top_c.items()])
            worker_rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 9px 12px; font-weight: bold; color: #005073; text-align: center;">{rank}위</td>
                <td style="padding: 9px 12px; font-weight: bold; color: #0f172a;">{w_name}</td>
                <td style="padding: 9px 12px; color: #64748b;">{w_team}</td>
                <td style="padding: 9px 12px; text-align: center; color: #475569;">{w_cnt}건</td>
                <td style="padding: 9px 12px; text-align: right; color: #0284c7; font-weight: bold;">{w_h:.1f}h</td>
                <td style="padding: 9px 12px; color: #475569;">{top_c_str}</td>
            </tr>
            """

        danger_str_list = [f"{w}({worker_hours.get(w, 0.0):.1f}h)" for w in danger_names]
        caution_str_list = [f"{w}({worker_hours.get(w, 0.0):.1f}h)" for w in caution_names]
        safe_str_list = [f"{w}({worker_hours.get(w, 0.0):.1f}h)" for w in safe_names]

        danger_badge = f"<span style='color: #dc2626; font-weight: bold;'>🚨 52h 초과({len(danger_names)}명: {', '.join(danger_str_list)})</span>" if danger_names else "<span style='color: #16a34a; font-weight: bold;'>🟢 52h 초과 없음 (안전)</span>"

        # 🌟 다차원 팩트 추출(2번) + AI 브리핑(1번) 연동
        facts = FactExtractor.extract_facts(df_active, prev_df, selected_team, current_week)
        ai_briefing = AIBriefingService.generate_briefing(facts, force_refresh=True)
        briefing_source = ai_briefing.get("source", "📊 다차원 팩트 분석 엔진")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 760px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;">
                <tr>
                    <td style="background: linear-gradient(135deg, #002d42 0%, #005073 100%); padding: 24px 30px; color: #ffffff;">
                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
                            <tr>
                                <td>
                                    <div style="font-size: 20px; font-weight: 800; letter-spacing: -0.5px;">📊 기술본부 주간 작업 실적 Executive Summary</div>
                                    <div style="font-size: 13px; color: #bae6fd; margin-top: 6px;">📅 대상 기간: <b>{current_week}</b> | 부서: <b>{selected_team}</b></div>
                                </td>
                                <td style="text-align: right; vertical-align: middle;">
                                    <span style="background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.3); color: #ffffff; padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: bold;">
                                        정기 자동 발송
                                    </span>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 24px 30px;">
                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 12px;">🏛️ 1. 핵심 성과 지표 (WoW 전주 대비)</div>
                        <table width="100%" cellpadding="0" cellspacing="8" border="0" style="margin-bottom: 20px;">
                            <tr>
                                <td width="25%" style="background: #f8fafc; border: 1px solid #e2e8f0; border-top: 4px solid #005073; border-radius: 8px; padding: 14px; text-align: center;">
                                    <div style="font-size: 11.5px; color: #64748b; font-weight: bold;">⏱️ 총 투입 공수</div>
                                    <div style="font-size: 22px; font-weight: 900; color: #005073; margin: 4px 0;">{tot_hours:,}h</div>
                                    <div style="font-size: 10.5px; color: #0284c7; font-weight: bold;">{delta_hours_str}</div>
                                </td>
                                <td width="25%" style="background: #f8fafc; border: 1px solid #e2e8f0; border-top: 4px solid #0284c7; border-radius: 8px; padding: 14px; text-align: center;">
                                    <div style="font-size: 11.5px; color: #64748b; font-weight: bold;">👥 1인당 평균</div>
                                    <div style="font-size: 22px; font-weight: 900; color: #0284c7; margin: 4px 0;">{avg_hours:,}h</div>
                                    <div style="font-size: 10.5px; color: #0284c7; font-weight: bold;">{delta_avg_str}</div>
                                </td>
                                <td width="25%" style="background: #f8fafc; border: 1px solid #e2e8f0; border-top: 4px solid #10b981; border-radius: 8px; padding: 14px; text-align: center;">
                                    <div style="font-size: 11.5px; color: #64748b; font-weight: bold;">🏢 지원 고객사</div>
                                    <div style="font-size: 22px; font-weight: 900; color: #10b981; margin: 4px 0;">{tot_clients}개사</div>
                                    <div style="font-size: 10.5px; color: #10b981; font-weight: bold;">{delta_clients_str}</div>
                                </td>
                                <td width="25%" style="background: #f8fafc; border: 1px solid #e2e8f0; border-top: 4px solid #f59e0b; border-radius: 8px; padding: 14px; text-align: center;">
                                    <div style="font-size: 11.5px; color: #64748b; font-weight: bold;">🎯 예측 준수율</div>
                                    <div style="font-size: 22px; font-weight: 900; color: #f59e0b; margin: 4px 0;">{on_time_rate}%</div>
                                    <div style="font-size: 10.5px; color: #64748b;">(초과 {overdue_cnt}건)</div>
                                </td>
                            </tr>
                        </table>

                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 10px; display: flex; justify-content: space-between;">
                            <span>📝 2. AI 주간 운영 인사이트 브리핑</span>
                            <span style="font-size: 11px; color: #0284c7; font-weight: bold;">[{briefing_source}]</span>
                        </div>
                        <div style="background: #f8fafc; border: 1.5px solid #005f8a; border-left: 5px solid #005073; border-radius: 8px; padding: 14px 18px; margin-bottom: 24px; font-size: 13px; line-height: 1.7; color: #1e293b;">
                            <div style="margin-bottom: 8px;">📌 <b>핵심 변화 & 집중 요인</b>: {ai_briefing.get('overview', '')}</div>
                            <div style="margin-bottom: 8px;">⚠️ <b>현장 리스크 & 지연 진단</b>: {ai_briefing.get('risks', '')}</div>
                            <div>💡 <b>차기 운영 전략 & 액션 플랜</b>: {ai_briefing.get('recommendations', '')}</div>
                        </div>

                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 10px;">⚖️ 3. 법정 근로시간 거버넌스 진단</div>
                        <table width="100%" cellpadding="0" cellspacing="8" border="0" style="margin-bottom: 24px;">
                            <tr>
                                <td width="33.3%" style="background: #ffffff; border: 1px solid #fca5a5; border-left: 4px solid #dc2626; border-radius: 6px; padding: 10px 12px;">
                                    <div style="font-size: 11px; font-weight: bold; color: #64748b;">🚨 주 52h 초과 위험군</div>
                                    <div style="font-size: 18px; font-weight: 900; color: #dc2626; margin: 2px 0;">{len(danger_names)}명</div>
                                    <div style="font-size: 11px; color: #dc2626; font-weight: 600;">{', '.join(danger_str_list) if danger_str_list else '초과자 없음'}</div>
                                </td>
                                <td width="33.3%" style="background: #ffffff; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; padding: 10px 12px;">
                                    <div style="font-size: 11px; font-weight: bold; color: #64748b;">⚠️ 주 40~52h 관리 주의군</div>
                                    <div style="font-size: 18px; font-weight: 900; color: #d97706; margin: 2px 0;">{len(caution_names)}명</div>
                                    <div style="font-size: 11px; color: #d97706; font-weight: 600;">{', '.join(caution_str_list) if caution_str_list else '주의자 없음'}</div>
                                </td>
                                <td width="33.3%" style="background: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid #16a34a; border-radius: 6px; padding: 10px 12px;">
                                    <div style="font-size: 11px; font-weight: bold; color: #64748b;">🟢 정상 준수군 (40h 이하)</div>
                                    <div style="font-size: 18px; font-weight: 900; color: #16a34a; margin: 2px 0;">{len(safe_names)}명</div>
                                    <div style="font-size: 11px; color: #16a34a; font-weight: 600;">{', '.join(safe_str_list) if safe_str_list else '해당 없음'}</div>
                                </td>
                            </tr>
                        </table>

                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 8px;">🏢 4. 주요 고객사 공수 투입 Top 5</div>
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; margin-bottom: 24px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background-color: #f1f5f9; color: #334155; font-size: 12px; font-weight: bold; border-bottom: 1.5px solid #cbd5e1;">
                                    <th style="padding: 8px 12px; text-align: center;">순위</th>
                                    <th style="padding: 8px 12px; text-align: left;">고객사명</th>
                                    <th style="padding: 8px 12px; text-align: right;">투입 공수</th>
                                    <th style="padding: 8px 12px; text-align: right;">비중</th>
                                    <th style="padding: 8px 12px; text-align: left;">주요 지원 작업</th>
                                </tr>
                            </thead>
                            <tbody>
                                {client_rows_html if client_rows_html else '<tr><td colspan="5" style="text-align: center; padding: 15px; color: #94a3b8;">데이터 없음</td></tr>'}
                            </tbody>
                        </table>

                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 8px;">👥 5. 최다 공수 투입 핵심 엔지니어 Top 5</div>
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; margin-bottom: 16px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background-color: #f1f5f9; color: #334155; font-size: 12px; font-weight: bold; border-bottom: 1.5px solid #cbd5e1;">
                                    <th style="padding: 8px 12px; text-align: center;">순위</th>
                                    <th style="padding: 8px 12px; text-align: left;">팀원명</th>
                                    <th style="padding: 8px 12px; text-align: left;">소속팀</th>
                                    <th style="padding: 8px 12px; text-align: center;">작업 건수</th>
                                    <th style="padding: 8px 12px; text-align: right;">총 공수</th>
                                    <th style="padding: 8px 12px; text-align: left;">주요 고객사</th>
                                </tr>
                            </thead>
                            <tbody>
                                {worker_rows_html if worker_rows_html else '<tr><td colspan="6" style="text-align: center; padding: 15px; color: #94a3b8;">데이터 없음</td></tr>'}
                            </tbody>
                        </table>
                    </td>
                </tr>
                <tr>
                    <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 30px; text-align: center; color: #94a3b8; font-size: 12px; line-height: 1.6;">
                        본 메일은 기술본부 현장 업무 관제 시스템에서 매주 월요일 오전 8시에 자동 발송되는 주간 정기 브리핑입니다.<br>
                        상세 작업 내역은 첨부된 엑셀 파일(<code>주간_작업실적_요약.xlsx</code>) 또는 웹 대시보드에서 확인하실 수 있습니다.
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_df = df_active[["worker_name", "worker_team", "client_name", "start_time", "end_time", "actual_hours", "task_description", "is_night_work", "is_weekend_work"]].copy()
            # 타임존 제거 및 가독성 높은 일시 포맷팅
            export_df["start_time"] = pd.to_datetime(export_df["start_time"]).dt.strftime("%Y-%m-%d %H:%M")
            export_df["end_time"] = pd.to_datetime(export_df["end_time"]).dt.strftime("%Y-%m-%d %H:%M")
            export_df["is_night_work"] = export_df["is_night_work"].apply(lambda x: "Y" if x else "N")
            export_df["is_weekend_work"] = export_df["is_weekend_work"].apply(lambda x: "Y" if x else "N")
            export_df.columns = ["엔지니어", "소속팀", "고객사", "시작일시", "종료일시", "투입공수(h)", "작업내용", "야간여부", "주말여부"]
            export_df.to_excel(writer, index=False, sheet_name="주간_상세작업로그")

            if not worker_agg.empty:
                w_summary_rows = []
                for w_name, w_h in worker_agg.items():
                    sub = df_active[df_active["worker_name"] == w_name]
                    w_summary_rows.append({
                        "엔지니어": w_name,
                        "소속팀": sub["worker_team"].iloc[0] if "worker_team" in sub.columns else "",
                        "총 투입공수(h)": w_h,
                        "작업 건수": len(sub),
                        "야간 작업(건)": int(sub["is_night_work"].sum()) if "is_night_work" in sub.columns else 0,
                        "주말 작업(건)": int(sub["is_weekend_work"].sum()) if "is_weekend_work" in sub.columns else 0
                    })
                pd.DataFrame(w_summary_rows).to_excel(writer, index=False, sheet_name="엔지니어별_요약")

        excel_bytes = excel_buffer.getvalue()

        return subject, html_content, excel_bytes
