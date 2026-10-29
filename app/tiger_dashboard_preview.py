from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import tiger_dashboard


app: FastAPI = FastAPI()

APP_DIR: Path = Path(__file__).resolve().parent

app.mount(
    "/static",
    StaticFiles(directory=str(APP_DIR / "static")),
    name="static",
)

app.include_router(tiger_dashboard.router)


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(
        url="/dashboard",
        status_code=303,
    )
