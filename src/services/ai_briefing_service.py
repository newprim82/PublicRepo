import os
import json
import urllib.request
import urllib.error
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import streamlit as st
except ImportError:
    st = None


class FactExtractor:
    """선택된 기간의 실제 작업 데이터로부터 다차원 이상치 및 통계적 팩트를 추출하는 분석 엔진"""

    @staticmethod
    def extract_facts(df_active: pd.DataFrame, prev_df: pd.DataFrame, selected_team: str, period_label: str) -> Dict[str, Any]:
        facts: Dict[str, Any] = {
            "period_label": period_label,
            "selected_team": selected_team,
            "total_hours": 0.0,
            "total_workers": 0,
            "total_tasks": 0,
            "total_clients": 0,
            "avg_hours_per_worker": 0.0,
            "mom_wow_change_rate": None,
            "diff_hours": 0.0,
            "top_clients": [],
            "surging_clients": [],
            "overrun_tasks": [],
            "workload_concentration": {},
            "night_weekend_causes": [],
            "top3_share": 0.0
        }

        if df_active.empty:
            return facts

        tot_hours = round(float(df_active["actual_hours"].sum()), 1)
        tot_workers = int(df_active["worker_name"].nunique())
        tot_tasks = int(len(df_active))
        tot_clients = int(df_active["client_name"].nunique())
        avg_hours = round(tot_hours / tot_workers, 1) if tot_workers > 0 else 0.0

        facts["total_hours"] = tot_hours
        facts["total_workers"] = tot_workers
        facts["total_tasks"] = tot_tasks
        facts["total_clients"] = tot_clients
        facts["avg_hours_per_worker"] = avg_hours

        # 1. 전주/전월(전기) 대비 증감 분석
        if prev_df is not None and not prev_df.empty:
            prev_hours = round(float(prev_df["actual_hours"].sum()), 1)
            diff_hours = round(tot_hours - prev_hours, 1)
            facts["diff_hours"] = diff_hours
            if prev_hours > 0:
                change_pct = round((diff_hours / prev_hours) * 100, 1)
                facts["mom_wow_change_rate"] = change_pct

            # 2. 공수 급증 고객사 추적 (전기 대비 절대 증가량 Top 2)
            cur_client_agg = df_active.groupby("client_name")["actual_hours"].sum()
            prev_client_agg = prev_df.groupby("client_name")["actual_hours"].sum()
            
            client_diffs = []
            for client, cur_h in cur_client_agg.items():
                prev_h = prev_client_agg.get(client, 0.0)
                diff = cur_h - prev_h
                client_diffs.append((client, diff, cur_h, prev_h))
            
            client_diffs.sort(key=lambda x: x[1], reverse=True)
            for client, diff, cur_h, prev_h in client_diffs[:3]:
                if diff > 0:
                    sample_tasks = df_active[df_active["client_name"] == client]["task_description"].dropna().unique()
                    sample_task_str = ", ".join(sample_tasks[:2])
                    facts["surging_clients"].append({
                        "client_name": client,
                        "diff_hours": round(diff, 1),
                        "current_hours": round(cur_h, 1),
                        "prev_hours": round(prev_h, 1),
                        "major_tasks": sample_task_str
                    })

        # 3. 주요 고객사 Top 3 점유율
        client_agg = df_active.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False)
        top3_hours = client_agg.head(3).sum()
        top3_share = round((top3_hours / tot_hours) * 100, 1) if tot_hours > 0 else 0.0
        facts["top_clients"] = [
            {"client": c, "hours": round(h, 1), "share": round((h / tot_hours) * 100, 1)}
            for c, h in client_agg.head(3).items()
        ]
        facts["top3_share"] = top3_share

        # 4. 예정 시간 대비 초과 소요 작업 분석 (예측 준수율 및 이상치)
        if "estimated_minutes" in df_active.columns and "actual_minutes" in df_active.columns:
            overrun_df = df_active[
                (df_active["estimated_minutes"] > 0) & 
                (df_active["actual_minutes"] > df_active["estimated_minutes"])
            ].copy()
            
            if not overrun_df.empty:
                overrun_df["overrun_mins"] = overrun_df["actual_minutes"] - overrun_df["estimated_minutes"]
                overrun_df = overrun_df.sort_values(by="overrun_mins", ascending=False)
                for _, row in overrun_df.head(3).iterrows():
                    facts["overrun_tasks"].append({
                        "worker": str(row.get("worker_name", "")),
                        "client": str(row.get("client_name", "")),
                        "task": str(row.get("task_description", ""))[:30],
                        "estimated_h": round(row.get("estimated_minutes", 0) / 60.0, 1),
                        "actual_h": round(row.get("actual_minutes", 0) / 60.0, 1),
                        "over_h": round(row["overrun_mins"] / 60.0, 1)
                    })

        # 5. 인력 편중도 분석 (상위 소수 인원의 작업 쏠림 현상)
        worker_agg = df_active.groupby("worker_name")["actual_hours"].sum().sort_values(ascending=False)
        if len(worker_agg) >= 2:
            top2_workers = list(worker_agg.head(2).index)
            top2_hours = float(worker_agg.head(2).sum())
            top2_share = round((top2_hours / tot_hours) * 100, 1) if tot_hours > 0 else 0.0
            facts["workload_concentration"] = {
                "top_workers": top2_workers,
                "top2_share": top2_share,
                "is_concentrated": top2_share >= 60.0
            }

        # 6. 야간/주말 비정규 근무 원인 특정
        abnormal_df = df_active[
            (df_active.get("is_night_work", False) == True) | 
            (df_active.get("is_weekend_work", False) == True)
        ]
        if not abnormal_df.empty:
            for client, group in abnormal_df.groupby("client_name"):
                h_sum = round(float(group["actual_hours"].sum()), 1)
                tasks = ", ".join(group["task_description"].dropna().unique()[:2])
                facts["night_weekend_causes"].append({
                    "client": client,
                    "hours": h_sum,
                    "tasks": tasks
                })

        return facts


