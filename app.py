import os
import sys
from pathlib import Path
import runpy

_root = Path(__file__).resolve().parent
if (_root / "worktime_dashboard").exists():
    _worktime_dir = _root / "worktime_dashboard"
else:
    _worktime_dir = _root.parent.parent / "worktime_dashboard"

os.chdir(str(_worktime_dir))
if str(_worktime_dir) not in sys.path:
    sys.path.insert(0, str(_worktime_dir))

_target_app = _worktime_dir / "src" / "dashboard" / "app.py"

# 캐시된 구버전 모듈 무효화로 최신 코드 즉시 로드 보장
for mod in list(sys.modules.keys()):
    if mod.startswith("src.") or mod == "src":
        del sys.modules[mod]

runpy.run_path(str(_target_app), run_name="__main__")
