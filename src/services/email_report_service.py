import io
import re
from datetime import datetime, timedelta, timezone
import pandas as pd
from typing import Dict, Any, Tuple, Optional, List

from ..database.supabase_client import DatabaseManager
from ..services.team_service import TeamService, UNASSIGNED_TEAM
from ..services.client_normalizer import normalize_client_name
from ..services.ai_briefing_service import FactExtractor, AIBriefingService

KST = timezone(timedelta(hours=9))

class EmailReportService:
    @staticmethod
    def generate_weekly_report(
        target_week_label: Optional[str] = None,
        selected_team: str = "전체",
        df_active_override: Optional[pd.DataFrame] = None,
        prev_df_override: Optional[pd.DataFrame] = None,
        ai_briefing_override: Optional[Dict[str, Any]] = None,
        current_period_label_override: Optional[str] = None,
        available_weeks_override: Optional[List[str]] = None,
        df_scope_override: Optional[pd.DataFrame] = None,
        team_mappings_override: Optional[dict] = None
    ) -> Tuple[str, str, bytes]:
        """
        대시보드의 '📊 Summary' 페이지와 100% 동일한 내용의
        Executive Summary 반응형 HTML 리포트 및 분석 엑셀 파일을 생성합니다.
        """
        def is_same_team(t1, t2):
            return str(t1).replace(" ", "").strip() == str(t2).replace(" ", "").strip()

        # 팀 매핑 준비
        team_mappings = team_mappings_override if team_mappings_override is not None else TeamService.get_team_mappings()
        team_members_dict = TeamService.get_team_members_dict() if hasattr(TeamService, "get_team_members_dict") else {}

        # ----------------------------------------------------
        # 1. 데이터 소스 및 필터링 결정 (화면 전달 데이터 vs DB 직접 로드)
        # ----------------------------------------------------
        if df_active_override is not None and not df_active_override.empty:
            df_active = df_active_override.copy()
            prev_df = prev_df_override.copy() if prev_df_override is not None else pd.DataFrame()
            current_period_label = current_period_label_override or f"{selected_team} - 작업 실적 Summary"
            available_weeks = available_weeks_override if available_weeks_override is not None else []
            df_scope = df_scope_override.copy() if df_scope_override is not None else df_active.copy()
            is_weekly_view = "주차" in current_period_label and "월간 전체" not in current_period_label
        else:
            db = DatabaseManager()
            df_raw = db.fetch_all_work_logs()
            if df_raw.empty:
                return "📊 [Summary 보고서] 데이터 없음", "<p>조회된 업무 내역이 없습니다.</p>", b""

            df = df_raw.copy()
            df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
            df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")

            if "client_name" in df.columns:
                df["client_name"] = df["client_name"].apply(normalize_client_name)

            df["worker_team"] = df["worker_name"].map(team_mappings).fillna(df.get("worker_team", "")).fillna(UNASSIGNED_TEAM)

            # 멀티데이 원본 중복 배제
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
            raw_weeks = [w for w in df["week_label"].dropna().unique() if str(w).strip()]
            try:
                available_weeks = sorted(raw_weeks, key=lambda x: int(''.join(filter(str.isdigit, str(x)))) if any(c.isdigit() for c in str(x)) else str(x))
            except Exception:
                available_weeks = sorted(raw_weeks)

            df_scope = df.copy()
            clean_target = (target_week_label or "").replace("📌 ", "").strip()

            if clean_target in ["📅 월간 전체 종합", "월간 전체 종합", "월간 전체"] or not available_weeks:
                # 월간 전체 종합
                df_active = df[df["week_label"].isin(available_weeks)].copy() if available_weeks else df.copy()
                if "msg_hash" in df_active.columns:
                    df_active = df_active.drop_duplicates(subset=["msg_hash"])
                if selected_team not in ["전체", "전체 팀"] and not df_active.empty:
                    df_active = df_active[df_active["worker_team"].apply(lambda t: is_same_team(t, selected_team))]

                current_period_label = f"{selected_team} - 월간 전체"
                is_weekly_view = False

                # 전월(MoM) 비교 데이터
                prev_df = pd.DataFrame()
                if "start_time" in df_active.columns and pd.notna(df_active["start_time"].min()) and pd.notna(df_active["start_time"].max()):
                    cur_min_dt = df_active["start_time"].min()
                    cur_max_dt = df_active["start_time"].max()
                    delta_days = max(1, (cur_max_dt.date() - cur_min_dt.date()).days + 1)
                    prev_start = cur_min_dt - pd.Timedelta(days=delta_days)
                    prev_end = cur_min_dt - pd.Timedelta(seconds=1)
                    raw_dt = pd.to_datetime(df["start_time"], errors="coerce")
                    prev_df = df[(raw_dt >= prev_start) & (raw_dt <= prev_end)].copy()
                    if selected_team not in ["전체", "전체 팀"] and not prev_df.empty:
                        prev_df = prev_df[prev_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
            else:
                # 특정 주차 (기본값: 마지막 주차)
                target_week = clean_target if clean_target in available_weeks else available_weeks[-1]
                df_active = df[df["week_label"] == target_week].copy()
                if selected_team not in ["전체", "전체 팀"] and not df_active.empty:
                    df_active = df_active[df_active["worker_team"].apply(lambda t: is_same_team(t, selected_team))]

                current_period_label = f"{selected_team} - {target_week}"
                is_weekly_view = True

                # 전주(WoW) 비교 데이터
                cur_w_idx = available_weeks.index(target_week) if target_week in available_weeks else -1
                prev_df = pd.DataFrame()
                if cur_w_idx > 0:
                    prev_week_label = available_weeks[cur_w_idx - 1]
                    prev_df = df[df["week_label"] == prev_week_label].copy()
                    if selected_team not in ["전체", "전체 팀"] and not prev_df.empty:
                        prev_df = prev_df[prev_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
                else:
                    cur_min_dt = df_active["start_time"].min() if not df_active.empty else None
                    if cur_min_dt is not None:
                        cur_monday = cur_min_dt - pd.Timedelta(days=cur_min_dt.weekday())
                        cur_monday_start = cur_monday.replace(hour=0, minute=0, second=0, microsecond=0)
                        prev_monday_start = cur_monday_start - pd.Timedelta(days=7)
                        prev_sunday_end = cur_monday_start - pd.Timedelta(seconds=1)
                        raw_dt = pd.to_datetime(df["start_time"], errors="coerce")
                        prev_df = df[(raw_dt >= prev_monday_start) & (raw_dt <= prev_sunday_end)].copy()
                        if selected_team not in ["전체", "전체 팀"] and not prev_df.empty:
                            prev_df = prev_df[prev_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]

        # 직급(worker_title) 보강
        if "worker_title" not in df_active.columns:
            def get_title(name):
                info = team_members_dict.get(name, {})
                return info.get("job_title", "") if isinstance(info, dict) else ""
            df_active["worker_title"] = df_active["worker_name"].apply(get_title)

        # ----------------------------------------------------
        # 2. 🏛️ 핵심 성과 지표 산출 (5초 펄스 카드)
        # ----------------------------------------------------
        tot_hours = round(df_active["actual_hours"].sum(), 1) if not df_active.empty else 0.0
        tot_cnt = len(df_active)
        tot_workers = df_active["worker_name"].nunique() if not df_active.empty else 0
        tot_clients = df_active["client_name"].nunique() if not df_active.empty else 0
        avg_hours_per_worker = round(tot_hours / tot_workers, 1) if tot_workers > 0 else 0.0

        est_df = df_active[df_active["estimated_hours"] > 0] if not df_active.empty else pd.DataFrame()
        if not est_df.empty:
            on_time_cnt = (est_df["actual_hours"] <= est_df["estimated_hours"]).sum()
            overdue_cnt = (est_df["actual_hours"] > est_df["estimated_hours"]).sum()
            on_time_rate = round((on_time_cnt / len(est_df)) * 100, 1)
        else:
            on_time_rate = 100.0
            overdue_cnt = 0

        # 전기 비교
        prev_tot_hours = round(prev_df["actual_hours"].sum(), 1) if not prev_df.empty else None
        prev_w_cnt = prev_df["worker_name"].nunique() if not prev_df.empty else 0
        prev_avg_hours = round(prev_tot_hours / prev_w_cnt, 1) if (prev_tot_hours is not None and prev_w_cnt > 0) else None
        prev_tot_clients = prev_df["client_name"].nunique() if not prev_df.empty else None

        def get_delta_badge(cur_val, prev_val, is_positive_good=True):
            period_type = "전주" if is_weekly_view else "전월"
            if prev_val is None or prev_val == 0 or pd.isna(prev_val):
                return "<span style='color:#94a3b8; font-size:11px; font-weight:600;'>전기 비교불가</span>"
            diff = cur_val - prev_val
            pct = (diff / prev_val) * 100
            if diff > 0:
                color = "#0284c7" if is_positive_good else "#dc2626"
                return f"<span style='color:{color}; font-size:11px; font-weight:bold;'>▲ +{diff:.1f} (+{pct:.1f}% vs {period_type})</span>"
            elif diff < 0:
                color = "#16a34a" if is_positive_good else "#16a34a"
                return f"<span style='color:{color}; font-size:11px; font-weight:bold;'>▼ {diff:.1f} ({pct:.1f}% vs {period_type})</span>"
            else:
                return f"<span style='color:#94a3b8; font-size:11px; font-weight:600;'>- 0.0% ({period_type} 동일)</span>"

        d_hours_badge = get_delta_badge(tot_hours, prev_tot_hours, is_positive_good=True)
        d_avg_badge = get_delta_badge(avg_hours_per_worker, prev_avg_hours, is_positive_good=True)
        d_clients_badge = get_delta_badge(tot_clients, prev_tot_clients, is_positive_good=True)

        # ----------------------------------------------------
        # 3. 📝 AI 경영 브리핑
        # ----------------------------------------------------
        if ai_briefing_override:
            ai_briefing = ai_briefing_override
        else:
            facts = FactExtractor.extract_facts(df_active, prev_df, selected_team, current_period_label)
            ai_briefing = AIBriefingService.generate_briefing(facts, force_refresh=True)

        briefing_source = ai_briefing.get("source", "📊 다차원 팩트 분석")
        is_gemini = "Gemini" in briefing_source
        ai_badge_text = "✨ Gemini AI 심층 컨설팅" if is_gemini else "📊 팩트 기반 규칙 브리핑"

        overview_text = AIBriefingService.clean_briefing_text(ai_briefing.get('overview', '집계 데이터가 충분하지 않습니다.'))
        risks_text = AIBriefingService.clean_briefing_text(ai_briefing.get('risks', '특이 리스크 요인이 감지되지 않았습니다.'))
        recomms_text = AIBriefingService.clean_briefing_text(ai_briefing.get('recommendations', '기존 운영 전략을 지속 유지하십시오.'))

        # ----------------------------------------------------
        # 4. 📅 주차별 핵심 실적 종합 비교표 (Weekly Breakdown Matrix)
        # ----------------------------------------------------
        weekly_matrix_html = ""
        weekly_matrix_rows = []
        if available_weeks and (len(available_weeks) > 1 or not is_weekly_view):
            for w_label in available_weeks:
                sub_w = df_scope[df_scope["week_label"] == w_label]
                if selected_team not in ["전체", "전체 팀"] and not sub_w.empty:
                    sub_w = sub_w[sub_w["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
                if sub_w.empty:
                    continue
                w_hours = round(sub_w["actual_hours"].sum(), 1)
                w_workers = sub_w["worker_name"].nunique()
                w_cnt = len(sub_w)
                w_avg = round(w_hours / w_workers, 1) if w_workers > 0 else 0.0
                w_night = int(sub_w["is_night_work"].sum()) if "is_night_work" in sub_w.columns else 0
                w_wknd = int(sub_w["is_weekend_work"].sum()) if "is_weekend_work" in sub_w.columns else 0

                w_top_c = sub_w.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(2)
                w_top_c_str = ", ".join([f"{cn}({round(ch,1)}h)" for cn, ch in w_top_c.items()]) if not w_top_c.empty else "-"

                # 주 52h 초과 시 교육 제외
                sub_w_work = sub_w[~sub_w["log_type"].fillna("").astype(str).str.contains("교육")] if "log_type" in sub_w.columns else sub_w
                w_agg = sub_w_work.groupby("worker_name")["actual_hours"].sum()
                w_danger = int((w_agg > 52).sum())
                w_status = f"<span style='color:#dc2626; font-weight:bold;'>🚨 52h 초과({w_danger}명)</span>" if w_danger > 0 else "<span style='color:#16a34a; font-weight:bold;'>🟢 안정</span>"

                weekly_matrix_rows.append({
                    "주차": w_label,
                    "투입인원": w_workers,
                    "작업건수": w_cnt,
                    "총공수": w_hours,
                    "평균공수": w_avg,
                    "주요고객사": w_top_c_str,
                    "야간건수": w_night,
                    "주말건수": w_wknd,
                    "건전성태그": "52h 초과" if w_danger > 0 else "안정"
                })

                weekly_matrix_html += f"""
                <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12.5px;">
                    <td style="padding: 8px 10px; font-weight: bold; color: #002d42;">{w_label}</td>
                    <td style="padding: 8px 10px; text-align: center; color: #334155;">{w_workers}명</td>
                    <td style="padding: 8px 10px; text-align: center; color: #334155;">{w_cnt:,}건</td>
                    <td style="padding: 8px 10px; text-align: right; color: #005073; font-weight: bold;">{w_hours:,}h</td>
                    <td style="padding: 8px 10px; text-align: right; color: #0284c7; font-weight: bold;">{w_avg}h</td>
                    <td style="padding: 8px 10px; color: #475569; font-size: 12px;">{w_top_c_str}</td>
                    <td style="padding: 8px 10px; text-align: center; color: #475569;">{w_night}건</td>
                    <td style="padding: 8px 10px; text-align: center; color: #475569;">{w_wknd}건</td>
                    <td style="padding: 8px 10px; text-align: center;">{w_status}</td>
                </tr>
                """

        # ----------------------------------------------------
        # 5. ⚖️ 인력 운영 건전성 & 법정 근로시간 거버넌스
        # ----------------------------------------------------
        danger_names, caution_names, safe_names = [], [], []
        danger_detail_map = {}
        caution_detail_map = {}

        def format_week_short(w_lbl: str) -> str:
            if not w_lbl:
                return ""
            base = str(w_lbl).split(" (")[0].strip()
            parts = base.split(" ")
            if len(parts) >= 2 and "-" in parts[0]:
                try:
                    _, month = parts[0].split("-")
                    return f"{int(month)}월 {parts[1]}"
                except Exception:
                    return base
            return base

        worker_hours = df_active.groupby("worker_name")["actual_hours"].sum().to_dict() if ("worker_name" in df_active.columns and not df_active.empty) else {}
        if not df_active.empty and "worker_name" in df_active.columns:
            all_active_workers = list(df_active["worker_name"].dropna().unique())
            if "week_label" in df_active.columns:
                # [교육] 제외하고 근로시간 산정
                df_active_work = df_active[~df_active["log_type"].fillna("").astype(str).str.contains("교육")] if "log_type" in df_active.columns else df_active
                wk_agg = df_active_work.groupby(["worker_name", "week_label"])["actual_hours"].sum().reset_index()
                danger_rows = wk_agg[wk_agg["actual_hours"] > 52]
                caution_rows = wk_agg[(wk_agg["actual_hours"] > 40) & (wk_agg["actual_hours"] <= 52)]

                danger_workers = danger_rows["worker_name"].unique()
                caution_workers = caution_rows["worker_name"].unique()

                def extract_week_sort_key(w_lbl: str):
                    nums = [int(n) for n in re.findall(r'\d+', str(w_lbl))]
                    return nums if nums else [9999]

                def get_earliest_week_key(w, sub_df):
                    w_sub = sub_df[sub_df["worker_name"] == w]
                    if not w_sub.empty:
                        keys = [extract_week_sort_key(wl) for wl in w_sub["week_label"]]
                        return min(keys)
                    return [9999]

                danger_names = sorted(
                    list(danger_workers),
                    key=lambda w: (get_earliest_week_key(w, danger_rows), -worker_hours.get(w, 0.0))
                )
                caution_names = sorted(
                    [w for w in caution_workers if w not in danger_names],
                    key=lambda w: (get_earliest_week_key(w, caution_rows), -worker_hours.get(w, 0.0))
                )

                show_week_info = (not is_weekly_view) or (df_active["week_label"].nunique() > 1)
                for w in danger_names:
                    sub_d = danger_rows[danger_rows["worker_name"] == w].copy()
                    sub_d["_w_sort"] = sub_d["week_label"].apply(extract_week_sort_key)
                    sub_d = sub_d.sort_values(by="_w_sort", ascending=True)
                    if show_week_info:
                        wk_infos = [f"{format_week_short(r['week_label'])}: {r['actual_hours']:.1f}h" for _, r in sub_d.iterrows()]
                        danger_detail_map[w] = f"{w}({', '.join(wk_infos)})"
                    else:
                        danger_detail_map[w] = f"{w}({worker_hours.get(w, 0.0):.1f}h)"

                for w in caution_names:
                    sub_c = caution_rows[caution_rows["worker_name"] == w].copy()
                    sub_c["_w_sort"] = sub_c["week_label"].apply(extract_week_sort_key)
                    sub_c = sub_c.sort_values(by="_w_sort", ascending=True)
                    if show_week_info:
                        wk_infos = [f"{format_week_short(r['week_label'])}: {r['actual_hours']:.1f}h" for _, r in sub_c.iterrows()]
                        caution_detail_map[w] = f"{w}({', '.join(wk_infos)})"
                    else:
                        caution_detail_map[w] = f"{w}({worker_hours.get(w, 0.0):.1f}h)"

            safe_names = sorted([w for w in all_active_workers if w not in danger_names and w not in caution_names], key=lambda w: worker_hours.get(w, 0.0), reverse=True)

        danger_cnt = len(danger_names)
        caution_cnt = len(caution_names)
        safe_cnt = len(safe_names)

        danger_str_list = [danger_detail_map.get(w, f"{w}({worker_hours.get(w, 0.0):.1f}h)") for w in danger_names]
        caution_str_list = [caution_detail_map.get(w, f"{w}({worker_hours.get(w, 0.0):.1f}h)") for w in caution_names]
        safe_str_list = [f"{w}({worker_hours.get(w, 0.0):.1f}h)" for w in safe_names]

        danger_text = "<br>".join(danger_str_list) if danger_str_list else "초과 인원 없음 (안전)"
        caution_text = "<br>".join(caution_str_list) if caution_str_list else "주의 대상자 없음 (안전)"
        safe_text = ", ".join(safe_str_list) if safe_str_list else "해당 인원 없음"

        # ----------------------------------------------------
        # 6. 🏢 전체 고객사별 공수 투입 및 파레토 분석
        # ----------------------------------------------------
        client_agg = df_active.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False) if not df_active.empty else pd.Series()
        all_clients = client_agg.reset_index()
        all_clients.columns = ["client_name", "actual_hours"]
        all_clients["cum_pct"] = (all_clients["actual_hours"].cumsum() / tot_hours) * 100 if tot_hours > 0 else 0.0

        # 파레토 80% 인덱스 계산
        cum_80_idx = len(all_clients)
        for idx, pct in enumerate(all_clients["cum_pct"]):
            if pct >= 80.0:
                cum_80_idx = idx + 1
                break

        if cum_80_idx <= 3:
            top_pareto_names = ", ".join(all_clients.iloc[:cum_80_idx]["client_name"].tolist())
        else:
            top_3_names = ", ".join(all_clients.iloc[:3]["client_name"].tolist())
            top_pareto_names = f"{top_3_names} 외 {cum_80_idx - 3}개사"

        top_pareto_pct = all_clients.iloc[cum_80_idx - 1]["cum_pct"] if not all_clients.empty else 0.0

        # 고객사 집중도 배너 HTML
        pareto_banner_html = f"""
        <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 5px solid #16a34a; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
            <div style="font-size: 12.5px; color: #14532d; font-weight: bold; line-height: 1.6;">
                💡 <b>고객사 공수 집중도 분석</b>: <b>{current_period_label}</b> 기준 지원 고객사는 총 <b>{tot_clients}개사</b>이며, 
                전체 업무 공수(<b>{tot_hours:,}시간</b>)의 <b>{top_pareto_pct:.1f}%</b>가 상위 <b>{cum_80_idx}개 고객사({top_pareto_names})</b>에 집중 투입되었습니다.
            </div>
        </div>
        """

        # 단일 고객사 30% 초과 편중 경보 배너 HTML
        over_30_clients = [(c_n, c_h, (c_h / tot_hours) * 100) for c_n, c_h in client_agg.items() if tot_hours > 0 and ((c_h / tot_hours) * 100) >= 30.0]
        warning_banner_html = ""
        if over_30_clients:
            over_30_details = ", ".join([f"<b>{cn}</b>({pct:.1f}%, {ch:,}h)" for cn, ch, pct in over_30_clients])
            warning_banner_html = f"""
            <div style="background: #fffbeb; border: 1.5px solid #fcd34d; border-left: 5px solid #f59e0b; border-radius: 8px; padding: 11px 16px; margin-bottom: 12px;">
                <div style="font-size: 12.5px; color: #b45309; font-weight: bold; line-height: 1.6;">
                    ⚠️ <b>고객사 의존도 주의 경보</b>: 단일 고객사 {over_30_details}의 비중이 전체의 <b>30% 이상</b>을 차지하여 특정 고객사 업무 편중 리스크가 감지되었습니다.
                </div>
            </div>
            """

        # 고객사 테이블 행 생성 (전체 고객사 순위별)
        client_rows_html = ""
        cum_running = 0.0
        for rank, (c_name, c_h) in enumerate(client_agg.items(), 1):
            c_share = round((c_h / tot_hours) * 100, 1) if tot_hours > 0 else 0.0
            cum_running = round(cum_running + c_share, 1)
            sub_c = df_active[df_active["client_name"] == c_name]
            c_w_cnt = sub_c["worker_name"].nunique()
            c_cnt = len(sub_c)
            tasks = ", ".join(sub_c["task_description"].dropna().unique()[:2])
            client_rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12.5px;">
                <td style="padding: 8px 10px; font-weight: bold; color: #005073; text-align: center;">{rank}위</td>
                <td style="padding: 8px 10px; font-weight: bold; color: #0f172a;">{c_name}</td>
                <td style="padding: 8px 10px; text-align: center; color: #334155;">{c_w_cnt}명</td>
                <td style="padding: 8px 10px; text-align: center; color: #334155;">{c_cnt:,}건</td>
                <td style="padding: 8px 10px; text-align: right; color: #005073; font-weight: bold;">{c_h:.1f}h</td>
                <td style="padding: 8px 10px; text-align: right; color: #0284c7; font-weight: bold;">{c_share}%</td>
                <td style="padding: 8px 10px; text-align: right; color: #ea580c; font-weight: bold;">{cum_running:.1f}%</td>
                <td style="padding: 8px 10px; color: #475569; font-size: 12px;">{tasks}</td>
            </tr>
            """

        # ----------------------------------------------------
        # 7. 👥 전체 팀원별 공수 투입 현황
        # ----------------------------------------------------
        worker_agg = df_active.groupby("worker_name")["actual_hours"].sum().sort_values(ascending=False) if not df_active.empty else pd.Series()
        worker_rows_html = ""
        for rank, (w_name, w_h) in enumerate(worker_agg.items(), 1):
            sub_w = df_active[df_active["worker_name"] == w_name]
            w_team = sub_w["worker_team"].iloc[0] if "worker_team" in sub_w.columns and pd.notna(sub_w["worker_team"].iloc[0]) else team_mappings.get(w_name, UNASSIGNED_TEAM)
            w_title = sub_w["worker_title"].iloc[0] if "worker_title" in sub_w.columns and pd.notna(sub_w["worker_title"].iloc[0]) else ""
            w_cnt = len(sub_w)
            top_c = sub_w.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(2)
            top_c_str = ", ".join([f"{cn}({round(ch,1)}h)" for cn, ch in top_c.items()]) if not top_c.empty else "-"
            worker_rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12.5px;">
                <td style="padding: 8px 10px; font-weight: bold; color: #005073; text-align: center;">{rank}위</td>
                <td style="padding: 8px 10px; font-weight: bold; color: #0f172a;">{w_name}</td>
                <td style="padding: 8px 10px; color: #64748b;">{w_team}</td>
                <td style="padding: 8px 10px; text-align: center; color: #475569;">{w_title}</td>
                <td style="padding: 8px 10px; text-align: center; color: #334155;">{w_cnt:,}건</td>
                <td style="padding: 8px 10px; text-align: right; color: #005073; font-weight: bold;">{w_h:.1f}h</td>
                <td style="padding: 8px 10px; color: #475569; font-size: 12px;">{top_c_str}</td>
            </tr>
            """

        # ----------------------------------------------------
        # 8. 📈 부서별 종합 집계표
        # ----------------------------------------------------
        all_teams_list = TeamService.get_all_teams() if hasattr(TeamService, "get_all_teams") else ["기술본부", "기술 1팀", "기술 2팀", "기술 3팀", "PI팀"]
        team_table_html = ""
        team_summary_rows = []
        for t_name in all_teams_list + [UNASSIGNED_TEAM]:
            sub_t = df_active[df_active["worker_team"].apply(lambda t: is_same_team(t, t_name))]
            if sub_t.empty:
                continue
            t_w_cnt = sub_t["worker_name"].nunique()
            t_cnt = len(sub_t)
            t_h = round(sub_t["actual_hours"].sum(), 1)
            t_avg_h = round(t_h / t_w_cnt, 1) if t_w_cnt > 0 else 0.0
            t_night = int(sub_t["is_night_work"].sum()) if "is_night_work" in sub_t.columns else 0
            t_wknd = int(sub_t["is_weekend_work"].sum()) if "is_weekend_work" in sub_t.columns else 0
            t_share = round((t_h / tot_hours) * 100, 1) if tot_hours > 0 else 0.0

            team_summary_rows.append({
                "부서/팀명": t_name,
                "투입인원": t_w_cnt,
                "총작업건수": t_cnt,
                "총공수": t_h,
                "1인평균공수": t_avg_h,
                "전체비중": t_share,
                "야간작업": t_night,
                "주말작업": t_wknd
            })

            team_table_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12.5px;">
                <td style="padding: 8px 10px; font-weight: bold; color: #002d42;">{t_name}</td>
                <td style="padding: 8px 10px; text-align: center; color: #334155;">{t_w_cnt}명</td>
                <td style="padding: 8px 10px; text-align: center; color: #334155;">{t_cnt:,}건</td>
                <td style="padding: 8px 10px; text-align: right; color: #005073; font-weight: bold;">{t_h:,}h</td>
                <td style="padding: 8px 10px; text-align: right; color: #0284c7; font-weight: bold;">{t_avg_h}h</td>
                <td style="padding: 8px 10px; text-align: right; color: #334155;">{t_share}%</td>
                <td style="padding: 8px 10px; text-align: center; color: #475569;">{t_night}건</td>
                <td style="padding: 8px 10px; text-align: center; color: #475569;">{t_wknd}건</td>
            </tr>
            """

        # 주차별 매트릭스 섹션 HTML 조립
        weekly_matrix_section = ""
        if weekly_matrix_html:
            weekly_matrix_section = f"""
            <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-top: 24px; margin-bottom: 8px;">📅 1. 주차별 핵심 실적 종합 비교표 (Weekly Matrix)</div>
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; margin-bottom: 24px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                <thead>
                    <tr style="background-color: #f1f5f9; color: #334155; font-size: 12px; font-weight: bold; border-bottom: 1.5px solid #cbd5e1;">
                        <th style="padding: 8px 10px; text-align: left;">주차</th>
                        <th style="padding: 8px 10px; text-align: center;">인원</th>
                        <th style="padding: 8px 10px; text-align: center;">건수</th>
                        <th style="padding: 8px 10px; text-align: right;">총공수</th>
                        <th style="padding: 8px 10px; text-align: right;">1인평균</th>
                        <th style="padding: 8px 10px; text-align: left;">주요 고객사 Top 2</th>
                        <th style="padding: 8px 10px; text-align: center;">야간</th>
                        <th style="padding: 8px 10px; text-align: center;">주말</th>
                        <th style="padding: 8px 10px; text-align: center;">건전성</th>
                    </tr>
                </thead>
                <tbody>
                    {weekly_matrix_html}
                </tbody>
            </table>
            """

        subject = f"📊 [경영진 보고용 Summary] {current_period_label}"

        # ----------------------------------------------------
        # 9. 최종 반응형 HTML 템플릿 조립 (대시보드 Summary와 100% 일치)
        # ----------------------------------------------------
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 16px; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Pretendard', Helvetica, Arial, sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 800px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;">
                <!-- 헤더 배너 -->
                <tr>
                    <td style="background: linear-gradient(135deg, #002d42 0%, #005073 100%); padding: 24px 30px; color: #ffffff;">
                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
                            <tr>
                                <td>
                                    <div style="font-size: 21px; font-weight: 800; letter-spacing: -0.5px;">📊 기술본부 작업 실적 Executive Summary</div>
                                    <div style="font-size: 13px; color: #bae6fd; margin-top: 6px;">📅 대상 기준: <b>{current_period_label}</b></div>
                                </td>
                                <td style="text-align: right; vertical-align: middle;">
                                    <span style="background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.3); color: #ffffff; padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: bold;">
                                        Executive Briefing
                                    </span>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- 본문 컨텐츠 -->
                <tr>
                    <td style="padding: 24px 30px;">
                        <!-- 1. 핵심 성과 지표 (5초 펄스 카드) -->
                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 10px;">🏛️ 핵심 성과 지표 (5초 펄스 진단)</div>
                        <table width="100%" cellpadding="0" cellspacing="8" border="0" style="margin-bottom: 22px;">
                            <tr>
                                <td width="25%" style="background: #ffffff; border: 1px solid #e2e8f0; border-top: 4px solid #005073; border-radius: 8px; padding: 14px 12px; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
                                    <div style="font-size: 11.5px; color: #64748b; font-weight: bold;">⏱️ 총 투입 공수</div>
                                    <div style="font-size: 22px; font-weight: 900; color: #005073; margin: 4px 0;">{tot_hours:,}h</div>
                                    <div>{d_hours_badge}</div>
                                </td>
                                <td width="25%" style="background: #ffffff; border: 1px solid #e2e8f0; border-top: 4px solid #0284c7; border-radius: 8px; padding: 14px 12px; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
                                    <div style="font-size: 11.5px; color: #64748b; font-weight: bold;">👥 1인당 평균 공수</div>
                                    <div style="font-size: 22px; font-weight: 900; color: #0284c7; margin: 4px 0;">{avg_hours_per_worker:,}h</div>
                                    <div>{d_avg_badge}</div>
                                </td>
                                <td width="25%" style="background: #ffffff; border: 1px solid #e2e8f0; border-top: 4px solid #10b981; border-radius: 8px; padding: 14px 12px; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
                                    <div style="font-size: 11.5px; color: #64748b; font-weight: bold;">🏢 지원 고객사 수</div>
                                    <div style="font-size: 22px; font-weight: 900; color: #10b981; margin: 4px 0;">{tot_clients}개사</div>
                                    <div>{d_clients_badge}</div>
                                </td>
                                <td width="25%" style="background: #ffffff; border: 1px solid #e2e8f0; border-top: 4px solid #f59e0b; border-radius: 8px; padding: 14px 12px; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
                                    <div style="font-size: 11.5px; color: #64748b; font-weight: bold;">🎯 공수 예측 준수율</div>
                                    <div style="font-size: 22px; font-weight: 900; color: #f59e0b; margin: 4px 0;">{on_time_rate}%</div>
                                    <div style="font-size: 11px; color: #64748b; font-weight: 600;">(초과 {overdue_cnt}건)</div>
                                </td>
                            </tr>
                        </table>

                        <!-- 2. AI 경영 핵심 요약 브리핑 -->
                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 10px; display: flex; justify-content: space-between;">
                            <span>📝 경영진 핵심 요약 브리핑 & 액션 아이템</span>
                            <span style="font-size: 11px; color: #0284c7; background: #e0f2fe; padding: 2px 8px; border-radius: 4px; font-weight: bold;">[{ai_badge_text}]</span>
                        </div>
                        <div style="background: #ffffff; border: 1.5px solid #005f8a; border-left: 5px solid #005073; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; font-size: 13px; line-height: 1.8; color: #1e293b; box-shadow: 0 2px 8px rgba(0,45,66,0.05);">
                            <div style="margin-bottom: 8px; background: #f8fafc; padding: 10px 14px; border-radius: 6px; border-left: 3px solid #0284c7;">📌 <b>핵심 변화 & 집중 요인</b>: {overview_text}</div>
                            <div style="margin-bottom: 8px; background: #f8fafc; padding: 10px 14px; border-radius: 6px; border-left: 3px solid #f59e0b;">⚠️ <b>현장 리스크 & 지연 진단</b>: {risks_text}</div>
                            <div style="background: #f8fafc; padding: 10px 14px; border-radius: 6px; border-left: 3px solid #10b981;">💡 <b>차기 운영 전략 & 액션 플랜</b>: {recomms_text}</div>
                        </div>

                        <!-- 3. 주차별 종합 비교표 (있을 경우만 표출) -->
                        {weekly_matrix_section}

                        <!-- 4. 인력 운영 건전성 & 법정 근로시간 거버넌스 -->
                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 10px;">⚖️ 2. 인력 운영 건전성 & 법정 근로시간 거버넌스</div>
                        <table width="100%" cellpadding="0" cellspacing="8" border="0" style="margin-bottom: 24px;">
                            <tr>
                                <td width="33.3%" style="background: #ffffff; border: 1.5px solid {'#fca5a5' if danger_cnt > 0 else '#e2e8f0'}; border-left: 4px solid {'#dc2626' if danger_cnt > 0 else '#16a34a'}; border-radius: 6px; padding: 12px 14px; vertical-align: top;">
                                    <div style="font-size: 11px; font-weight: bold; color: #64748b;">🚨 주 52시간 초과 위험군</div>
                                    <div style="font-size: 20px; font-weight: 900; color: {'#dc2626' if danger_cnt > 0 else '#16a34a'}; margin: 2px 0;">{danger_cnt}명</div>
                                    <div style="font-size: 11px; color: {'#dc2626' if danger_cnt > 0 else '#64748b'}; font-weight: 600; line-height: 1.5;">{danger_text}</div>
                                </td>
                                <td width="33.3%" style="background: #ffffff; border: 1.5px solid {'#fde68a' if caution_cnt > 0 else '#e2e8f0'}; border-left: 4px solid {'#d97706' if caution_cnt > 0 else '#16a34a'}; border-radius: 6px; padding: 12px 14px; vertical-align: top;">
                                    <div style="font-size: 11px; font-weight: bold; color: #64748b;">⚠️ 주 40~52시간 관리 주의군</div>
                                    <div style="font-size: 20px; font-weight: 900; color: {'#d97706' if caution_cnt > 0 else '#16a34a'}; margin: 2px 0;">{caution_cnt}명</div>
                                    <div style="font-size: 11px; color: {'#d97706' if caution_cnt > 0 else '#64748b'}; font-weight: 600; line-height: 1.5;">{caution_text}</div>
                                </td>
                                <td width="33.3%" style="background: #ffffff; border: 1.5px solid #e2e8f0; border-left: 4px solid #16a34a; border-radius: 6px; padding: 12px 14px; vertical-align: top;">
                                    <div style="font-size: 11px; font-weight: bold; color: #64748b;">🟢 안정적 근로시간 준수군</div>
                                    <div style="font-size: 20px; font-weight: 900; color: #16a34a; margin: 2px 0;">{safe_cnt}명</div>
                                    <div style="font-size: 11px; color: #16a34a; font-weight: 600; line-height: 1.5;">{safe_text}</div>
                                </td>
                            </tr>
                        </table>

                        <!-- 5. 전체 고객사별 공수 투입 및 파레토 분석 -->
                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 8px;">🏢 3. 전체 고객사별 공수 투입 및 파레토 분석 (전체 {len(client_agg)}개사)</div>
                        {pareto_banner_html}
                        {warning_banner_html}
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; margin-bottom: 24px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background-color: #f1f5f9; color: #334155; font-size: 12px; font-weight: bold; border-bottom: 1.5px solid #cbd5e1;">
                                    <th style="padding: 8px 10px; text-align: center;">순위</th>
                                    <th style="padding: 8px 10px; text-align: left;">고객사명</th>
                                    <th style="padding: 8px 10px; text-align: center;">인원</th>
                                    <th style="padding: 8px 10px; text-align: center;">건수</th>
                                    <th style="padding: 8px 10px; text-align: right;">투입공수</th>
                                    <th style="padding: 8px 10px; text-align: right;">공수비중</th>
                                    <th style="padding: 8px 10px; text-align: right;">누적비중</th>
                                    <th style="padding: 8px 10px; text-align: left;">주요 지원 작업</th>
                                </tr>
                            </thead>
                            <tbody>
                                {client_rows_html if client_rows_html else '<tr><td colspan="8" style="text-align: center; padding: 15px; color: #94a3b8;">데이터 없음</td></tr>'}
                            </tbody>
                        </table>

                        <!-- 6. 전체 팀원별 공수 투입 현황 -->
                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 8px;">👥 4. 전체 팀원별 공수 투입 현황 (전체 {len(worker_agg)}명)</div>
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; margin-bottom: 24px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background-color: #f1f5f9; color: #334155; font-size: 12px; font-weight: bold; border-bottom: 1.5px solid #cbd5e1;">
                                    <th style="padding: 8px 10px; text-align: center;">순위</th>
                                    <th style="padding: 8px 10px; text-align: left;">팀원명</th>
                                    <th style="padding: 8px 10px; text-align: left;">소속팀</th>
                                    <th style="padding: 8px 10px; text-align: center;">직급</th>
                                    <th style="padding: 8px 10px; text-align: center;">건수</th>
                                    <th style="padding: 8px 10px; text-align: right;">총 공수</th>
                                    <th style="padding: 8px 10px; text-align: left;">주요 고객사</th>
                                </tr>
                            </thead>
                            <tbody>
                                {worker_rows_html if worker_rows_html else '<tr><td colspan="7" style="text-align: center; padding: 15px; color: #94a3b8;">데이터 없음</td></tr>'}
                            </tbody>
                        </table>

                        <!-- 7. 부서별 종합 집계표 -->
                        <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 8px;">📈 5. 부서별 종합 집계표</div>
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; margin-bottom: 16px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background-color: #f1f5f9; color: #334155; font-size: 12px; font-weight: bold; border-bottom: 1.5px solid #cbd5e1;">
                                    <th style="padding: 8px 10px; text-align: left;">부서/팀명</th>
                                    <th style="padding: 8px 10px; text-align: center;">투입인원</th>
                                    <th style="padding: 8px 10px; text-align: center;">총작업건수</th>
                                    <th style="padding: 8px 10px; text-align: right;">총 공수</th>
                                    <th style="padding: 8px 10px; text-align: right;">1인당평균</th>
                                    <th style="padding: 8px 10px; text-align: right;">전체비중</th>
                                    <th style="padding: 8px 10px; text-align: center;">야간작업</th>
                                    <th style="padding: 8px 10px; text-align: center;">주말작업</th>
                                </tr>
                            </thead>
                            <tbody>
                                {team_table_html if team_table_html else '<tr><td colspan="8" style="text-align: center; padding: 15px; color: #94a3b8;">데이터 없음</td></tr>'}
                            </tbody>
                        </table>
                    </td>
                </tr>

                <!-- 푸터 안내 -->
                <tr>
                    <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 30px; text-align: center; color: #94a3b8; font-size: 12px; line-height: 1.6;">
                        본 메일은 기술본부 현장 업무 관제 시스템에서 발송된 경영진 보고용 Executive Summary 리포트입니다.<br>
                        상세 작업 내역은 첨부된 엑셀 파일(<code>Executive_Summary_{datetime.now().strftime('%Y%m%d')}.xlsx</code>) 또는 웹 대시보드에서 확인하실 수 있습니다.
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        # ----------------------------------------------------
        # 10. 고도화된 다중 시트 엑셀 파일 생성
        # ----------------------------------------------------
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            # Sheet 1: 상세 작업 로그
            export_cols = [c for c in ["worker_name", "worker_team", "worker_title", "client_name", "start_time", "end_time", "actual_hours", "task_description", "is_night_work", "is_weekend_work"] if c in df_active.columns]
            export_df = df_active[export_cols].copy()
            if "start_time" in export_df.columns:
                export_df["start_time"] = pd.to_datetime(export_df["start_time"]).dt.strftime("%Y-%m-%d %H:%M")
            if "end_time" in export_df.columns:
                export_df["end_time"] = pd.to_datetime(export_df["end_time"]).dt.strftime("%Y-%m-%d %H:%M")
            if "is_night_work" in export_df.columns:
                export_df["is_night_work"] = export_df["is_night_work"].apply(lambda x: "Y" if x else "N")
            if "is_weekend_work" in export_df.columns:
                export_df["is_weekend_work"] = export_df["is_weekend_work"].apply(lambda x: "Y" if x else "N")
            col_rename = {
                "worker_name": "엔지니어", "worker_team": "소속팀", "worker_title": "직급",
                "client_name": "고객사", "start_time": "시작일시", "end_time": "종료일시",
                "actual_hours": "투입공수(h)", "task_description": "작업내용",
                "is_night_work": "야간여부", "is_weekend_work": "주말여부"
            }
            export_df = export_df.rename(columns=col_rename)
            export_df.to_excel(writer, index=False, sheet_name="상세_작업로그")

            # Sheet 2: 고객사별 집계
            if not client_agg.empty:
                c_rows = []
                c_cum = 0.0
                for rank, (c_name, c_h) in enumerate(client_agg.items(), 1):
                    sub_c = df_active[df_active["client_name"] == c_name]
                    share = round((c_h / tot_hours) * 100, 1) if tot_hours > 0 else 0.0
                    c_cum = round(c_cum + share, 1)
                    c_rows.append({
                        "순위": f"{rank}위",
                        "고객사명": c_name,
                        "투입 인원": sub_c["worker_name"].nunique(),
                        "작업 건수": len(sub_c),
                        "총 투입공수(h)": round(c_h, 1),
                        "공수 비중(%)": share,
                        "누적 점유율(%)": c_cum
                    })
                pd.DataFrame(c_rows).to_excel(writer, index=False, sheet_name="고객사별_집계")

            # Sheet 3: 팀원별 집계
            if not worker_agg.empty:
                w_rows = []
                for rank, (w_name, w_h) in enumerate(worker_agg.items(), 1):
                    sub_w = df_active[df_active["worker_name"] == w_name]
                    w_team = sub_w["worker_team"].iloc[0] if "worker_team" in sub_w.columns and pd.notna(sub_w["worker_team"].iloc[0]) else team_mappings.get(w_name, UNASSIGNED_TEAM)
                    w_title = sub_w["worker_title"].iloc[0] if "worker_title" in sub_w.columns and pd.notna(sub_w["worker_title"].iloc[0]) else ""
                    top_c = sub_w.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(2)
                    top_c_str = ", ".join([f"{cn}({round(ch,1)}h)" for cn, ch in top_c.items()]) if not top_c.empty else "-"
                    w_rows.append({
                        "순위": f"{rank}위",
                        "팀원명": w_name,
                        "소속팀": w_team,
                        "직급": w_title,
                        "작업 건수": len(sub_w),
                        "총 투입공수(h)": round(w_h, 1),
                        "야간 작업(건)": int(sub_w["is_night_work"].sum()) if "is_night_work" in sub_w.columns else 0,
                        "주말 작업(건)": int(sub_w["is_weekend_work"].sum()) if "is_weekend_work" in sub_w.columns else 0,
                        "주요 지원 고객사": top_c_str
                    })
                pd.DataFrame(w_rows).to_excel(writer, index=False, sheet_name="팀원별_집계")

            # Sheet 4: 부서별 집계
            if team_summary_rows:
                pd.DataFrame(team_summary_rows).to_excel(writer, index=False, sheet_name="부서별_집계")

            # Sheet 5: 주차별 집계 (복수 주차일 때)
            if weekly_matrix_rows:
                pd.DataFrame(weekly_matrix_rows).to_excel(writer, index=False, sheet_name="주차별_집계")

        excel_bytes = excel_buffer.getvalue()

        return subject, html_content, excel_bytes