class AIBriefingService:
    """1단계 추출 팩트를 바탕으로 LLM(Gemini) 또는 자체 동적 알고리즘을 통해 심층 브리핑을 완성하는 서비스"""

    @classmethod
    def generate_briefing(cls, facts: Dict[str, Any], force_refresh: bool = False) -> Dict[str, str]:
        cache_key = f"ai_briefing_{facts.get('period_label', '')}_{facts.get('selected_team', '')}"
        if not force_refresh and st is not None:
            try:
                if cache_key in st.session_state:
                    return st.session_state[cache_key]
            except Exception:
                pass

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key and st is not None:
            try:
                if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
                    api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
            except Exception:
                pass

        briefing = None
        if api_key:
            briefing = cls._call_gemini_api(facts, api_key)

        if not briefing:
            briefing = cls._generate_fact_based_rule_briefing(facts)

        if st is not None:
            try:
                st.session_state[cache_key] = briefing
            except Exception:
                pass

        return briefing

    @classmethod
    def _call_gemini_api(cls, facts: Dict[str, Any], api_key: str) -> Optional[Dict[str, str]]:
        """Google Gemini Flash REST API를 직접 호출하여 심층 브리핑을 생성"""
        prompt = f"""당신은 IT 인프라/엔지니어링 기술본부의 수석 운영 분석관이자 경영 컨설턴트입니다.
아래에 제공된 [정량 데이터 팩트 JSON]은 이번 기간의 실제 엔지니어 현장 지원 실적 통계입니다.

정형화된 고정 틀을 벗어나, 사람이 직접 작성한 것처럼 날카롭고 생생하며 실질적인 [경영진 주간/월간 핵심 브리핑]을 작성해주세요.
반드시 아래 JSON 형식으로만 답변해야 합니다:
{{
  "overview": "🎯 핵심 변화 & 집중 요인: (전기 대비 공수 증감 원인, 특히 어떤 고객사의 어떤 구체적 작업 때문에 공수가 급증했는지 사실에 근거해 2~3문장)",
  "risks": "⚠️ 현장 리스크 & 지연 진단: (예정 시간 대비 초과 지연된 작업 건수와 구체적 고객사/작업 내용, 인력 쏠림 현상, 야간/주말 근무 원인을 2~3문장)",
  "recommendations": "💡 차기 운영 전략 & 액션 플랜: (현장 관리자/팀장이 다음 주에 즉시 취해야 할 인력 재배치, 고객사 난이도 재산정, 피로도 관리 등 구체적 실행 지침 2~3문장)"
}}

[정량 데이터 팩트 JSON]:
{json.dumps(facts, ensure_ascii=False, indent=2)}
"""
        model_candidates = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-latest"]
        for model in model_candidates:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "response_mime_type": "application/json"
                    }
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=15) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    text_content = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(text_content)
                    parsed["source"] = "✨ Gemini AI 심층 분석"
                    return parsed
            except Exception:
                continue
        return None

    @classmethod
    def _generate_fact_based_rule_briefing(cls, facts: Dict[str, Any]) -> Dict[str, str]:
        """Gemini API가 없거나 실패했을 때 팩트 데이터를 결합하여 동적으로 생성하는 고품질 알고리즘 브리핑"""
        tot_h = facts["total_hours"]
        tot_w = facts["total_workers"]
        tot_c = facts["total_clients"]
        change_rate = facts.get("mom_wow_change_rate")
        surging = facts.get("surging_clients", [])
        
        overview_parts = [
            f"총 <b>{tot_w}명</b>의 인원이 <b>{tot_c}개 고객사</b>를 대상으로 <b>{tot_h:,.1f}시간</b>의 현장 지원을 수행했습니다."
        ]
        if change_rate is not None:
            sign = "증가(▲)" if change_rate > 0 else "감소(▼)"
            overview_parts.append(f"전기 대비 총 투입 공수는 <b>{abs(change_rate):.1f}% {sign}</b>한 수치입니다.")
        
        if surging:
            top_s = surging[0]
            overview_parts.append(
                f"특히 <b>{top_s['client_name']}</b>에 전주 대비 <b>+{top_s['diff_hours']}h</b>가 집중 투입되었으며, 주요 원인은 <i>'{top_s['major_tasks']}'</i> 지원에 따른 것입니다."
            )
        elif facts.get("top_clients"):
            top_c = facts["top_clients"][0]
            overview_parts.append(
                f"최대 지원 고객사는 <b>{top_c['client']}</b>(총 {top_c['hours']}h, 점유율 {top_c['share']}%)로 나타났습니다."
            )

        risk_parts = []
        overruns = facts.get("overrun_tasks", [])
        if overruns:
            max_o = overruns[0]
            risk_parts.append(
                f"예측 시간 대비 지연된 작업이 총 <b>{len(overruns)}건</b> 감지되었습니다. 대표적으로 <b>{max_o['client']}</b>의 <i>'{max_o['task']}'</i> 작업이 예정({max_o['estimated_h']}h) 대비 <b>+{max_o['over_h']}h 초과</b>되어 원인 점검이 필요합니다."
            )
        else:
            risk_parts.append("모든 작업이 예정 공수 범위 내에서 계획대로 안정적으로 준수되었습니다.")

        conc = facts.get("workload_concentration", {})
        if conc.get("is_concentrated"):
            workers_str = ", ".join(conc["top_workers"])
            risk_parts.append(
                f"인력 편중도 진단 결과, 상위 소수 인원(<b>{workers_str}</b>)에게 전체 업무의 <b>{conc['top2_share']}%</b>가 쏠려 있어 업무 피로도 분산이 필요합니다."
            )

        causes = facts.get("night_weekend_causes", [])
        if causes:
            c_names = [f"{c['client']}({c['hours']}h)" for c in causes[:2]]
            risk_parts.append(f"비정규(야간/주말) 근무는 주로 <b>{', '.join(c_names)}</b> 일정으로 인해 발생했습니다.")

        rec_parts = []
        top3_share = facts.get("top3_share", 0.0)
        if top3_share >= 70.0:
            rec_parts.append(
                f"상위 3개 고객사 점유율이 <b>{top3_share}%</b>로 매우 높으므로, 특정 엔지니어 단독 전담을 지양하고 <b>크로스 서포트(교차 지원 체계)</b> 편성을 권장합니다."
            )
        else:
            rec_parts.append("고객사별 투입 비중이 비교적 균형 있게 분산되어 전반적인 운영 밸런스를 유지하고 있습니다.")

        if overruns:
            rec_parts.append("소요시간 초과 빈도가 높은 작업 유형에 대해 현장 난이도 및 기준 공수를 재조정하여 다음 주 예측 정확도를 개선해야 합니다.")
        else:
            rec_parts.append("차기 주기에도 현 공수 예측 프로세스를 유지하며 긴급 장애 발생 시 백업 인력 동원 체계를 사전 점검하시기 바랍니다.")

        return {
            "overview": " ".join(overview_parts),
            "risks": " ".join(risk_parts),
            "recommendations": " ".join(rec_parts),
            "source": "📊 다차원 팩트 분석 엔진"
        }
