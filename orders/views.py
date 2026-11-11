from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from .models import Order, OrderItem



def checkout(request):
    messages.info(
        request,
        "Online checkout is unavailable. Please contact us to place your order."
    )
    return redirect("order_by_message")

def order_success(request, order_id):
    if request.session.get("last_order_id") != order_id:
        return redirect("home")

    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        id=order_id
    )

    return render(
        request,
        "orders/order_success.html",
        {"order": order}
    )
