"""
StaySweep — Web Server
-----------------------
FastAPI application with SSE for real-time search progress.

Run with:
    python -m web.app
    # or
    uvicorn web.app:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from main import run_pipeline

app = FastAPI(title="StaySweep")

# Serve static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# In-memory store for active searches
active_searches: dict[str, asyncio.Queue] = {}
search_results: dict[str, list] = {}


class SearchRequest(BaseModel):
    query: str
    city: str


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))


@app.post("/api/search")
async def start_search(req: SearchRequest):
    search_id = str(uuid.uuid4())[:8]
    queue = asyncio.Queue()
    active_searches[search_id] = queue
    search_results[search_id] = []

    async def on_progress(event):
        await queue.put(("status", event))

    async def on_result(result):
        search_results[search_id].append(result)
        await queue.put(("hotel_result", result))

    async def run_search():
        try:
            results = await run_pipeline(
                req.query, req.city,
                on_progress=on_progress,
                on_result=on_result,
            )
            search_results[search_id] = sorted(results, key=lambda x: x["final_score"], reverse=True)
            await queue.put(("complete", {"results": search_results[search_id]}))
        except Exception as e:
            await queue.put(("error", {"message": str(e)}))
        finally:
            await queue.put(None)  # sentinel

    asyncio.create_task(run_search())
    return {"search_id": search_id}


@app.get("/api/search/{search_id}/stream")
async def stream_search(search_id: str):
    queue = active_searches.get(search_id)
    if not queue:
        return JSONResponse({"error": "Search not found"}, status_code=404)

    async def event_generator():
        # Send heartbeat immediately
        yield {"event": "heartbeat", "data": "{}"}

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
                if item is None:
                    break
                event_type, data = item
                yield {"event": event_type, "data": json.dumps(data)}
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": "{}"}

        # Cleanup
        active_searches.pop(search_id, None)

    return EventSourceResponse(event_generator())


@app.get("/api/results/{search_id}")
async def get_results(search_id: str):
    results = search_results.get(search_id)
    if results is None:
        return JSONResponse({"error": "Results not found"}, status_code=404)
    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
