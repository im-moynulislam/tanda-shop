"""
Tests for the staff side of orders (orders/admin.py): status buttons, the add and
edit forms, stock locking, and the order list.

Run:  python manage.py test config.test_orders_admin -v 2

One test here, test_zero_quantity_line_is_blocked, is EXPECTED TO FAIL until
OrderItemForm.clean in orders/admin.py rejects a quantity of 0.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Product
from config.admin import admin_site

from orders.models import Order
from config.test_orders import change_status, make_order, make_product

ADMIN = admin_site.name  # "store_admin"
Status = Order.Status


def form_data(order=None, new_items=(), **overrides):
    """Build the data the admin order form sends when staff press Save."""
    data = {
        "customer_name": "Rahim Uddin",
        "phone_number": "01712345678",
        "delivery_address": "House 5, Road 3, Dhaka",
        "notes": "",
        "status": "pending",
        "payment_status": "unpaid",
        "delivery_advance_status": "pending",
        "courier_name": "",
        "tracking_id": "",
        "courier_booking_date": "",
        "staff_note": "",
    }
    existing = list(order.items.all()) if order else []
    history = list(order.status_history.all()) if order else []
    if order:
        data.update(
            customer_name=order.customer_name,
            phone_number=order.phone_number,
            delivery_address=order.delivery_address,
            notes=order.notes,
            status=str(order.status),
            payment_status=str(order.payment_status),
            delivery_advance_status=str(order.delivery_advance_status),
            courier_name=order.courier_name,
            tracking_id=order.tracking_id,
            staff_note=order.staff_note,
        )
    data.update(
        {
            "items-TOTAL_FORMS": str(len(existing) + len(new_items)),
            "items-INITIAL_FORMS": str(len(existing)),
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "status_history-TOTAL_FORMS": str(len(history)),
            "status_history-INITIAL_FORMS": str(len(history)),
            "status_history-MIN_NUM_FORMS": "0",
            "status_history-MAX_NUM_FORMS": "0",
        }
    )
    for i, item in enumerate(existing):
        data[f"items-{i}-id"] = str(item.pk)
        data[f"items-{i}-order"] = str(order.pk)
        data[f"items-{i}-product"] = str(item.product_id)
        data[f"items-{i}-quantity"] = str(item.quantity)
    for j, (product, quantity) in enumerate(new_items, start=len(existing)):
        data[f"items-{j}-product"] = str(product.pk)
        data[f"items-{j}-quantity"] = str(quantity)
    for i, entry in enumerate(history):
        data[f"status_history-{i}-id"] = str(entry.pk)
        data[f"status_history-{i}-order"] = str(order.pk)
    data.update(overrides)
    return data


class AdminTestCase(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_superuser(
            "boss", "boss@example.com", "Test-pass-12345"
        )
        self.client.force_login(self.staff)
        self.changelist = reverse(f"{ADMIN}:orders_order_changelist")
        self.add_url = reverse(f"{ADMIN}:orders_order_add")

    def change_url(self, order):
        return reverse(f"{ADMIN}:orders_order_change", args=[order.pk])

    def messages(self, response):
        return [str(message) for message in response.context["messages"]]

    def run_action(self, action, *orders):
        return self.client.post(
            self.changelist,
            {"action": action, "_selected_action": [str(o.pk) for o in orders]},
            follow=True,
        )


class OrderActionTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(stock=10)

    def stock(self):
        self.product.refresh_from_db()
        return self.product.stock

    def confirmed_order(self, qty=2, **extra):
        order = make_order((self.product, qty), **extra)
        change_status(order, Status.CONFIRMED)
        return order

    def test_confirm_reserves_stock_and_records_who_did_it(self):
        order = make_order((self.product, 3))
        response = self.run_action("mark_as_confirmed", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CONFIRMED)
        self.assertTrue(order.stock_reserved)
        self.assertEqual(self.stock(), 7)
        entry = order.status_history.get()
        self.assertEqual((entry.previous_status, entry.new_status), ("pending", "confirmed"))
        self.assertEqual(entry.changed_by, self.staff)
        self.assertIn("1 order(s) marked as confirmed.", self.messages(response))

    def test_confirm_with_too_little_stock_changes_nothing(self):
        order = make_order((self.product, 5))
        Product.objects.filter(pk=self.product.pk).update(stock=2)
        response = self.run_action("mark_as_confirmed", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.PENDING)
        self.assertFalse(order.stock_reserved)
        self.assertEqual(self.stock(), 2)
        self.assertEqual(order.status_history.count(), 0)
        self.assertTrue(any("Only 2 unit(s)" in m for m in self.messages(response)))

    def test_two_orders_for_the_last_unit_confirm_only_one(self):
        last = make_product("Last One", stock=1)
        first = make_order((last, 1))
        second = make_order((last, 1))
        response = self.run_action("mark_as_confirmed", first, second)
        statuses = sorted(Order.objects.values_list("status", flat=True))
        self.assertEqual(statuses, ["confirmed", "pending"])
        last.refresh_from_db()
        self.assertEqual(last.stock, 0)
        messages = self.messages(response)
        self.assertIn("1 order(s) marked as confirmed.", messages)
        self.assertEqual(sum("Only 0 unit(s)" in m for m in messages), 1)

    def test_ship_needs_a_courier_name(self):
        order = self.confirmed_order()
        response = self.run_action("mark_as_shipped", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CONFIRMED)
        self.assertTrue(any("courier" in m.lower() for m in self.messages(response)))

    def test_ship_works_with_a_courier(self):
        order = self.confirmed_order(courier_name="Pathao")
        self.run_action("mark_as_shipped", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.SHIPPED)
        self.assertIsNotNone(order.shipped_at)

    def test_pending_order_cannot_be_shipped_or_delivered(self):
        for action in ("mark_as_shipped", "mark_as_delivered"):
            with self.subTest(action=action):
                order = make_order((self.product, 1), courier_name="Pathao")
                response = self.run_action(action, order)
                order.refresh_from_db()
                self.assertEqual(order.status, Status.PENDING)
                self.assertTrue(any("Confirm an order before" in m for m in self.messages(response)))

    def test_confirmed_order_cannot_jump_straight_to_delivered(self):
        order = self.confirmed_order()
        response = self.run_action("mark_as_delivered", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CONFIRMED)
        self.assertTrue(any("Cannot move from Confirmed to Delivered" in m for m in self.messages(response)))

    def test_full_journey_keeps_the_stock_taken(self):
        order = self.confirmed_order(qty=2, courier_name="Pathao")
        self.run_action("mark_as_shipped", order)
        self.run_action("mark_as_delivered", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.DELIVERED)
        self.assertIsNotNone(order.delivered_at)
        self.assertEqual(self.stock(), 8)
        self.assertEqual(order.status_history.count(), 3)

    def test_cancel_returns_the_stock(self):
        order = self.confirmed_order(qty=4)
        self.assertEqual(self.stock(), 6)
        self.run_action("mark_as_cancelled", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CANCELLED)
        self.assertFalse(order.stock_reserved)
        self.assertEqual(self.stock(), 10)

    def test_cancelling_a_pending_order_does_not_change_stock(self):
        order = make_order((self.product, 4))
        self.run_action("mark_as_cancelled", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CANCELLED)
        self.assertEqual(self.stock(), 10)

    def test_delivered_order_cannot_be_cancelled(self):
        order = make_order((self.product, 1))
        Order.objects.filter(pk=order.pk).update(status=Status.DELIVERED)
        response = self.run_action("mark_as_cancelled", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.DELIVERED)
        self.assertTrue(any("Cannot move from Delivered to Cancelled" in m for m in self.messages(response)))

    def test_cancelled_order_cannot_be_confirmed_again(self):
        order = make_order((self.product, 1))
        Order.objects.filter(pk=order.pk).update(status=Status.CANCELLED)
        response = self.run_action("mark_as_confirmed", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CANCELLED)
        self.assertEqual(self.stock(), 10)
        self.assertTrue(any("Cannot move from Cancelled to Confirmed" in m for m in self.messages(response)))

    def test_delivery_advance_action_marks_every_selected_order(self):
        first = make_order((self.product, 1))
        second = make_order((self.product, 1))
        untouched = make_order((self.product, 1))
        self.run_action("mark_delivery_advance_paid", first, second)
        paid = Order.DeliveryAdvanceStatus.PAID
        first.refresh_from_db()
        second.refresh_from_db()
        untouched.refresh_from_db()
        self.assertEqual(first.delivery_advance_status, paid)
        self.assertEqual(second.delivery_advance_status, paid)
        self.assertNotEqual(untouched.delivery_advance_status, paid)


class OrderListPageTests(AdminTestCase):
    def test_list_shows_orders_in_every_status(self):
        for status in Status:
            Order.objects.create(
                customer_name=f"Customer {status.value}",
                phone_number="01700000000",
                delivery_address="Somewhere",
                status=status,
            )
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cl"].result_count, 5)

    def test_search_by_customer_name_and_by_phone(self):
        make_order(customer_name="Rahim Uddin", phone_number="01711111111", tracking_id="TRK-1")
        make_order(customer_name="Karim Ali", phone_number="01822222222")
        for term in ("Rahim", "0171111", "TRK-1"):
            with self.subTest(term=term):
                response = self.client.get(self.changelist, {"q": term})
                self.assertEqual(response.context["cl"].result_count, 1)

    def test_status_filter(self):
        make_order()
        confirmed = make_order()
        Order.objects.filter(pk=confirmed.pk).update(status=Status.CONFIRMED)
        response = self.client.get(self.changelist, {"status__exact": "confirmed"})
        self.assertEqual(response.context["cl"].result_count, 1)

    def test_phone_becomes_a_whatsapp_link_with_the_country_code(self):
        order = make_order(phone_number="01712345678")
        html = str(admin_site._registry[Order].customer_phone(order))
        self.assertIn("https://wa.me/8801712345678", html)

    def test_phone_text_is_escaped(self):
        order = make_order(phone_number="<b>1</b>")
        html = str(admin_site._registry[Order].customer_phone(order))
        self.assertNotIn("<b>1</b>", html)
        self.assertIn("&lt;b&gt;", html)

    def test_add_page_and_change_pages_load(self):
        product = make_product()
        pending = make_order((product, 1))
        confirmed = make_order((product, 1))
        change_status(confirmed, Status.CONFIRMED)
        self.assertEqual(self.client.get(self.add_url).status_code, 200)
        self.assertEqual(self.client.get(self.change_url(pending)).status_code, 200)
        self.assertEqual(self.client.get(self.change_url(confirmed)).status_code, 200)


class OrderFormTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product("Cotton Shirt", price="500.00", stock=10)

    def stock(self):
        self.product.refresh_from_db()
        return self.product.stock

    # ---- creating an order -------------------------------------------------

    def test_staff_can_create_a_pending_order_with_items(self):
        bag = make_product("Leather Bag", price="250.00", stock=4)
        response = self.client.post(
            self.add_url, form_data(new_items=[(self.product, 2), (bag, 1)])
        )
        self.assertRedirects(response, self.changelist)
        order = Order.objects.get()
        self.assertEqual(order.status, Status.PENDING)
        self.assertEqual(order.total_amount, Decimal("1250.00"))
        snapshot = {i.product_name: i.product_price for i in order.items.all()}
        self.assertEqual(snapshot, {"Cotton Shirt": Decimal("500.00"), "Leather Bag": Decimal("250.00")})
        self.assertEqual(self.stock(), 10)
        entry = order.status_history.get()
        self.assertEqual((entry.previous_status, entry.new_status), ("", "pending"))

    def test_new_order_must_start_as_pending(self):
        response = self.client.post(
            self.add_url, form_data(new_items=[(self.product, 1)], status="confirmed")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.context["adminform"].form.errors)
        self.assertEqual(Order.objects.count(), 0)

    def test_order_needs_at_least_one_item(self):
        response = self.client.post(self.add_url, form_data(new_items=[]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_quantity_above_stock_is_blocked(self):
        response = self.client.post(self.add_url, form_data(new_items=[(self.product, 11)]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_unavailable_product_is_blocked(self):
        hidden = make_product("Hidden", stock=5)
        Product.objects.filter(pk=hidden.pk).update(is_available=False)
        response = self.client.post(self.add_url, form_data(new_items=[(hidden, 1)]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_same_product_twice_is_blocked(self):
        response = self.client.post(
            self.add_url, form_data(new_items=[(self.product, 1), (self.product, 2)])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_zero_quantity_line_is_blocked(self):
        # EXPECTED TO FAIL until OrderItemForm.clean rejects quantity 0.
        response = self.client.post(self.add_url, form_data(new_items=[(self.product, 0)]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    # ---- editing an order --------------------------------------------------

    def test_staff_can_confirm_an_order_from_the_edit_page(self):
        order = make_order((self.product, 3))
        response = self.client.post(self.change_url(order), form_data(order, status="confirmed"))
        self.assertRedirects(response, self.changelist)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CONFIRMED)
        self.assertTrue(order.stock_reserved)
        self.assertEqual(self.stock(), 7)
        entry = order.status_history.get()
        self.assertEqual((entry.previous_status, entry.new_status), ("pending", "confirmed"))
        self.assertEqual(entry.changed_by, self.staff)

    def test_editing_other_details_changes_no_stock_and_no_history(self):
        order = make_order((self.product, 3))
        response = self.client.post(self.change_url(order), form_data(order, customer_name="New Name"))
        self.assertRedirects(response, self.changelist)
        order.refresh_from_db()
        self.assertEqual(order.customer_name, "New Name")
        self.assertEqual(self.stock(), 10)
        self.assertEqual(order.status_history.count(), 0)

    def test_confirming_with_too_little_stock_is_refused(self):
        order = make_order((self.product, 5))
        Product.objects.filter(pk=self.product.pk).update(stock=2)
        response = self.client.post(self.change_url(order), form_data(order, status="confirmed"))
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.PENDING)
        self.assertFalse(order.stock_reserved)
        self.assertEqual(self.stock(), 2)

    def test_pending_order_cannot_skip_to_delivered(self):
        order = make_order((self.product, 1))
        response = self.client.post(self.change_url(order), form_data(order, status="delivered"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.context["adminform"].form.errors)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.PENDING)

    def test_shipping_needs_a_courier(self):
        order = make_order((self.product, 1))
        change_status(order, Status.CONFIRMED)
        response = self.client.post(self.change_url(order), form_data(order, status="shipped"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("courier_name", response.context["adminform"].form.errors)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CONFIRMED)

    def test_shipping_with_a_courier_works(self):
        order = make_order((self.product, 1))
        change_status(order, Status.CONFIRMED)
        response = self.client.post(
            self.change_url(order), form_data(order, status="shipped", courier_name="Pathao")
        )
        self.assertRedirects(response, self.changelist)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.SHIPPED)
        self.assertIsNotNone(order.shipped_at)
        self.assertEqual(order.status_history.count(), 2)

    def test_stock_reserved_order_cannot_go_back_to_pending(self):
        order = make_order((self.product, 2))
        change_status(order, Status.CONFIRMED)
        response = self.client.post(self.change_url(order), form_data(order, status="pending"))
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.CONFIRMED)
        self.assertEqual(self.stock(), 8)

    def test_items_of_a_confirmed_order_are_locked(self):
        order = make_order((self.product, 3))
        change_status(order, Status.CONFIRMED)
        data = form_data(order)
        data["items-0-quantity"] = "9"
        data["items-0-DELETE"] = "on"
        self.client.post(self.change_url(order), data)
        item = order.items.get()
        self.assertEqual(item.quantity, 3)
        self.assertEqual(self.stock(), 7)
