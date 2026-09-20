import ipaddress
import socket
import urllib.parse
import httpx
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class MediaSecurityException(Exception):
    pass


class MediaProcessor:
    ALLOWED_MIMES = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "audio/mpeg",
        "audio/ogg",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    MAX_BYTES = 25 * 1024 * 1024  # 25 MB

    @staticmethod
    def is_private_ip(hostname: str) -> bool:
        """
        DNS resolution check against RFC 1918 / loopback / link-local addresses to prevent SSRF.
        """
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if (
                    ip_obj.is_private
                    or ip_obj.is_loopback
                    or ip_obj.is_link_local
                    or ip_obj.is_reserved
                    or ip_obj.is_multicast
                ):
                    return True
            return False
        except Exception:
            return True  # Fail-safe closed

    @classmethod
    async def download_media_secure(cls, url: str) -> Tuple[bytes, str]:
        """
        Downloads media with strict SSRF defense, size bounds, and MIME verification.
        """
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise MediaSecurityException(f"Unsupported URI scheme: {parsed.scheme}")

        if not parsed.hostname or cls.is_private_ip(parsed.hostname):
            raise MediaSecurityException(f"SSRF violation: Hostname {parsed.hostname} resolves to restricted IP")

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            # Stream response to check Content-Length and MIME type before reading full body
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if content_type not in cls.ALLOWED_MIMES:
                    raise MediaSecurityException(f"Prohibited MIME type: {content_type}")

                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > cls.MAX_BYTES:
                    raise MediaSecurityException(f"File size exceeds limit of {cls.MAX_BYTES} bytes")

                # Read body with chunked size guard
                downloaded_bytes = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    downloaded_bytes.extend(chunk)
                    if len(downloaded_bytes) > cls.MAX_BYTES:
                        raise MediaSecurityException("Download exceeded maximum allowed file size")

                return bytes(downloaded_bytes), content_type
