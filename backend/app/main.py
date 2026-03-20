from fastapi import FastAPI
from backend.app.routes.upload import router as upload_router

app = FastAPI(title="Document Processing API")

app.include_router(upload_router)

@app.get("/")
def root():
    return {"message": "API running"}