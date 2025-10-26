# src/utils/paths.py
from pathlib import Path
import os

# Force correct project root: go up from this file
FILE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FILE_DIR.parent.parent  # src/utils → src → project_root

# Debug print (remove later)
print(f"[PATHS] Project root resolved to: {PROJECT_ROOT}")
print(f"[PATHS] Exists: {PROJECT_ROOT.exists()}")

# Data paths
DATA_DIR = PROJECT_ROOT / "data"
INPUTS_DIR = DATA_DIR / "inputs"
OUTPUTS_DIR = DATA_DIR / "outputs"
LOGS_DIR = DATA_DIR / "logs"

# Create if missing
INPUTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Optional: Force working directory (extra safety)
os.chdir(PROJECT_ROOT)
print(f"[PATHS] Changed working dir to: {Path.cwd()}")