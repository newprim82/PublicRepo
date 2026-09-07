import streamlit as st
import streamlit.components.v1 as components

def apply_custom_styles():
    """전역 Cisco ACI Enterprise 테마 및 Pretendard 폰트 CSS 주입"""
    # 커스텀 CSS
    st.markdown("""
    <style>
        /* 🔤 토스(Toss) 표준 프리미엄 웹 폰트: Pretendard (프리텐다드) */
        @import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");

        /* 1. 사이트 전체 기본 본문 -> Pretendard (최고의 화면 가독성 & 선명도) */
        html, body, .stApp, .stApp *:not([data-testid*="Icon"]):not([data-testid*="icon"]):not(span[translate="no"]):not(svg) {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Segoe UI", sans-serif;
            letter-spacing: -0.2px;
        }

        /* 2. 모든 제목, 대형 KPI 수치 숫자, 타이틀 -> Pretendard 800 (ExtraBold) */
        h1, h2, h3, h4, h5, h6, 
        .kpi-value, 
        .kpi-value *,
        .kpi-title, 
        .main-title-text, 
        .main-title-text *,
        .sidebar-section-header,
        .filter-badge b,
        .alert-blink-badge,
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Segoe UI", sans-serif !important;
            font-weight: 800 !important;
            letter-spacing: -0.4px;
        }

        /* 🚀 Streamlit 머티리얼 아이콘 폰트 (Material Symbols / Icons) 100% 온전하게 보존 */
        span[translate="no"],
        [data-testid*="Icon"],
        [data-testid*="icon"],
        [data-testid="stExpanderToggleIcon"],
        .material-symbols-rounded,
        .material-symbols-outlined,
        .material-icons {
            font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons", sans-serif !important;
            font-weight: normal !important;
        }

        html {
            scroll-behavior: smooth;
        }
        /* 🏛️ Cisco ACI Enterprise 관제 포털 테마 (Light & Deep Cyan-Navy Hybrid) */
        html, body, [data-testid="stAppViewContainer"], .stApp {
            background-color: #f4f6f9 !important;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Pretendard, sans-serif !important;
            color: #0f172a !important;
        }

        /* 🚀 타이틀 + 기준시각 & 우측 Deploy/점세개 최적화 */
        header[data-testid="stHeader"] {
            background: transparent !important;
            height: 0px !important;
            z-index: 100 !important;
        }

        /* 🚀 좌측 사이드바 열기 버튼 (stExpandSidebarButton: >>) */
        [data-testid="stExpandSidebarButton"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            position: fixed !important;
            top: 1.15rem !important;
            left: 1.2rem !important;
            z-index: 999999 !important;
            background-color: #001e2d !important;
            color: #00b4d8 !important;
            border: 1.5px solid #00b4d8 !important;
            border-radius: 6px !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
        }
        [data-testid="stExpandSidebarButton"] svg {
            fill: #00b4d8 !important;
            color: #00b4d8 !important;
        }

        /* 🚀 좌측 사이드바 닫기 버튼 (stSidebarCollapseButton: <<) */
        [data-testid="stSidebarCollapseButton"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }
        [data-testid="stSidebarCollapseButton"] button {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            color: #00b4d8 !important;
            background: rgba(0, 180, 216, 0.12) !important;
            border: 1.5px solid #00b4d8 !important;
            border-radius: 6px !important;
        }
        [data-testid="stSidebarCollapseButton"] svg,
        [data-testid="stSidebarCollapseButton"] span {
            fill: #00b4d8 !important;
            color: #00b4d8 !important;
        }

        /* 🚀 우측 불필요한 Streamlit 툴바만 정밀 숨김 */
        [data-testid="stAppDeployButton"],
        [data-testid="stMainMenuButton"],
        [data-testid="stToolbarActions"],
        [data-testid="stToolbarActionButton"],
        .stDeployButton,
        #MainMenu {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        .block-container {
            padding-top: 1.15rem !important;
            padding-bottom: 2rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            max-width: 100% !important;
        }

        /* 🚀 상단 헤더 컴포넌트 iframe 깜빡임(화이트 플래시) 100% 원천 방지 */
        iframe[title*="components.v1.html"],
        div[data-testid="stCustomComponentV1"] iframe {
            background-color: transparent !important;
            border: none !important;
            color-scheme: dark !important;
        }
        div[data-testid="stCustomComponentV1"] {
            background: transparent !important;
        }

        /* 🔘 시스템 표준 프리미엄 버튼 기본 스타일 (메일 발송 버튼 테마로 완전 일원화) */
        div[data-testid="stButton"] > button,
        .stButton > button,
        button[kind="secondary"] {
            background-color: #004060 !important;
            background: linear-gradient(135deg, #002d42 0%, #005073 100%) !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(255, 255, 255, 0.3) !important;
            border-radius: 6px !important;
            font-size: 13.5px !important;
            font-weight: 700 !important;
            height: 38px !important;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25) !important;
            transition: all 0.2s ease !important;
        }
        div[data-testid="stButton"] > button p,
        div[data-testid="stButton"] > button span,
        .stButton > button p,
        .stButton > button span,
        button[kind="secondary"] p,
        button[kind="secondary"] span {
            color: #FFFFFF !important;
            font-weight: 700 !important;
            font-size: 13.5px !important;
            letter-spacing: -0.2px !important;
        }
        div[data-testid="stButton"] > button:hover,
        .stButton > button:hover,
        button[kind="secondary"]:hover {
            background-color: #00608a !important;
            background: linear-gradient(135deg, #004060 0%, #0284c7 100%) !important;
            border-color: #38bdf8 !important;
            color: #FFFFFF !important;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.45) !important;
            transform: translateY(-1px) !important;
        }
        div[data-testid="stButton"] > button:hover p,
        div[data-testid="stButton"] > button:hover span,
        .stButton > button:hover p,
        .stButton > button:hover span {
            color: #FFFFFF !important;
        }

        /* 📊 [과중근무 배너 전용] 프로그레스 바 타입 버튼 스타일링 */
        /* 1) 🚨 [52h 초과] 레드 프로그레스 바 */
        div[data-testid="stColumn"]:has(.danger-chip-zone) div[data-testid="stButton"] > button,
        div[data-testid="column"]:has(.danger-chip-zone) div[data-testid="stButton"] > button,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.danger-chip-zone) button,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) button[kind="primary"] {
            background: linear-gradient(90deg, #dc2626 0%, #ef4444 100%) !important;
            background-color: #dc2626 !important;
            border: 1px solid #b91c1c !important;
            border-radius: 6px !important;
            height: 30px !important;
            min-height: 30px !important;
            padding: 0 8px !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 1px 3px rgba(220, 38, 38, 0.25) !important;
            cursor: pointer !important;
            transition: all 0.15s ease-in-out !important;
        }
        div[data-testid="stColumn"]:has(.danger-chip-zone) div[data-testid="stButton"] > button:hover,
        div[data-testid="column"]:has(.danger-chip-zone) div[data-testid="stButton"] > button:hover,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) button[kind="primary"]:hover {
            background: linear-gradient(90deg, #b91c1c 0%, #dc2626 100%) !important;
            border-color: #991b1b !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 3px 8px rgba(220, 38, 38, 0.45) !important;
            transform: translateY(-1px) !important;
        }

        /* 2) ⚠️ [40h 초과] 주황색 프로그레스 바 */
        div[data-testid="stColumn"]:has(.caution-chip-zone) div[data-testid="stButton"] > button,
        div[data-testid="column"]:has(.caution-chip-zone) div[data-testid="stButton"] > button,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.caution-chip-zone) button,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) button[kind="secondary"],
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div.stButton > button:not([kind="primary"]) {
            background: linear-gradient(90deg, #ea580c 0%, #f97316 100%) !important;
            background-color: #ea580c !important;
            border: 1px solid #c2410c !important;
            border-radius: 6px !important;
            height: 30px !important;
            min-height: 30px !important;
            padding: 0 8px !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 1px 3px rgba(234, 88, 12, 0.25) !important;
            cursor: pointer !important;
            transition: all 0.15s ease-in-out !important;
        }
        div[data-testid="stColumn"]:has(.caution-chip-zone) div[data-testid="stButton"] > button:hover,
        div[data-testid="column"]:has(.caution-chip-zone) div[data-testid="stButton"] > button:hover,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.caution-chip-zone) button:hover {
            background: linear-gradient(90deg, #c2410c 0%, #ea580c 100%) !important;
            border-color: #9a3412 !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 3px 8px rgba(234, 88, 12, 0.45) !important;
            transform: translateY(-1px) !important;
        }

        /* 3) ✅ [보상 완료] 초록색 프로그레스 바 */
        div[data-testid="stColumn"]:has(.reward-chip-zone) div[data-testid="stButton"] > button,
        div[data-testid="column"]:has(.reward-chip-zone) div[data-testid="stButton"] > button,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.reward-chip-zone) button {
            background: linear-gradient(90deg, #16a34a 0%, #22c55e 100%) !important;
            background-color: #16a34a !important;
            border: 1px solid #15803d !important;
            border-radius: 6px !important;
            height: 30px !important;
            min-height: 30px !important;
            padding: 0 8px !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 1px 3px rgba(22, 163, 74, 0.25) !important;
            cursor: pointer !important;
            transition: all 0.15s ease-in-out !important;
        }
        div[data-testid="stColumn"]:has(.reward-chip-zone) div[data-testid="stButton"] > button:hover,
        div[data-testid="column"]:has(.reward-chip-zone) div[data-testid="stButton"] > button:hover,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.reward-chip-zone) button:hover {
            background: linear-gradient(90deg, #15803d 0%, #16a34a 100%) !important;
            border-color: #166534 !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 3px 8px rgba(22, 163, 74, 0.45) !important;
            transform: translateY(-1px) !important;
        }

        /* 4) 📝 프로그레스 바 내부 볼드 화이트 텍스트 + 입체 텍스트 그림자 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stButton"] > button *,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stButton"] > button p,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stButton"] > button span,
        div[data-testid="stColumn"]:has(.danger-chip-zone) div[data-testid="stButton"] > button *,
        div[data-testid="stColumn"]:has(.caution-chip-zone) div[data-testid="stButton"] > button *,
        div[data-testid="stColumn"]:has(.reward-chip-zone) div[data-testid="stButton"] > button * {
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 11.5px !important;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5) !important;
            letter-spacing: -0.3px !important;
            white-space: nowrap !important;
        }


        /* ⚠️ Streamlit 알림창 (st.warning, st.info, st.success, st.error) 고대비 가독성 보장 (흰색 글씨 원천 방지) */
        div[data-testid="stAlert"] {
            border-radius: 8px !important;
        }
        div[data-testid="stAlert"] * {
            color: #1e293b !important;
            font-weight: 600 !important;
        }
        /* warning (노란색 배경) -> 짙은 다크 브라운 텍스트 */
        div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]),
        div[data-testid="stAlert"] [data-testid="stAlertContentWarning"],
        div[data-testid="stAlert"] [data-testid="stAlertContentWarning"] *,
        div[data-testid="stAlert"] [data-testid="stAlertContentWarning"] p,
        div[data-testid="stAlert"] [data-testid="stAlertContentWarning"] span,
        div[data-testid="stAlert"] [data-testid="stAlertContentWarning"] div,
        div[data-testid="stAlert"] [data-testid="stAlertContentWarning"] strong,
        div[data-testid="stNotificationContentWarning"],
        div[data-testid="stNotificationContentWarning"] *,
        div[data-testid="stDialog"] div[data-testid="stAlert"] *,
        div[role="dialog"] div[data-testid="stAlert"] *,
        div[data-baseweb="modal"] div[data-testid="stAlert"] * {
            color: #713f12 !important;
            font-weight: 700 !important;
        }
        /* info (하늘색 배경) -> 짙은 네이비 텍스트 */
        div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]),
        div[data-testid="stAlert"] [data-testid="stAlertContentInfo"],
        div[data-testid="stAlert"] [data-testid="stAlertContentInfo"] * {
            color: #075985 !important;
            font-weight: 700 !important;
        }
        /* success (초록색 배경) -> 짙은 그린 텍스트 */
        div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]),
        div[data-testid="stAlert"] [data-testid="stAlertContentSuccess"],
        div[data-testid="stAlert"] [data-testid="stAlertContentSuccess"] * {
            color: #14532d !important;
            font-weight: 700 !important;
        }
        /* error (빨간색 배경) -> 짙은 레드 텍스트 */
        div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]),
        div[data-testid="stAlert"] [data-testid="stAlertContentError"],
        div[data-testid="stAlert"] [data-testid="stAlertContentError"] * {
            color: #7f1d1d !important;
            font-weight: 700 !important;
        }

        /* ⚠️ 노란색/연노란색/경고 배경 내 텍스트 시인성 완벽 보장 (모달 및 인라인 div 포함 흰색 글씨 원천 차단) */
        .overwork-warning-box,
        .overwork-warning-box *,
        div.overwork-warning-box *,
        div[style*="fefce8"],
        div[style*="fefce8"] *,
        div[style*="fffbeb"],
        div[style*="fffbeb"] *,
        div[style*="fef08a"],
        div[style*="fef08a"] *,
        div[style*="fef3c7"],
        div[style*="fef3c7"] *,
        div[style*="fde047"],
        div[style*="fde047"] *,
        div[style*="fff9db"],
        div[style*="fff9db"] * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            font-weight: 800 !important;
            text-shadow: none !important;
        }

        /* 🚨 연빨간색 배경 내 텍스트 고대비 보장 */
        .overwork-danger-box,
        .overwork-danger-box *,
        div.overwork-danger-box *,
        div[style*="fef2f2"],
        div[style*="fef2f2"] *,
        div[style*="fecaca"],
        div[style*="fecaca"] * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            font-weight: 800 !important;
            text-shadow: none !important;
        }


        /* 🏛️ Cisco ACI 스타일 필터 배지 및 고시인성 실시간 집계 기준 정보 패널 */
        .filter-badge {
            background-color: #e0f2fe !important;
            color: #0369a1 !important;
            padding: 9px 16px !important;
            border-radius: 8px !important;
            font-size: 13.5px !important;
            font-weight: 600 !important;
            display: inline-block !important;
            margin-bottom: 18px !important;
            border: 1px solid #bae6fd !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
        }

        .active-criteria-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px 14px;
            background: #ffffff !important;
            border: 1.5px solid #cbd5e1 !important;
            border-left: 5px solid #005073 !important;
            border-radius: 10px !important;
            padding: 10px 16px !important;
            margin-top: 4px !important;
            margin-bottom: 18px !important;
            box-shadow: 0 2px 8px rgba(0, 45, 66, 0.05), 0 1px 3px rgba(0, 0, 0, 0.03) !important;
        }
        .criteria-left {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            flex: 1;
        }
        .criteria-header {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: linear-gradient(135deg, #002d42 0%, #004d71 100%) !important;
            color: #ffffff !important;
            padding: 5px 11px !important;
            border-radius: 6px !important;
            font-weight: 800 !important;
            font-size: 12.5px !important;
            letter-spacing: -0.2px;
            white-space: nowrap;
            box-shadow: 0 1px 3px rgba(0, 45, 66, 0.2) !important;
        }
        .criteria-chips-wrapper {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }
        .criteria-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 11px;
            border-radius: 6px;
            font-size: 13px;
            white-space: nowrap;
        }
        .criteria-chip .chip-label {
            color: #64748b;
            font-size: 11.5px;
            font-weight: 600;
        }
        .criteria-chip .chip-value {
            font-weight: 800;
            font-size: 13px;
        }
        .chip-period {
            background: #eff6ff !important;
            border: 1px solid #bfdbfe !important;
        }
        .chip-period .chip-value { color: #1d4ed8 !important; }
    
        .chip-team {
            background: #f0fdf4 !important;
            border: 1px solid #bbf7d0 !important;
        }
        .chip-team .chip-value { color: #15803d !important; }
    
        .chip-worker {
            background: #faf5ff !important;
            border: 1px solid #e9d5ff !important;
        }
        .chip-worker .chip-value { color: #7e22ce !important; }

        .chip-extra {
            background: #fffbeb !important;
            border: 1px solid #fde68a !important;
        }
        .chip-extra .chip-value { color: #b45309 !important; }

        .criteria-count-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #f8fafc !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
            padding: 5px 13px !important;
            font-size: 12.5px !important;
            color: #475569 !important;
            font-weight: 700 !important;
            white-space: nowrap;
        }
        .criteria-count-badge b {
            color: #005073 !important;
            font-size: 14.5px !important;
            font-weight: 800 !important;
        }

        /* 🏛️ Cisco ACI 탭 바 완벽 카드형 배경 및 가독성 보장 */
        div[data-testid="stTabs"] [role="tablist"],
        div[data-testid="stTabs"] [data-baseweb="tab-list"],
        .stTabs [role="tablist"],
        .stTabs [data-baseweb="tab-list"] {
            display: flex !important;
            gap: 12px !important;
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            margin-bottom: 16px !important;
        }
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
        div[data-testid="stTabs"] [data-baseweb="tab-border"],
        .stTabs [data-baseweb="tab-highlight"],
        .stTabs [data-baseweb="tab-border"] {
            display: none !important;
            height: 0px !important;
            background-color: transparent !important;
        }
        div[data-testid="stTabs"] button[role="tab"],
        div[data-testid="stTabs"] button[data-baseweb="tab"],
        .stTabs button[role="tab"],
        .stTabs button[data-baseweb="tab"] {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            height: 42px !important;
            min-height: 42px !important;
            white-space: nowrap !important;
            padding: 8px 20px !important;
            border-radius: 8px !important;
            font-size: 14px !important;
            font-weight: 800 !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
        }
        /* 비선택 탭: 밝은 그레이 배경 + 선명한 다크네이비 글자 + 테두리 */
        div[data-testid="stTabs"] button[role="tab"]:not([aria-selected="true"]),
        div[data-testid="stTabs"] button[role="tab"][aria-selected="false"],
        div[data-testid="stTabs"] button[data-baseweb="tab"]:not([aria-selected="true"]),
        .stTabs button[role="tab"]:not([aria-selected="true"]) {
            background-color: #f1f5f9 !important;
            background: #f1f5f9 !important;
            border: 1.5px solid #cbd5e1 !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
        }
        div[data-testid="stTabs"] button[role="tab"]:not([aria-selected="true"]) *,
        div[data-testid="stTabs"] button[role="tab"][aria-selected="false"] *,
        div[data-testid="stTabs"] button[data-baseweb="tab"]:not([aria-selected="true"]) *,
        .stTabs button[role="tab"]:not([aria-selected="true"]) * {
            color: #002d42 !important;
            font-weight: 800 !important;
            font-size: 14px !important;
            opacity: 1 !important;
            visibility: visible !important;
        }
        div[data-testid="stTabs"] button[role="tab"]:not([aria-selected="true"]):hover,
        .stTabs button[role="tab"]:not([aria-selected="true"]):hover {
            background-color: #e2e8f0 !important;
            border-color: #94a3b8 !important;
        }
        /* 선택된 활성 탭: Cisco ACI 딥블루 배경 + 볼드 화이트 글자 */
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"],
        div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"],
        .stTabs button[role="tab"][aria-selected="true"] {
            background-color: #005073 !important;
            background: linear-gradient(135deg, #005073 0%, #003852 100%) !important;
            border: 1.5px solid #002233 !important;
            box-shadow: 0 3px 10px rgba(0, 80, 115, 0.35) !important;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] *,
        div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] *,
        .stTabs button[role="tab"][aria-selected="true"] * {
            color: #ffffff !important;
            font-weight: 900 !important;
            font-size: 14px !important;
            opacity: 1 !important;
            visibility: visible !important;
        }

        /* 🏛️ 전역 다운로드 버튼 스타일링 (선명한 화이트 볼드 텍스트) */
        div[data-testid="stDownloadButton"] button,
        [data-testid="stDownloadButton"] button,
        .stDownloadButton button {
            background: linear-gradient(135deg, #005073 0%, #003852 100%) !important;
            background-color: #005073 !important;
            color: #ffffff !important;
            border: 1px solid #002233 !important;
            border-radius: 6px !important;
            padding: 8px 18px !important;
            box-shadow: 0 2px 5px rgba(0, 80, 115, 0.3) !important;
        }
        div[data-testid="stDownloadButton"] button *,
        [data-testid="stDownloadButton"] button *,
        .stDownloadButton button * {
            color: #ffffff !important;
            font-weight: 800 !important;
            font-size: 13.5px !important;
            opacity: 1 !important;
            visibility: visible !important;
        }
        div[data-testid="stDownloadButton"] button:hover,
        [data-testid="stDownloadButton"] button:hover {
            background-color: #003852 !important;
        }
        div[data-testid="stDownloadButton"] button:hover * {
            color: #38bdf8 !important;
        }

        /* 🏛️ Cisco ACI 엔터프라이즈 화이트 KPI 카드 스타일 (완벽 중앙 정렬 & 입체감) */
        .kpi-card {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 10px !important;
            padding: 16px 14px !important;
            margin-bottom: 0px !important;
            box-shadow: 0 4px 16px rgba(0, 45, 66, 0.08), 0 1px 3px rgba(0, 0, 0, 0.05) !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
            cursor: pointer !important;
            user-select: none;
            text-align: center !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .kpi-card:hover {
            transform: translateY(-4px) !important;
            box-shadow: 0 10px 25px rgba(0, 45, 66, 0.15), 0 2px 6px rgba(0, 0, 0, 0.08) !important;
        }
        /* 🎨 5대 KPI 카드별 소프트 파스텔 그라데이션 및 상단 5px 컬러 바 */
        .kpi-card-hours {
            background: linear-gradient(180deg, #f0f9ff 0%, #ffffff 85%) !important;
            border: 1px solid #bae6fd !important;
            border-top: 5px solid #005073 !important;
        }
        .kpi-card-tasks {
            background: linear-gradient(180deg, #eff6ff 0%, #ffffff 85%) !important;
            border: 1px solid #bfdbfe !important;
            border-top: 5px solid #0284c7 !important;
        }
        .kpi-card-workers {
            background: linear-gradient(180deg, #f5f3ff 0%, #ffffff 85%) !important;
            border: 1px solid #ddd6fe !important;
            border-top: 5px solid #4f46e5 !important;
        }
        .kpi-card-urgent {
            background: linear-gradient(180deg, #fffbeb 0%, #ffffff 85%) !important;
            border: 1px solid #fde68a !important;
            border-top: 5px solid #ea580c !important;
        }
        .kpi-card-overdue-danger {
            background: linear-gradient(180deg, #fef2f2 0%, #ffffff 85%) !important;
            border: 1px solid #fca5a5 !important;
            border-top: 5px solid #dc2626 !important;
        }
        .kpi-card-overdue-safe {
            background: linear-gradient(180deg, #f0fdf4 0%, #ffffff 85%) !important;
            border: 1px solid #bbf7d0 !important;
            border-top: 5px solid #16a34a !important;
        }
        /* 🌟 5대 KPI 카드 투명 오버레이 버튼: 카드를 완벽하게 덮어서 원클릭 모달 오픈 유지 */
        div[data-testid="column"]:hover .kpi-card,
        div[data-testid="stColumn"]:hover .kpi-card {
            transform: translateY(-4px) !important;
            box-shadow: 0 10px 25px rgba(0, 45, 66, 0.15), 0 2px 6px rgba(0, 0, 0, 0.08) !important;
        }
        div.element-container:has(.kpi-card) + div.element-container {
            margin-top: -138px !important;
            height: 138px !important;
            position: relative !important;
            z-index: 20 !important;
        }
        div.element-container:has(.kpi-card) + div.element-container .stButton,
        div.element-container:has(.kpi-card) + div.element-container button,
        button[aria-label=" "] {
            height: 138px !important;
            min-height: 138px !important;
            width: 100% !important;
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            color: transparent !important;
            opacity: 0 !important;
            cursor: pointer !important;
            padding: 0 !important;
            margin: 0 !important;
        }

        .kpi-title {
            font-size: 16.5px !important;
            font-weight: 800 !important;
            color: #002d42 !important;
            text-transform: uppercase !important;
            padding-bottom: 8px !important;
            margin-bottom: 10px !important;
            border-bottom: 1.5px solid #e2e8f0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
            gap: 6px !important;
            letter-spacing: -0.3px !important;
            text-align: center !important;
        }
        .kpi-value {
            font-size: 35px !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
            margin-bottom: 10px !important;
            font-family: 'Segoe UI', Pretendard, sans-serif !important;
            color: #0f172a !important;
            display: flex !important;
            align-items: baseline !important;
            justify-content: center !important;
            width: 100% !important;
            text-align: center !important;
        }
        .kpi-unit {
            font-size: 15px !important;
            font-weight: 700 !important;
            color: #64748b !important;
            margin-left: 4px !important;
        }
        .kpi-badge {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 4px !important;
            padding: 4px 10px !important;
            border-radius: 6px !important;
            font-size: 12px !important;
            font-weight: 800 !important;
            letter-spacing: -0.2px !important;
            margin: 0 auto !important;
        }
        .badge-cyan { background-color: #e0f2fe !important; color: #0369a1 !important; border: 1px solid #bae6fd !important; }
        .badge-green { background-color: #d1e7dd !important; color: #0f5132 !important; border: 1px solid #a3cfbb !important; }
        .badge-purple { background-color: #ede9fe !important; color: #5b21b6 !important; border: 1px solid #c4b5fd !important; }
        .badge-amber { background-color: #fef3c7 !important; color: #d97706 !important; border: 1px solid #fde68a !important; }
        .badge-red { background-color: #fee2e2 !important; color: #dc2626 !important; border: 1px solid #fca5a5 !important; }
        /* 🏛️ Cisco APIC 트리 메뉴 사이드바 스타일링 */
        [data-testid="stSidebar"] {
            background-color: #002d42 !important;
            border-right: 1px solid #003852 !important;
        }
        [data-testid="stSidebar"] * {
            color: #bdcddc !important;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: #00b4d8 !important;
        }
        [data-testid="stSidebar"] .block-container,
        [data-testid="stSidebarUserContent"] {
            padding-top: 0.4rem !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        [data-testid="stSidebarHeader"] {
            padding-top: 0.4rem !important;
            padding-bottom: 0.1rem !important;
        }
        /* 사이드바 내부 엘리먼트 초밀착 (APIC 트리 간격) */
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"],
        [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] > div {
            gap: 1px !important;
        }
        [data-testid="stSidebar"] div.element-container {
            margin-top: 0px !important;
            margin-bottom: 0px !important;
            padding-top: 0px !important;
            padding-bottom: 0px !important;
        }
        /* 🌲 APIC 트리 노드 (Expander = 폴더/카테고리 헤더) */
        [data-testid="stSidebar"] [data-testid="stExpander"],
        [data-testid="stSidebar"] details,
        [data-testid="stSidebar"] details[data-testid="stExpander"] {
            margin-top: 0px !important;
            margin-bottom: 0px !important;
            border: none !important;
            box-shadow: none !important;
            background: transparent !important;
            background-color: transparent !important;
        }
        [data-testid="stSidebar"] details,
        [data-testid="stSidebar"] div[data-testid="stExpanderDetails"] {
            border: none !important;
            border-radius: 0px !important;
            background-color: transparent !important;
            background: transparent !important;
            padding-top: 0px !important;
            padding-bottom: 0px !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] details[data-testid="stExpander"] summary,
        [data-testid="stSidebar"] details summary,
        [data-testid="stSidebar"] [data-testid="stExpanderSummary"],
        [data-testid="stSidebar"] .streamlit-expanderHeader {
            font-weight: 800 !important;
            font-size: 13px !important;
            color: #ffffff !important;
            background: transparent !important;
            background-color: transparent !important;
            background-image: none !important;
            border: none !important;
            border-radius: 0px !important;
            border-bottom: 1px solid #1a5a73 !important;
            padding: 8px 8px 6px 8px !important;
            min-height: 28px !important;
            box-shadow: none !important;
            display: flex !important;
            align-items: center !important;
            letter-spacing: 0.3px !important;
            text-transform: uppercase !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary *,
        [data-testid="stSidebar"] details[data-testid="stExpander"] summary *,
        [data-testid="stSidebar"] [data-testid="stExpanderSummary"] *,
        [data-testid="stSidebar"] .streamlit-expanderHeader * {
            font-weight: 800 !important;
            font-size: 13px !important;
            color: #ffffff !important;
            background: transparent !important;
            background-color: transparent !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover,
        [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover *,
        [data-testid="stSidebar"] details[data-testid="stExpander"] summary:hover,
        [data-testid="stSidebar"] details[data-testid="stExpander"] summary:hover * {
            color: #00b4d8 !important;
            background: rgba(0, 180, 216, 0.06) !important;
            background-color: rgba(0, 180, 216, 0.06) !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary svg,
        [data-testid="stSidebar"] details[data-testid="stExpander"] summary svg {
            fill: #4a7b94 !important;
            color: #4a7b94 !important;
            width: 14px !important;
            height: 14px !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover svg,
        [data-testid="stSidebar"] details[data-testid="stExpander"] summary:hover svg {
            fill: #00b4d8 !important;
            color: #00b4d8 !important;
        }
        /* 사이드바 내부 라벨 & 인풋 */
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stMarkdown p {
            color: #e2e8f0 !important;
            font-weight: 600 !important;
        }
        /* 사이드바 셀렉트박스 완벽 복원 (글씨 선명한 흰색 & 배경 유지) */
        [data-testid="stSidebar"] [data-baseweb="select"] {
            background-color: #002d42 !important;
            color: #ffffff !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] * {
            color: #ffffff !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background-color: #002d42 !important;
            border: 1px solid #003852 !important;
            border-radius: 4px !important;
            color: #ffffff !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] svg {
            fill: #00b4d8 !important;
            color: #00b4d8 !important;
        }
        /* 사이드바 라디오 & 체크박스 */
        [data-testid="stSidebar"] [data-baseweb="radio"] div {
            color: #bdcddc !important;
        }
        [data-testid="stSidebar"] [data-baseweb="checkbox"] span {
            color: #bdcddc !important;
        }
        /* 🌲 APIC 트리 아이템: 하위 메뉴 버튼에만 정밀하게 좌측 정렬 적용 (다른 위젯 간섭 0%) */
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button,
        [data-testid="stSidebar"] details .stButton > button {
            display: flex !important;
            justify-content: flex-start !important;
            align-items: center !important;
            text-align: left !important;
            border-radius: 0px !important;
            font-size: 12.5px !important;
            font-weight: 500 !important;
            background-color: transparent !important;
            border: none !important;
            border-left: 3px solid transparent !important;
            color: #bdcddc !important;
            transition: all 0.12s ease !important;
            padding: 6px 8px 6px 12px !important;
            min-height: 30px !important;
            width: 100% !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button div,
        [data-testid="stSidebar"] details .stButton > button div {
            justify-content: flex-start !important;
            text-align: left !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] details .stButton > button [data-testid="stMarkdownContainer"] {
            width: 100% !important;
            text-align: left !important;
            display: flex !important;
            justify-content: flex-start !important;
            align-items: center !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] details .stButton > button [data-testid="stMarkdownContainer"] p {
            text-align: left !important;
            width: 100% !important;
            margin: 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover,
        [data-testid="stSidebar"] details .stButton > button:hover {
            background-color: rgba(0, 180, 216, 0.10) !important;
            color: #ffffff !important;
            border-left: 3px solid #00b4d8 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] details .stButton > button[kind="primary"] {
            background-color: rgba(0, 180, 216, 0.15) !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            border-left: 3px solid #00b4d8 !important;
            border-radius: 0px !important;
            box-shadow: none !important;
        }
        /* 🏠 홈 버튼 빨간색 배경 & 중앙 정렬 (APIC 스타일 메인 네비게이션) */
        [data-testid="stSidebar"] .element-container:has(#home-nav-marker) + .element-container button {
            background-color: #b91c1c !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            border-left: 3px solid #ef4444 !important;
            border-radius: 4px !important;
            padding: 7px 12px !important;
            justify-content: center !important;
            text-align: center !important;
        }
        [data-testid="stSidebar"] .element-container:has(#home-nav-marker) + .element-container button * {
            justify-content: center !important;
            text-align: center !important;
        }
        [data-testid="stSidebar"] .element-container:has(#home-nav-marker) + .element-container button:hover {
            background-color: #991b1b !important;
            border-left: 3px solid #f87171 !important;
        }

        /* 🏛️ Cisco ACI 표준 테이블 스타일링 */
        table {
            width: 100% !important;
            border-collapse: collapse !important;
            background: #ffffff !important;
            border-radius: 8px !important;
            overflow: hidden !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
            margin-bottom: 25px !important;
        }
        th {
            background-color: #005073 !important;
            color: #ffffff !important;
            font-weight: 600 !important;
            padding: 12px 16px !important;
            text-align: left !important;
            font-size: 13.5px !important;
        }
        td {
            padding: 12px 16px !important;
            border-bottom: 1px solid #e1e4e8 !important;
            color: #334155 !important;
            font-size: 13.5px !important;
        }

        /* 🏛️ 과중 근무 알림 배너 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) {
            background: #fff5f5 !important;
            border: 1.5px solid #fecaca !important;
            border-left: 8px solid #dc2626 !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
            padding: 14px 20px !important;
            margin-top: 10px !important;
            margin-bottom: 6px !important;
        }
        /* 🚨 과중 근무 알림 배너 내부 버튼 및 사람 이름 칩 글자 선명한 흰색 볼드 표출 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton > button,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button {
            background-color: #1e293b !important;
            border: 1px solid #475569 !important;
            border-radius: 6px !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 13px !important;
            padding: 4px 12px !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton > button *,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button * {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton > button:hover,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button:hover {
            background-color: #334155 !important;
            border-color: #94a3b8 !important;
            color: #ffffff !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton > button:hover *,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button:hover * {
            color: #ffffff !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.normal-status-badge) {
            background: #f0fdf4 !important;
            border: 1.5px solid #bbf7d0 !important;
            border-left: 8px solid #16a34a !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
            padding: 12px 20px !important;
            margin-top: 8px !important;
            margin-bottom: 6px !important;
            text-align: center !important;
        }
        .normal-status-badge {
            background: #d1e7dd !important;
            color: #0f5132 !important;
            border: 1px solid #a3cfbb !important;
            padding: 3px 12px !important;
            border-radius: 4px !important;
            font-weight: 700 !important;
            font-size: 13px !important;
            display: inline-flex !important;
            align-items: center !important;
        }
        .alert-blink-badge {
            background: #fee2e2 !important;
            color: #dc2626 !important;
            border: 1px solid #fca5a5 !important;
            padding: 3px 12px !important;
            border-radius: 4px !important;
            font-weight: 700 !important;
            font-size: 13px !important;
            display: inline-flex !important;
            align-items: center !important;
        }

        /* 🏛️ LIVE 관제 중 하위 통합 대형 네모 컨테이너 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.live-board-main-container) {
            background: #ffffff !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 18px rgba(0, 45, 66, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04) !important;
            padding: 22px 24px 24px 24px !important;
            margin-top: 4px !important;
            margin-bottom: 24px !important;
        }

        /* 🚫 툴팁 오버레이 완전 차단 */
        div[data-baseweb="tooltip"],
        div[role="tooltip"],
        .stTooltipContent,
        [data-testid="stTooltipContent"],
        [data-testid="stTooltipHoverTarget"] div[data-baseweb="tooltip"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }

        /* ⚡ 팝업 모달 다이얼로그(@st.dialog) 및 배경(Backdrop) 페이드/트랜지션 애니메이션 완전 제거 (즉시 표출) */
        div[data-baseweb="backdrop"],
        div[data-testid="stDialog"],
        div[data-testid="stDialog"] > div,
        div[role="dialog"],
        div[role="dialog"] > div,
        div[data-baseweb="modal"],
        div[data-baseweb="modal"] > div {
            transition: none !important;
            transition-duration: 0s !important;
            transition-delay: 0s !important;
            animation: none !important;
            animation-duration: 0s !important;
            animation-delay: 0s !important;
            transform: none !important;
        }
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        section.main {
            transition: none !important;
        }

        /* 🏛️ 팝업 모달 다이얼로그 (@st.dialog) 제목 및 닫기 버튼 흰색 스타일링 */
        div[data-testid="stDialog"] h1,
        div[data-testid="stDialog"] h2,
        div[data-testid="stDialog"] h3,
        div[data-testid="stDialog"] [data-testid="stHeadingWithActionElements"] h2,
        div[data-testid="stDialog"] [data-testid="stMarkdownContainer"] h2,
        div[data-testid="stDialog"] header,
        div[data-testid="stDialog"] header *,
        div[role="dialog"] h1,
        div[role="dialog"] h2,
        div[role="dialog"] h3,
        div[role="dialog"] [data-testid="stHeadingWithActionElements"] h2,
        div[role="dialog"] [data-testid="stMarkdownContainer"] h2,
        div[role="dialog"] header,
        div[role="dialog"] header *,
        div[data-baseweb="modal"] h1,
        div[data-baseweb="modal"] h2,
        div[data-baseweb="modal"] h3,
        div[data-baseweb="modal"] header,
        div[data-baseweb="modal"] header * {
            color: #ffffff !important;
            font-weight: 800 !important;
            fill: #ffffff !important;
        }
        div[data-testid="stDialog"] h1 *,
        div[data-testid="stDialog"] h2 *,
        div[data-testid="stDialog"] h3 *,
        div[role="dialog"] h1 *,
        div[role="dialog"] h2 *,
        div[role="dialog"] h3 * {
            color: #ffffff !important;
            fill: #ffffff !important;
        }
        div[data-testid="stDialog"] button[aria-label="Close"],
        div[data-testid="stDialog"] button[data-testid="stBaseButton-header"],
        div[role="dialog"] button[aria-label="Close"],
        div[role="dialog"] button[data-testid="stBaseButton-header"],
        div[data-baseweb="modal"] button[aria-label="Close"] {
            color: #ffffff !important;
        }
        div[data-testid="stDialog"] button[aria-label="Close"] svg,
        div[role="dialog"] button[aria-label="Close"] svg {
            fill: #ffffff !important;
            stroke: #ffffff !important;
        }

        /* 🏛️ 드롭다운 팝오버 및 셀렉트박스 옵션 가독성 */
        div[data-baseweb="popover"] {
            background-color: #ffffff !important;
            border: 1px solid #e1e4e8 !important;
            border-radius: 6px !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1) !important;
        }
        div[data-baseweb="popover"] *,
        ul[role="listbox"] * {
            color: #0f172a !important;
        }

    </style>
    """, unsafe_allow_html=True)



