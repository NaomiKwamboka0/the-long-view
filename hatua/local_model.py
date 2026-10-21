"""Strict loopback-only access for the optional Ollama planner and writer."""
import os
import urllib.request
from urllib.parse import urlsplit


def local_host(value=None):
    value = value if value is not None else os.environ.get("HATUA_OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        url = urlsplit(value)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.username is not None or url.password is not None
                or url.path not in ("", "/") or url.query or url.fragment):
            return None
        port = url.port if url.port is not None else 11434
        if not 1 <= port <= 65535:
            return None
    except (ValueError, TypeError):
        return None
    # Resolve localhost to a literal loopback address; never use DNS or env proxies.
    host = "[::1]" if url.hostname == "::1" else "127.0.0.1"
    return f"http://{host}:{port}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_local(request, timeout):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    return opener.open(request, timeout=timeout)
