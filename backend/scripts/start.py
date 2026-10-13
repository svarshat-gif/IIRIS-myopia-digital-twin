"""Release startup: require a model, migrate, then serve one rate-limited worker."""
import os
import subprocess
import sys
import uvicorn
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.ml.registry import load_bundle  # noqa: E402

if not settings.model_path.is_file():
    raise SystemExit("Required model artifact missing. Run make model, then rebuild the image.")
bundle = load_bundle()
if bundle.get("data_is_synthetic") is not False:
    raise SystemExit("Refusing to serve a synthetic model. Train from verified open data.")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")),
            workers=1, access_log=False, proxy_headers=False)
