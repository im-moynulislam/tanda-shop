
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("order-by-message/", views.order_by_message, name="order_by_message"),
    path("return-exchange-policy/", views.return_exchange_policy, name="return_exchange_policy"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    
    # Cart URLs
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/update/<int:product_id>/", views.update_cart, name="update_cart"),
    path("cart/remove/<int:product_id>/", views.remove_from_cart, name="remove_from_cart"),
]
