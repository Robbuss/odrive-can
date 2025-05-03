from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routers import joints_router

app = FastAPI(title="Robotic Arm API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(joints_router)