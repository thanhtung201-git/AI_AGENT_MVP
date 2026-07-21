"""
FastAPI entry point cho AI Agent MVP.
Chạy: uvicorn backend.api.main:app --reload --port 8000
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from backend.api.routes import po, trimlist, history, agent, recap, dashboard, batch_go, compare, upload_history, task_a, task_b, task_c

app = FastAPI(
    title="AI Agent MVP — Garment PO & Trimlist",
    description="API để xử lý Purchase Order và tạo Trim List từ Tech Pack",
    version="1.0.0",
)

# CORS — cho phép Next.js frontend (localhost:3000) gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(agent.router,    prefix="/api/agent",    tags=["Agent"])
app.include_router(recap.router,    prefix="/api/recap",    tags=["Recap"])
app.include_router(po.router,       prefix="/api/po",       tags=["PO"])
app.include_router(trimlist.router, prefix="/api/trimlist", tags=["Trimlist"])
app.include_router(history.router,  prefix="/api/history",  tags=["History"])
app.include_router(batch_go.router)
app.include_router(compare.router)
app.include_router(upload_history.router)
app.include_router(task_a.router,   prefix="/api/task-a",   tags=["Task A"])
app.include_router(task_b.router,   prefix="/api/task-b",   tags=["Task B"])
app.include_router(task_c.router,   prefix="/api/task-c",   tags=["Task C"])


@app.get("/")
def root():
    return {"status": "ok", "message": "AI Agent MVP API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}
