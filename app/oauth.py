from fastapi import Request


def local_redirect_uri(request: Request) -> str:
    """Azure allows localhost HTTP redirects, but rejects 127.0.0.1."""
    scheme = request.url.scheme or "http"
    port = request.url.port
    port_part = f":{port}" if port and port not in {80, 443} else ""
    return f"{scheme}://localhost{port_part}/auth/callback"
