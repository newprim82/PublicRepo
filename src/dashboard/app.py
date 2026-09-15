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
runpy.run_path(str(_target_app), run_name="__main__")
