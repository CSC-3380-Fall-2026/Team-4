from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import tiger_dashboard


app: FastAPI = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=str(tiger_dashboard.APP_DIR / "static")),
    name="static",
)

app.include_router(tiger_dashboard.router)


@app.get("/")
def root(request: Request) -> RedirectResponse:
    return RedirectResponse(
        url=tiger_dashboard.panel_url(request),
        status_code=303,
    )
