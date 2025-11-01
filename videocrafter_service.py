from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from typing import Optional
import sys
from pathlib import Path
import time
import subprocess

app = FastAPI()
WORKDIR = Path("jobs")
WORKDIR.mkdir(exist_ok=True)
PYTHON_BIN = sys.executable  # Python hiện tại đang chạy

jobs = {}

class VideoRequest(BaseModel):
    prompt: str                # Văn bản mô tả video
    type: str = "t2v"          # 't2v' hoặc 'i2v'
    duration: int = 4           # Thời lượng video (giây)
    fps: int = 12               # Frame per second
    resolution: str = "512x320" # "320x512", "640x1024", ...
    style: Optional[str] = None # Style name, ví dụ "van Gogh"
    seed: Optional[int] = None  # Seed cho random, đảm bảo reproducible
    num_inference_steps: int = 30 # Số bước diffusion
    scale: float = 7.5           # CFG scale, nếu model hỗ trợ

def generate_video(job_id: str, req: VideoRequest):
    out_dir = WORKDIR / job_id
    out_dir.mkdir(exist_ok=True)
    jobs[job_id]["status"] = "running"

    base_cmd = ""
    if req.type == "t2v":
        base_cmd = f"{PYTHON_BIN} scripts/run_text2video.py --prompt \"{req.prompt}\" --out_dir {out_dir}"
    else:
        base_cmd = f"{PYTHON_BIN} scripts/run_image2video.py --prompt \"{req.prompt}\" --out_dir {out_dir}"

    # Thêm các tham số nâng cao
    base_cmd += f" --duration {req.duration}"
    base_cmd += f" --fps {req.fps}"
    base_cmd += f" --resolution {req.resolution}"
    if req.style:
        base_cmd += f" --style \"{req.style}\""
    if req.seed:
        base_cmd += f" --seed {req.seed}"
    base_cmd += f" --num_inference_steps {req.num_inference_steps}"
    base_cmd += f" --scale {req.scale}"

    try:
        subprocess.run(base_cmd, shell=True, check=True)
        jobs[job_id]["status"] = "finished"
        jobs[job_id]["result"] = str(next(out_dir.glob("*.mp4")))
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["logs"].append(str(e))

@app.post("/generate")
async def create_job(req: VideoRequest, background: BackgroundTasks):
    job_id = uuid4().hex
    jobs[job_id] = {"status":"queued", "logs":[], "result": None}
    background.add_task(generate_video, job_id, req)
    return {"job_id": job_id}

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    info = jobs[job_id].copy()
    return {"job_id": job_id, "status": info["status"], "logs": info["logs"], "result_available": info["result"] is not None}

from fastapi.staticfiles import StaticFiles
app.mount("/files", StaticFiles(directory=str(WORKDIR)), name="files")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("videocrafter_service:app", host="0.0.0.0", port=5001, reload=True)