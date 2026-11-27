from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView

from orders import views as orders
from orders import drafts

from . import views

urlpatterns = [
    path("pos/<int:pk>/", drafts.detail, name="draft-detail"),
    path("pos/<int:pk>/original/", drafts.original, name="original"),
    path("", orders.workspace, name="workspace"),
    path("health", views.health),
    path("login/", LoginView.as_view(template_name="orders/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("api/pos/", orders.order_list, name="order-list"),
    path("api/pos/<int:pk>/", orders.order_detail, name="order-detail"),
    path("api/approval-queue/", orders.approval_queue, name="approval-queue"),
]
