from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import uvicorn
import dotenv
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
from controllers.Github_Api_Controller import router as github_router 
from controllers.developer_insights_controller import router as developer_insights_router
from controllers.auth_controller import router as auth_router

# Lifecycle Manager for Kafka Consumer
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or your React origin like "http://localhost:3000"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include GitHub API controller routes
app.include_router(github_router)
app.include_router(developer_insights_router)
app.include_router(auth_router)

@app.get("/")
async def root():
    return {"message": "FastAPI with Milvus is running!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)