from django.db.models import Q
from django.http import JsonResponse

from .models import PurchaseOrder

CREATOR = "Creator"
APPROVER = "Approver"


def require_api_session(get_response):
    def middleware(request):
        if request.path_info.startswith("/api/") and not request.user.is_authenticated:
            return JsonResponse({"detail": "Sign in required."}, status=401)
        return get_response(request)

    return middleware


def roles_for(user):
    return set(user.groups.filter(name__in=[CREATOR, APPROVER]).values_list("name", flat=True))


def visible_orders(user, roles):
    scope = Q(pk__in=[])
    if CREATOR in roles:
        scope |= Q(creator=user)
    if APPROVER in roles:
        scope |= Q(status=PurchaseOrder.Status.SUBMITTED)
    return PurchaseOrder.objects.filter(scope).order_by("-pk")
