# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.active import router as active_router
from app.passive import router as passive_router
from app.lifespan import lifespan
from app.ws_routes import ws_router


app = FastAPI(lifespan=lifespan)
#防止跨域处理
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发阶段）；生产环境建议指定来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)
app.include_router(ws_router)
app.include_router(active_router)
app.include_router(passive_router)
