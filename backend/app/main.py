from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import core, service

app = FastAPI(title="UK wind forecast monitor", version="1.0")


@app.exception_handler(FileNotFoundError)
async def _no_data(_: Request, exc: FileNotFoundError):
    return JSONResponse({"detail": "No dataset found. Run `python -m app.ingest` (real data) first."}, status_code=503)


def _cutoff(c: str) -> str:
    if c not in core.CUTOFF_OPTIONS:
        raise HTTPException(400, f"cutoff must be one of {list(core.CUTOFF_OPTIONS)}")
    return c


def _date(d: str) -> str:
    if d not in service.store().dates:
        raise HTTPException(404, f"delivery date {d} outside loaded range")
    return d


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/meta")
def meta():
    return service.store().get_meta()


@app.get("/api/day")
def day(date: str, cutoff: str = "09:20"):
    return service.store().get_day(_date(date), _cutoff(cutoff))


@app.get("/api/metrics")
def metrics(cutoff: str = "09:20", date_from: str | None = None, date_to: str | None = None):
    return service.store().get_metrics(_cutoff(cutoff), date_from, date_to)


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():  # registered last so /api/* wins
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
