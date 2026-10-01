import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Dict, Any, List

try:
    from src.services.holiday_service import HolidayService
    from src.auth.auth_manager import AuthManager
except ImportError:
    from ...services.holiday_service import HolidayService
    from ...auth.auth_manager import AuthManager


def render_holiday_management_view():
    """
    📅 [법정 및 임시 공휴일 관리] 메인 뷰 (Cisco ACI 테마 표준 100% 준수)
    - 대한민국 법정 공휴일 및 대체공휴일 캘린더 조회
    - 정부 지정 임시공휴일 관리자 직접 등록/삭제
    - 근로기준법 제56조 준수 실시간 1.5배 할증 연동
    """
    st.markdown("""
    <style>
    /* 🏛️ Cisco ACI 표준 테마: 공휴일 관리 스타일 */
    .holiday-main-title {
        font-size: 21px !important;
        font-weight: 800 !important;
        color: #002d42 !important;
        letter-spacing: -0.4px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .holiday-main-desc {
        font-size: 13px !important;
        color: #475569 !important;
        margin-top: 4px;
        font-weight: 500;
        line-height: 1.5;
    }
    .holiday-kpi-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-top: 14px;
        margin-bottom: 20px;
    }
    .holiday-kpi-card {
        background: #ffffff;
        border: 1.2px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px 16px;
        box-shadow: 0 1px 3px rgba(0, 45, 66, 0.05);
        border-top: 3.5px solid #005073;
    }
    .holiday-kpi-card.top-blue { border-top-color: #0284c7; }
    .holiday-kpi-card.top-green { border-top-color: #10b981; }
    .holiday-kpi-card.top-purple { border-top-color: #8b5cf6; }
    .holiday-kpi-label {
        font-size: 12px;
        font-weight: 700;
        color: #64748b;
        margin-bottom: 4px;
    }
    .holiday-kpi-val {
        font-size: 20px;
        font-weight: 900;
        color: #002d42;
        letter-spacing: -0.5px;
    }
    .holiday-kpi-sub {
        font-size: 11.5px;
        font-weight: 600;
        color: #0284c7;
        margin-top: 3px;
    }
    .holiday-section-header {
        font-size: 15px;
        font-weight: 800;
        color: #002d42;
        padding: 8px 12px;
        background: #f8fafc;
        border: 1.2px solid #cbd5e1;
        border-left: 4.5px solid #005073;
        border-radius: 6px;
        margin-top: 20px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .holiday-info-box {
        background: #f0f9ff;
        border: 1px solid #bae6fd;
        border-left: 4px solid #0284c7;
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 14px;
        font-size: 13px;
        color: #0369a1;
        line-height: 1.5;
        font-weight: 600;
    }
    label, div[data-testid="stWidgetLabel"] p, div[data-testid="stWidgetLabel"] span {
        color: #002d42 !important;
        font-weight: 800 !important;
        font-size: 13.5px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. 상단 헤더
    st.markdown("""
    <div style="margin-bottom: 12px;">
        <div class="holiday-main-title">
            <span>📅</span>
            <span>법정 및 임시 공휴일 관리 (근로기준법 제56조)</span>
        </div>
        <div class="holiday-main-desc">
            대한민국 법정 공휴일 및 대체공휴일 캘린더 자동 연동 현황을 확인하고, 정부 지정 임시공휴일을 직접 등록·삭제 관리합니다.
            등록된 휴일 근무는 예상 청구 금액 산정 시 <b>1.5배 할증(50% 가산)</b>이 즉시 자동 적용됩니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ⚖️ 근로기준법 제56조 준수 안내 바
    st.markdown("""
    <div style="background: #f0fdf4; border: 1.2px solid #86efac; border-left: 5px solid #16a34a; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
        <div>
            <div style="font-size: 13px; font-weight: 700; color: #14532d; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <span>⚖️ <b>근로기준법 제56조 준수:</b> 일요일 및 법정/대체/임시 공휴일 근무 공수에 대해 <b>1.5배 할증 가산(50% 가산)</b>이 상시 자동 적용됩니다.</span>
            </div>
            <div style="margin-top: 5px; font-size: 12px; font-weight: 600; color: #166534; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <span>📖 관련 법령:</span>
                <a href="https://www.law.go.kr/LSW//lsLinkCommonInfo.do?lsJoLnkSeq=1025590551&chrClsCd=010202&ancYnChk=" target="_blank" rel="noopener noreferrer" style="color: #0284c7; font-weight: 800; text-decoration: underline;">[국가법령정보센터 | 조문정보]</a>
                <span style="color: #64748b; font-size: 11.5px;">(클릭 시 근로기준법 제56조 조문 새 창 열기 ↗)</span>
            </div>
        </div>
        <div>
            <div style="font-size: 12px; font-weight: 800; color: #15803d; background: #dcfce7; padding: 4px 12px; border-radius: 4px; border: 1px solid #bbf7d0; white-space: nowrap;">
                상시 자동 적용 (배율: 1.5배)
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 올해 공휴일 통계 산출
    current_year = datetime.now().year
    holidays_this_year = HolidayService.get_holidays_for_year(current_year)
    statutory_cnt = sum(1 for h in holidays_this_year if h["holiday_type"] == "법정공휴일")
    substitute_cnt = sum(1 for h in holidays_this_year if h["holiday_type"] == "대체공휴일")
    custom_holidays = HolidayService.get_custom_holidays(force_reload=True)
    custom_cnt = len(custom_holidays)

    # 4대 KPI 카드
    st.markdown(f"""
    <div class="holiday-kpi-row">
        <div class="holiday-kpi-card">
            <div class="holiday-kpi-label">🏛️ 올해 법정 공휴일 ({current_year}년)</div>
            <div class="holiday-kpi-val" style="color: #005073;">{statutory_cnt}일</div>
            <div class="holiday-kpi-sub">양력 8대 공휴일 + 음력 3대 명절</div>
        </div>
        <div class="holiday-kpi-card top-blue">
            <div class="holiday-kpi-label">🔄 법정 대체공휴일 ({current_year}년)</div>
            <div class="holiday-kpi-val" style="color: #0284c7;">{substitute_cnt}일</div>
            <div class="holiday-kpi-sub">주말 겹침 시 익영업일 자동 산출</div>
        </div>
        <div class="holiday-kpi-card top-green">
            <div class="holiday-kpi-label">⚡ 정부 지정 임시공휴일</div>
            <div class="holiday-kpi-val" style="color: #10b981;">{custom_cnt}건 등록</div>
            <div class="holiday-kpi-sub">관리자 직접 등록 (DB 영구 보존)</div>
        </div>
        <div class="holiday-kpi-card top-purple">
            <div class="holiday-kpi-label">⚖️ 근로기준법 할증 배율</div>
            <div class="holiday-kpi-val" style="color: #8b5cf6;">1.5배 (50% 가산)</div>
            <div class="holiday-kpi-sub" style="color: #8b5cf6;">휴일 1시간 이상 근무 시 자동 적용</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # =========================================================================
    # 섹션 1: ➕ 정부 지정 임시공휴일 직접 등록 및 관리 (관리자 전용)
    # =========================================================================
    st.markdown('<div class="holiday-section-header"><span>➕</span><span>정부 지정 임시공휴일 직접 추가 및 관리 (DB 영구 보존)</span></div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="holiday-info-box">
        💡 <b>임시공휴일 등록 가이드:</b> 국무회의 의결 등으로 정부에서 비정기 <b>임시공휴일</b>(예: <i>2024년 10월 1일 국군의 날 임시공휴일</i> 등)을 지정한 경우,
        아래에서 날짜와 명칭을 직접 등록하시면 시스템 재배포 없이 <b>즉시 전역에서 1.5배 할증 대상 휴일로 자동 반영</b>됩니다.
    </div>
    """, unsafe_allow_html=True)

    col_form, col_list = st.columns([5, 5])

    with col_form:
        with st.form("form_add_custom_holiday", clear_on_submit=True):
            st.markdown("##### 📝 신규 임시공휴일 등록")
            input_date = st.date_input("📅 공휴일 지정 일자", value=date.today())
            input_name = st.text_input("🏷️ 공휴일 명칭 / 사유", placeholder="예: 국군의 날 임시공휴일, 정부 지정 임시휴일")
            btn_submit = st.form_submit_button("➕ 임시공휴일 등록 (DB 즉시 반영)", use_container_width=True, type="primary")

            if btn_submit:
                if not input_name.strip():
                    st.error("공휴일 명칭 또는 사유를 입력해주세요.")
                else:
                    d_str = input_date.strftime("%Y-%m-%d")
                    current_user = AuthManager.get_current_user() or "관리자"
                    success = HolidayService.add_custom_holiday(d_str, input_name.strip(), created_by=current_user)
                    if success:
                        st.cache_data.clear()
                        st.toast(f"✅ {d_str} ({input_name.strip()}) 임시공휴일이 등록되었습니다!", icon="🎉")
                        st.rerun()
                    else:
                        st.error("임시공휴일 등록에 실패했습니다.")

    with col_list:
        st.markdown("##### 📋 현재 등록된 임시공휴일 목록")
        if not custom_holidays:
            st.info("현재 등록된 추가 임시공휴일이 없습니다.")
        else:
            for d_key in sorted(custom_holidays.keys(), reverse=True):
                h_val = custom_holidays[d_key]
                c_item1, c_item2 = st.columns([7, 3])
                with c_item1:
                    st.markdown(f"""
                    <div style="background: #ffffff; border: 1px solid #cbd5e1; border-left: 4px solid #10b981; border-radius: 6px; padding: 7px 12px; margin-bottom: 6px;">
                        <span style="font-weight: 800; color: #002d42; font-size: 13.5px;">📅 {d_key}</span>
                        <span style="color: #64748b; font-size: 12.5px; margin-left: 8px;">{h_val}</span>
                    </div>
                    """, unsafe_allow_html=True)
                with c_item2:
                    if st.button("🗑️ 삭제", key=f"btn_del_holiday_{d_key}", use_container_width=True):
                        HolidayService.delete_custom_holiday(d_key)
                        st.cache_data.clear()
                        st.toast(f"🗑️ {d_key} 공휴일이 삭제되었습니다.", icon="ℹ️")
                        st.rerun()

    # =========================================================================
    # 섹션 2: 📋 연도별 대한민국 공휴일 및 대체공휴일 전체 캘린더 (한국천문연구원 공식 기준)
    # =========================================================================
    st.markdown('<div class="holiday-section-header" style="margin-top: 30px;"><span>📋</span><span>연도별 대한민국 공휴일·대체공휴일 전체 캘린더 (한국천문연구원 공식 기준)</span></div>', unsafe_allow_html=True)

    col_y1, col_y2 = st.columns([3, 7])
    with col_y1:
        selected_year = st.selectbox(
            "조회 연도 선택",
            options=[2024, 2025, 2026, 2027, 2028, 2029, 2030],
            index=2,  # 기본 2026년
            key="sel_holiday_year"
        )

    holidays_view = HolidayService.get_holidays_for_year(selected_year)
    if not holidays_view:
        st.info(f"{selected_year}년 등록된 공휴일 정보가 없습니다.")
    else:
        df_h = pd.DataFrame(holidays_view)
        df_h = df_h.rename(columns={
            "date": "공휴일 일자",
            "day_name": "요일",
            "holiday_name": "공휴일 명칭",
            "holiday_type": "공휴일 구분",
            "is_weekend": "주말 겹침 여부"
        })
        df_h["주말 겹침 여부"] = df_h["주말 겹침 여부"].apply(lambda x: "주말(토/일)" if x else "평일")

        st.dataframe(
            df_h,
            use_container_width=True,
            height=380,
            hide_index=True
        )

        csv_h_data = df_h.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=f"📥 {selected_year}년 공휴일 캘린더 CSV 다운로드",
            data=csv_h_data,
            file_name=f"{selected_year}년_대한민국_공휴일목록_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            key="btn_dl_holiday_calendar_csv"
        )
