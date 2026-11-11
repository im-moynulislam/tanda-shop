"""
Tests for the admin dashboard (the home page of /admin/ built in config/admin.py).

Run:  python manage.py test config.test_dashboard -v 2
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from config.admin import admin_site
from orders.models import Order
from config.test_orders import make_order, make_product

ADMIN = admin_site.name  # "store_admin"
Status = Order.Status


class DashboardTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_superuser("boss", "boss@example.com", "Test-pass-12345")
        self.client.force_login(staff)
        self.url = reverse(f"{ADMIN}:index")

    def set_state(self, order, **fields):
        Order.objects.filter(pk=order.pk).update(**fields)

    def test_dashboard_loads_with_an_empty_shop(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        counts = response.context["dashboard_counts"]
        self.assertTrue(all(value == 0 for value in counts.values()), counts)
        self.assertEqual(response.context["dashboard_totals"]["open_order_value"], 0)

    def test_counts_and_totals_match_the_real_orders(self):
        now = timezone.now()
        plenty = make_product("Plenty", price="100.00", stock=50)   # not low
        make_product("Sold Out", stock=0)                           # out of stock and low
        make_product("Nearly Out", stock=2)                         # low (threshold is 3)

        pending_a = make_order((plenty, 1))                          # 100
        make_order((plenty, 2))                                      # 200, pending
        confirmed_courier = make_order((plenty, 3), courier_name="Pathao")   # 300
        confirmed_no_courier = make_order((plenty, 4))               # 400
        shipped = make_order((plenty, 5))                            # 500
        delivered = make_order((plenty, 6))                          # 600
        cancelled = make_order((plenty, 7))                          # 700 (not counted as open)

        self.set_state(confirmed_courier, status=Status.CONFIRMED, confirmed_at=now)
        self.set_state(confirmed_no_courier, status=Status.CONFIRMED, confirmed_at=now)
        self.set_state(shipped, status=Status.SHIPPED, shipped_at=now)
        self.set_state(
            delivered,
            status=Status.DELIVERED,
            delivered_at=now,
            payment_status=Order.PaymentStatus.PAID,
        )
        self.set_state(cancelled, status=Status.CANCELLED, cancelled_at=now)
        self.set_state(pending_a, delivery_advance_status=Order.DeliveryAdvanceStatus.PAID)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        counts = response.context["dashboard_counts"]
        self.assertEqual(counts["pending_orders"], 2)
        self.assertEqual(counts["confirmed_orders"], 2)
        self.assertEqual(counts["confirmed_without_courier"], 1)
        self.assertEqual(counts["ready_to_dispatch"], 1)
        self.assertEqual(counts["shipped_orders"], 1)
        self.assertEqual(counts["delivered_today"], 1)
        self.assertEqual(counts["cancelled_this_week"], 1)
        self.assertEqual(counts["unpaid_orders"], 6)
        self.assertEqual(counts["delivery_advance_paid_orders"], 1)
        self.assertEqual(counts["out_of_stock_products"], 1)
        self.assertEqual(counts["low_stock_products"], 2)

        totals = response.context["dashboard_totals"]
        self.assertEqual(totals["open_order_value"], Decimal("2100.00"))
        self.assertEqual(totals["delivered_value_this_week"], Decimal("600.00"))

    def test_old_delivered_orders_do_not_count_as_delivered_today(self):
        order = make_order((make_product(), 1))
        long_ago = timezone.now() - timedelta(days=30)
        self.set_state(order, status=Status.DELIVERED, delivered_at=long_ago)
        counts = self.client.get(self.url).context["dashboard_counts"]
        self.assertEqual(counts["delivered_today"], 0)
        totals = self.client.get(self.url).context["dashboard_totals"]
        self.assertEqual(totals["delivered_value_this_week"], 0)

    def test_pending_list_shows_at_most_five_orders(self):
        product = make_product(stock=50)
        for _ in range(7):
            make_order((product, 1))
        response = self.client.get(self.url)
        self.assertEqual(len(list(response.context["recent_pending_orders"])), 5)

    def test_low_stock_list_shows_the_emptiest_products_first(self):
        make_product("Two Left", stock=2)
        make_product("None Left", stock=0)
        make_product("Plenty", stock=50)
        response = self.client.get(self.url)
        names = [product.name for product in response.context["low_stock_products"]]
        self.assertEqual(names, ["None Left", "Two Left"])
