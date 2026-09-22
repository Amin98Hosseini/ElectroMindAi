"""HTTP and socket helpers.

Bypass the Windows system proxy for localhost: TCP connects directly, but
urllib by default uses the system proxy (e.g. 127.0.0.1:59483) which resets
localhost connections.
"""
import socket
import urllib.error  # noqa: F401  (re-exported for convenience)
import urllib.request

_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_open(req, timeout=10):
    """urllib opener that ignores the system proxy (for 127.0.0.1 requests)."""
    return _NO_PROXY_OPENER.open(req, timeout=timeout)


def port_open(port, host="127.0.0.1"):
    """True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            return True
    except OSError:
        return False
