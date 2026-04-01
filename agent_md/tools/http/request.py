"""Tool: http_request — Make HTTP requests."""

import httpx
from langchain_core.tools import tool


@tool
def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
) -> str:
    """Make an HTTP request and return the response.

    Args:
        url: Full URL for the request.
        method: HTTP method (GET, POST, PUT, DELETE, PATCH).
        headers: Optional request headers as a dict.
        body: Optional request body for POST/PUT.

    Returns:
        Status code and response body (truncated to 5000 chars).
    """
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.request(
                method=method.upper(),
                url=url,
                headers=headers or {},
                content=body,
            )
            body_text = response.text[:5000]
            if len(response.text) > 5000:
                body_text += "\n... [truncated]"
            return f"Status: {response.status_code}\n\n{body_text}"
    except httpx.TimeoutException:
        return f"ERROR: Request timed out after 30s: {url}"
    except Exception as e:
        return f"ERROR in HTTP request: {e}"
