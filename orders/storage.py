import json
import logging
import os
from urllib.error import URLError
from urllib.request import Request, urlopen


class StorageUnavailable(Exception):
    pass


def storage_request(path, method="GET", data=None, content_type="application/json"):
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url.startswith("https://") or not secret:
        raise StorageUnavailable("Private storage is not configured.")
    req = Request(url + "/storage/v1/" + path, method=method, data=data, headers={
        "apikey": secret, "Authorization": "Bearer " + secret, "Content-Type": content_type,
    })
    try:
        with urlopen(req, timeout=12) as result:
            return result.read()
    except (URLError, TimeoutError, OSError) as exc:
        logging.getLogger(__name__).warning("Storage %s failed (%s)", method, getattr(exc, "code", type(exc).__name__))
        raise StorageUnavailable("Private storage is temporarily unavailable.") from None


def check_bucket():
    if json.loads(storage_request("bucket/po-originals")).get("public") is not False:
        raise StorageUnavailable("Originals require a private bucket.")


def delete_original(key):
    storage_request("object/po-originals", "DELETE", json.dumps({"prefixes": [key]}).encode())
