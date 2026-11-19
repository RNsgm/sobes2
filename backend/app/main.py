from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.keitaro.client import KeitaroError, close_keitaro


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_keitaro()


app = FastAPI(title="Keitaro Wrapper", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(KeitaroError)
async def keitaro_error_handler(_: Request, exc: KeitaroError):
    # 401/403 от Keitaro — это проблема ключа обёртки, а не пользователя фронта
    status = 502 if exc.status_code in (401, 403) or exc.status_code >= 500 else exc.status_code
    return JSONResponse(status_code=status, content={"detail": exc.message})


app.include_router(router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
