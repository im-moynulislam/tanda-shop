from datetime import timedelta

from django.contrib.admin import AdminSite
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import F, Sum
from django.utils import timezone


class StoreAdminSite(AdminSite):
    """Admin home page with the small set of operational queues staff need."""

    site_header = "Store administration"
    site_title = "Store administration"
    index_title = "Operations dashboard"
    index_template = "admin/index.html"

    def index(self, request, extra_context=None):
        from catalog.models import Product
        from orders.models import Order

        extra_context = extra_context or {}
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        pending_orders = Order.objects.filter(status=Order.Status.PENDING)
        confirmed_orders = Order.objects.filter(
            status=Order.Status.CONFIRMED
        )
        unpaid_orders = Order.objects.filter(
            payment_status=Order.PaymentStatus.UNPAID
        )
        delivery_advance_paid_orders = Order.objects.filter(
            delivery_advance_status=Order.DeliveryAdvanceStatus.PAID
        )
        shipped_orders = Order.objects.filter(status=Order.Status.SHIPPED)
        delivered_this_week = Order.objects.filter(
            status=Order.Status.DELIVERED,
            delivered_at__date__gte=week_start,
        )
        cancelled_this_week = Order.objects.filter(
            status=Order.Status.CANCELLED,
            cancelled_at__date__gte=week_start,
        )
        low_stock_products = Product.objects.filter(
            stock__lte=F("low_stock_threshold")
        )

        def total_value(queryset):
            return queryset.aggregate(total=Sum("total_amount"))["total"] or 0

        extra_context.update(
            {
                "dashboard_counts": {
                    "pending_orders": pending_orders.count(),
                    "confirmed_orders": confirmed_orders.count(),
                    "unpaid_orders": unpaid_orders.count(),
                    "delivery_advance_paid_orders": (
                        delivery_advance_paid_orders.count()
                    ),
                    "out_of_stock_products": Product.objects.filter(
                        stock=0
                    ).count(),
                    "confirmed_without_courier": confirmed_orders.filter(
                        courier_name=""
                    ).count(),
                    "ready_to_dispatch": confirmed_orders.exclude(
                        courier_name=""
                    ).count(),
                    "shipped_orders": shipped_orders.count(),
                    "low_stock_products": low_stock_products.count(),
                    "delivered_today": Order.objects.filter(
                        status=Order.Status.DELIVERED,
                        delivered_at__date=today,
                    ).count(),
                    "cancelled_this_week": cancelled_this_week.count(),
                },
                "dashboard_totals": {
                    "open_order_value": total_value(
                        Order.objects.exclude(status=Order.Status.CANCELLED)
                    ),
                    "delivered_value_this_week": total_value(delivered_this_week),
                },
                "recent_pending_orders": pending_orders.order_by(
                    "-created_at"
                )[:5],
                "ready_to_dispatch_orders": confirmed_orders.exclude(
                    courier_name=""
                ).order_by("-confirmed_at")[:5],
                "recent_delivered_orders": delivered_this_week.order_by(
                    "-delivered_at"
                )[:5],
                "low_stock_products": low_stock_products.select_related(
                    "category"
                ).order_by("stock", "name")[:8],
                "recent_products": Product.objects.select_related(
                    "category"
                ).order_by("-created_at")[:8],
            }
        )

        return super().index(request, extra_context=extra_context)


admin_site = StoreAdminSite(name="store_admin")
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)
