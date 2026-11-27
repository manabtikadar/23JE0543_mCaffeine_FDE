import logging

from django.db import DatabaseError, InterfaceError, connection
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@require_safe
def home(request):
    return HttpResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Purchase orders</title><main><h1>PEP Brands purchase orders</h1>'
        '<p><a href="/health">Check database connection</a></p></main></html>'
    )


@require_safe
@never_cache
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except (DatabaseError, InterfaceError) as error:
        # Driver messages can contain connection details. Log only the error class.
        logger.error("Database health check failed (%s)", type(error).__name__)
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
