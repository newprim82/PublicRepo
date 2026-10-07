# -*- coding: utf-8 -*-
"""
🏛️ 대시보드 전역 스타일링 및 상단 헤더 프레임 로더
- CSS 본문: src/dashboard/styles.css 파일로 완전 분리
- 로딩 방식: @st.cache_data를 통한 1회 고속 메모리 캐싱 주입
"""

from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

CSS_FILE_PATH = Path(__file__).resolve().parent / "styles.css"


@st.cache_data(show_spinner=False)
def _load_stylesheet() -> str:
    """styles.css 파일을 읽어와 메모리에 캐싱"""
    if CSS_FILE_PATH.exists():
        return CSS_FILE_PATH.read_text(encoding="utf-8")
    return ""


def apply_custom_styles():
    """전역 Cisco ACI Enterprise 테마 및 Pretendard 폰트 CSS 주입"""
    css_content = _load_stylesheet()
    if css_content:
        st.markdown(f"<style>\n{css_content}\n</style>", unsafe_allow_html=True)


def render_header_banner(initial_ms: int, page_tag: str):
    """
    🏛️ Frame 2: 실시간 NTP 시계 & 기술본부 관제센터 고정 헤더 배너
    """
    components.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: transparent;
                font-family: 'Segoe UI', Pretendard, -apple-system, sans-serif;
                overflow: hidden;
            }}
            .header-bar {{
                background: linear-gradient(135deg, #001e2d 0%, #00364d 50%, #004d71 100%);
                height: 52px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 20px;
                border-radius: 8px;
                box-shadow: 0 4px 14px rgba(0, 30, 45, 0.25);
                border: 1px solid rgba(0, 180, 216, 0.3);
            }}
            .header-left {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .header-title {{
                color: #ffffff;
                font-size: 16.5px;
                font-weight: 800;
                letter-spacing: -0.3px;
                text-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
            }}
            .header-tag {{
                background: rgba(0, 180, 216, 0.18);
                color: #00e5ff;
                border: 1px solid #00b4d8;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            .header-right {{
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


# 하위 호환 별칭
render_top_floating_header = render_header_banner

