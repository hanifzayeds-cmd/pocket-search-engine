import os
from typing import Optional, List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Configuration ---
# Set this in your Render dashboard (or a local .env file)
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://localhost:8080")
# The timeout for the request to SearXNG
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", 30.0))

app = FastAPI(
    title="SearXNG FastAPI Wrapper",
    description="A privacy-focused search API wrapper for SearXNG.",
    version="1.0.0",
)

# Allow your frontend to call this API from a browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production (e.g., ["https://yourfrontend.com"])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models for Validation & Docs ---
class SearchResponse(BaseModel):
    query: str
    number_of_results: int = 0
    results: List[Dict[str, Any]] = Field(default_factory=list)
    answers: List[Any] = Field(default_factory=list)
    corrections: List[Any] = Field(default_factory=list)
    infoboxes: List[Any] = Field(default_factory=list)
    suggestions: List[Any] = Field(default_factory=list)
    unresponsive_engines: List[Any] = Field(default_factory=list)

# --- Core Search Endpoint ---
@app.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="The search query string", min_length=1),
    categories: Optional[str] = Query(None, description="Comma-separated list of categories (e.g., 'general,news')"),
    engines: Optional[str] = Query(None, description="Comma-separated list of engines (e.g., 'google,duckduckgo')"),
    language: str = Query("en", description="Language code (e.g., 'en', 'de')"),
    pageno: int = Query(1, ge=1, description="Page number (1-based)"),
    time_range: Optional[str] = Query(None, description="Time filter: 'day', 'month', 'year'"),
    safesearch: int = Query(0, ge=0, le=2, description="SafeSearch: 0 (off), 1 (moderate), 2 (strict)"),
):
    """
    Proxies a search request to the configured SearXNG instance.
    """
    # Build the parameters for SearXNG (matching its official API contract)
    params = {
        "q": q,
        "format": "json",  # This is essential for machine-readable output[reference:1]
        "language": language,
        "pageno": pageno,
        "safesearch": safesearch,
    }
    if categories:
        params["categories"] = categories
    if engines:
        params["engines"] = engines
    if time_range:
        params["time_range"] = time_range

    search_url = f"{SEARXNG_BASE_URL.rstrip('/')}/search"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Validate and return the structured response
            return SearchResponse(**data)

        except httpx.HTTPStatusError as e:
            # Forward SearXNG's error status (e.g., 403 if JSON is not enabled)
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"SearXNG request failed: {e.response.text}",
            )
        except httpx.RequestError as e:
            # Handle network/connection errors
            raise HTTPException(
                status_code=502,
                detail=f"Unable to connect to SearXNG instance: {str(e)}",
            )
        except Exception as e:
            # Catch JSON parsing errors or other unexpected issues
            raise HTTPException(status_code=500, detail=f"Internal wrapper error: {str(e)}")

# --- Health Check Endpoint (Recommended for Render) ---
@app.get("/health")
async def health():
    """Returns the health status of the wrapper and its connection to SearXNG."""
    searxng_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # A simple GET to the base URL often returns a 200 even if no search is performed
            resp = await client.get(SEARXNG_BASE_URL)
            searxng_status = "healthy" if resp.status_code < 500 else "degraded"
    except Exception:
        searxng_status = "unreachable"

    return {
        "status": "ok",
        "wrapper": "healthy",
        "searxng_instance": searxng_status,
    }