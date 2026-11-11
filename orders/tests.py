from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from catalog.models import Product

from .models import Order, OrderItem


class PublicCheckoutTests(TestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name="Checkout Test Product",
            description="A product used for checkout tests.",
            price=Decimal("250.00"),
            stock=5,
            is_available=True,
        )

    def set_cart_quantity(self, quantity):
        session = self.client.session

        session["cart"] = {
            str(self.product.id): quantity,
        }

        session.save()

    def test_checkout_redirects_to_message_ordering_without_creating_order(self):
        self.set_cart_quantity(2)

        response = self.client.post(
            reverse("checkout"),
        )

        self.assertRedirects(
            response,
            reverse("order_by_message"),
        )
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    def test_message_order_page_shows_both_contact_options(self):
        response = self.client.get(reverse("order_by_message"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order on WhatsApp")
        self.assertContains(response, "Order on Messenger")


class AdminDashboardTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )
        self.product = Product.objects.create(
            name="Order workflow product",
            description="Used for order administration tests.",
            price=Decimal("250.00"),
            stock=5,
            is_available=True,
        )
        Order.objects.create(
            customer_name="Pending Customer",
            phone_number="01700000000",
            delivery_address="Dhaka",
            total_amount=Decimal("250.00"),
        )
        Order.objects.create(
            customer_name="Confirmed Customer",
            phone_number="01700000001",
            delivery_address="Dhaka",
            total_amount=Decimal("500.00"),
            status=Order.Status.CONFIRMED,
            delivery_advance_status=Order.DeliveryAdvanceStatus.PAID,
        )
        self.confirmed_order = Order.objects.get(customer_name="Confirmed Customer")
        OrderItem.objects.create(
            order=self.confirmed_order,
            product=self.product,
            product_name=self.product.name,
            product_price=self.product.price,
            quantity=1,
        )

    def test_dashboard_shows_operational_order_counts(self):
        Product.objects.create(
            name="Dashboard product",
            description="Shown on the admin dashboard.",
            price=Decimal("100.00"),
            stock=5,
            is_available=True,
        )
        self.client.force_login(self.user)

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations dashboard")
        self.assertContains(response, "Recent pending orders")
        self.assertContains(response, "Dashboard product")
        self.assertContains(response, "Add product")
        self.assertContains(response, "View all products")
        self.assertEqual(
            response.context["dashboard_counts"]["pending_orders"],
            1,
        )
        self.assertEqual(
            response.context["dashboard_counts"]["confirmed_orders"],
            1,
        )
        self.assertEqual(
            response.context["dashboard_counts"]["delivery_advance_paid_orders"],
            1,
        )

    def test_admin_action_marks_an_order_as_delivered(self):
        self.client.force_login(self.user)
        order = self.confirmed_order
        order.stock_reserved = True
        order.courier_name = "Pathao"
        order.save(update_fields=("stock_reserved", "courier_name"))

        self.client.post(
            "/admin/orders/order/",
            {
                "action": "mark_as_shipped",
                "_selected_action": [order.pk],
            },
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)

        response = self.client.post(
            "/admin/orders/order/",
            {
                "action": "mark_as_delivered",
                "_selected_action": [order.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertIsNotNone(order.shipped_at)
        self.assertIsNotNone(order.delivered_at)
        self.assertEqual(order.status_history.count(), 2)

    def test_admin_can_create_a_pending_message_order_with_items(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("store_admin:orders_order_add"),
            {
                "customer_name": "Message Customer",
                "phone_number": "01700000002",
                "delivery_address": "Dhaka",
                "notes": "Please call first.",
                "status": Order.Status.PENDING,
                "payment_status": Order.PaymentStatus.UNPAID,
                "delivery_advance_status": Order.DeliveryAdvanceStatus.PENDING,
                "courier_name": "",
                "tracking_id": "",
                "courier_booking_date": "",
                "staff_note": "From WhatsApp",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": str(self.product.pk),
                "items-0-quantity": "2",
                "status_history-TOTAL_FORMS": "0",
                "status_history-INITIAL_FORMS": "0",
                "status_history-MIN_NUM_FORMS": "0",
                "status_history-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(customer_name="Message Customer")
        item = order.items.get()
        self.assertEqual(item.product_name, self.product.name)
        self.assertEqual(item.product_price, self.product.price)
        self.assertEqual(order.total_amount, Decimal("500.00"))
        self.assertEqual(order.status_history.count(), 1)

    def test_confirming_an_order_reserves_stock_and_cancelling_returns_it(self):
        self.client.force_login(self.user)
        order = Order.objects.get(customer_name="Pending Customer")
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            product_price=self.product.price,
            quantity=2,
        )

        self.client.post(
            reverse("store_admin:orders_order_changelist"),
            {
                "action": "mark_as_confirmed",
                "_selected_action": [order.pk],
            },
        )
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertTrue(order.stock_reserved)
        self.assertIsNotNone(order.confirmed_at)
        self.assertEqual(order.status_history.count(), 1)
        self.assertEqual(self.product.stock, 3)

        self.client.post(
            reverse("store_admin:orders_order_changelist"),
            {
                "action": "mark_as_cancelled",
                "_selected_action": [order.pk],
            },
        )
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertFalse(order.stock_reserved)
        self.assertIsNotNone(order.cancelled_at)
        self.assertEqual(order.status_history.count(), 2)
        self.assertEqual(self.product.stock, 5)

    def test_admin_rejects_duplicate_product_lines(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("store_admin:orders_order_add"),
            {
                "customer_name": "Duplicate Item Customer",
                "phone_number": "01700000003",
                "delivery_address": "Dhaka",
                "status": Order.Status.PENDING,
                "payment_status": Order.PaymentStatus.UNPAID,
                "delivery_advance_status": Order.DeliveryAdvanceStatus.PENDING,
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": str(self.product.pk),
                "items-0-quantity": "1",
                "items-1-product": str(self.product.pk),
                "items-1-quantity": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add each product only once")
        self.assertFalse(
            Order.objects.filter(customer_name="Duplicate Item Customer").exists()
        )

    def test_staff_role_groups_are_available(self):
        catalog_manager = Group.objects.get(name="Catalog managers")
        order_processor = Group.objects.get(name="Order processors")

        self.assertTrue(
            catalog_manager.permissions.filter(codename="change_product").exists()
        )
        self.assertTrue(
            order_processor.permissions.filter(codename="change_order").exists()
        )
        self.assertFalse(
            order_processor.permissions.filter(codename="delete_order").exists()
        )

    def test_admin_action_marks_delivery_advance_as_paid(self):
        self.client.force_login(self.user)
        order = Order.objects.get(customer_name="Pending Customer")

        response = self.client.post(
            "/admin/orders/order/",
            {
                "action": "mark_delivery_advance_paid",
                "_selected_action": [order.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(
            order.delivery_advance_status,
            Order.DeliveryAdvanceStatus.PAID,
        )
