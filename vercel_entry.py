import sys
from pathlib import Path

app_dir: Path = Path(__file__).resolve().parent / "app"
sys.path.insert(0, str(app_dir))

from tiger_app import app
