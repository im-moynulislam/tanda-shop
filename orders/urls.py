from django.urls import path

from . import views


urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path(
        "order-success/<int:order_id>/",
        views.order_success,
        name="order_success"
    ),
]