# Streamlit Cloud Auto-Deploy Trigger: 2026-10-21 11:40 (40/52h Governance Weekend Red Row Styling Fix)
import os
import sys
from pathlib import Path
import runpy

_file_dir = Path(__file__).resolve().parent

# 루트든 src/dashboard든 상관없이 정확한 worktime_dashboard 디렉토리 자동 감지
if (_file_dir / "worktime_dashboard").exists():
    _worktime_dir = _file_dir / "worktime_dashboard"
elif (_file_dir.parent.parent / "worktime_dashboard").exists():
    _worktime_dir = _file_dir.parent.parent / "worktime_dashboard"
else:
    _worktime_dir = _file_dir

os.chdir(str(_worktime_dir))
if str(_worktime_dir) in sys.path:
    sys.path.remove(str(_worktime_dir))
sys.path.insert(0, str(_worktime_dir))

# Streamlit Cloud 핫 리로드 시 뷰/다이얼로그/서비스 서브모듈을 메모리에서 강제 제거하여 최신 코드 반영 보장
for mod_name in list(sys.modules.keys()):
    if (mod_name.startswith("src.dashboard.common.") or 
        mod_name.startswith("src.dashboard.views.") or 
        mod_name.startswith("src.services.") or 
        mod_name.startswith("src.analytics.")):
        del sys.modules[mod_name]

_target_app = _worktime_dir / "src" / "dashboard" / "app.py"

runpy.run_path(str(_target_app), run_name="__main__")