def render_header_banner(initial_ms: int, page_tag: str):
    """LGU+ time.bora.net NTP 타임서버 실시간 동기화 헤더 배너 렌더링"""
    components.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
            }}
            body {{
                background: transparent;
                overflow: hidden;
            }}
            .header-bar {{
                background: linear-gradient(135deg, #002233 0%, #003a55 50%, #004d71 100%);
                color: #ffffff;
                padding: 11px 20px 11px 18px;
                border-radius: 9px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 4px 14px rgba(0, 34, 51, 0.25);
                border: 1px solid #005f8a;
            }}
            .header-left {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .header-title {{
                font-size: 18.5px;
                font-weight: 800;
                color: #ffffff;
                letter-spacing: -0.4px;
                text-shadow: 0 1px 3px rgba(0,0,0,0.5);
            }}
            .header-tag {{
                background: rgba(0, 180, 216, 0.22);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.5);
                padding: 2px 8px;
                border-radius: 6px;
                font-size: 11.5px;
                font-weight: 700;
                margin-left: 4px;
            }}
            .header-right {{
                font-size: 12.5px;
                color: #94a3b8;
                display: flex;
                align-items: center;
                gap: 14px;
            }}
            .clock-box {{
                display: inline-flex;
                align-items: center;
                gap: 6px;
                background-color: rgba(15, 23, 42, 0.55);
                color: #e2e8f0;
                padding: 4px 13px;
                border-radius: 20px;
                font-weight: bold;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }}
            #live-bora-clock {{
                color: #ffffff;
                font-weight: 700;
                font-family: 'Segoe UI', Pretendard, sans-serif;
                letter-spacing: -0.2px;
            }}
            .badge-bora {{
                background: #0284c7;
                color: #ffffff;
                font-size: 10px;
                font-weight: 800;
                padding: 1px 6px;
                border-radius: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header-bar">
            <div class="header-left">
                <span class="header-title">📊 기술본부 현장 업무 관제 센터</span>
                <span class="header-tag">{page_tag}</span>
            </div>
            <div class="header-right">
                <span style="font-weight: 700; color: #4ade80;"><span style="color: #22c55e; text-shadow: 0 0 8px #22c55e;">●</span> 관제 포털 정상 가동</span>
                <span style="color: rgba(255,255,255,0.25);">|</span>
                <div class="clock-box">
                    <span>🕒</span>
                    <span id="live-bora-clock">로딩 중...</span>
                    <span class="badge-bora" title="LGU+ time.bora.net NTP 타임서버 실시간 동기화">time.bora.net·KST</span>
                </div>
            </div>
        </div>
        <script>
            let serverTime = {initial_ms};
            let clientStart = performance.now();
            function tickBoraClock() {{
                let current = new Date(serverTime + (performance.now() - clientStart));
                let formatter = new Intl.DateTimeFormat('ko-KR', {{
                    timeZone: 'Asia/Seoul',
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                }});
                let parts = formatter.formatToParts(current);
                let p = {{}};
                parts.forEach(x => p[x.type] = x.value);
                let el = document.getElementById('live-bora-clock');
                if (el) {{
                    el.innerText = p.year + '-' + p.month + '-' + p.day + ' ' + p.hour + ':' + p.minute + ':' + p.second;
                }}
            }}
            setInterval(tickBoraClock, 1000);
            tickBoraClock();
        </script>
    </body>
    </html>
    """, height=56)

