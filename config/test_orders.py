"""
Tests for orders: totals, status flow, stock handling, checkout form, order pages.

Run:  python manage.py test config.test_orders -v 2

Note: these tests run on SQLite, which cannot truly test two staff members
confirming the same last unit at the very same moment. The "last unit" tests
below check the same rule one after the other.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from catalog.models import Product

from orders.forms import CheckoutForm
from orders.models import Order, OrderItem, OrderStatusHistory

Status = Order.Status


def make_product(name="Cotton Shirt", price="500.00", stock=10):
    return Product.objects.create(
        name=name, description="Test product", price=Decimal(price), stock=stock
    )


def make_order(*lines, **extra):
    """make_order((product, quantity), (product2, quantity2), ...)"""
    details = {
        "customer_name": "Test Customer",
        "phone_number": "01700000000",
        "delivery_address": "House 1, Road 2, Dhaka",
    }
    details.update(extra)
    order = Order.objects.create(**details)
    for product, quantity in lines:
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            product_price=product.price,
            quantity=quantity,
        )
    order.recalculate_total()
    return order


def change_status(order, new_status, user=None):
    """Do what staff do: save the new status, then record the change."""
    previous = order.status
    order.status = new_status
    order.save()
    order.record_status_change(previous, changed_by=user)
    order.refresh_from_db()


class OrderTotalTests(TestCase):
    def test_new_order_defaults(self):
        order = make_order()
        self.assertEqual(order.status, Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)
        self.assertEqual(order.delivery_advance_status, Order.DeliveryAdvanceStatus.PENDING)
        self.assertFalse(order.stock_reserved)
        self.assertEqual(order.total_amount, Decimal("0.00"))

    def test_total_is_the_sum_of_all_lines(self):
        shirt = make_product("Shirt", price="500.00")
        bag = make_product("Bag", price="250.50")
        order = make_order((shirt, 2), (bag, 1))
        self.assertEqual(order.total_amount, Decimal("1250.50"))

    def test_line_total_is_price_times_quantity(self):
        order = make_order((make_product(price="199.99"), 3))
        self.assertEqual(order.items.get().line_total, Decimal("599.97"))

    def test_order_keeps_the_price_from_when_it_was_placed(self):
        product = make_product(price="500.00")
        order = make_order((product, 2))
        product.price = Decimal("999.00")
        product.save()
        order.recalculate_total()
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("1000.00"))

    def test_str_shows_order_number_and_customer(self):
        order = make_order()
        self.assertEqual(str(order), f"Order #{order.id} - Test Customer")
        item = OrderItem(product_name="Shirt", quantity=2)
        self.assertEqual(str(item), "Shirt x 2")


class StatusRulesTests(TestCase):
    def test_every_status_has_a_next_step_rule(self):
        for status in Status:
            Order.allowed_next_statuses(status)

    def test_allowed_next_steps(self):
        expected = {
            Status.PENDING: {Status.CONFIRMED, Status.CANCELLED},
            Status.CONFIRMED: {Status.SHIPPED, Status.CANCELLED},
            Status.SHIPPED: {Status.DELIVERED, Status.CANCELLED},
            Status.DELIVERED: set(),
            Status.CANCELLED: set(),
        }
        for status, allowed in expected.items():
            with self.subTest(status=status):
                self.assertEqual(Order.allowed_next_statuses(status), allowed)

    def test_cannot_skip_steps_or_go_backwards(self):
        self.assertNotIn(Status.DELIVERED, Order.allowed_next_statuses(Status.PENDING))
        self.assertNotIn(Status.SHIPPED, Order.allowed_next_statuses(Status.PENDING))
        self.assertNotIn(Status.PENDING, Order.allowed_next_statuses(Status.CONFIRMED))

    def test_finished_orders_cannot_change_again(self):
        self.assertEqual(Order.allowed_next_statuses(Status.DELIVERED), set())
        self.assertEqual(Order.allowed_next_statuses(Status.CANCELLED), set())


class StockTests(TestCase):
    def setUp(self):
        self.product = make_product(stock=10)

    def stock(self):
        self.product.refresh_from_db()
        return self.product.stock

    def test_confirming_an_order_takes_the_stock(self):
        order = make_order((self.product, 3))
        change_status(order, Status.CONFIRMED)
        self.assertEqual(self.stock(), 7)
        self.assertTrue(order.stock_reserved)
        self.assertIsNotNone(order.confirmed_at)

    def test_pending_order_does_not_touch_stock(self):
        make_order((self.product, 3))
        self.assertEqual(self.stock(), 10)

    def test_same_product_on_two_lines_is_counted_together(self):
        order = make_order((self.product, 2), (self.product, 3))
        change_status(order, Status.CONFIRMED)
        self.assertEqual(self.stock(), 5)

    def test_several_products_are_each_reduced(self):
        bag = make_product("Bag", stock=4)
        order = make_order((self.product, 1), (bag, 4))
        change_status(order, Status.CONFIRMED)
        bag.refresh_from_db()
        self.assertEqual(self.stock(), 9)
        self.assertEqual(bag.stock, 0)

    def test_order_for_exactly_the_stock_is_allowed(self):
        order = make_order((self.product, 10))
        change_status(order, Status.CONFIRMED)
        self.assertEqual(self.stock(), 0)

    def test_not_enough_stock_blocks_confirmation_and_changes_nothing(self):
        product = make_product("Low", stock=2)
        order = make_order((product, 5))
        with self.assertRaises(ValidationError), transaction.atomic():
            change_status(order, Status.CONFIRMED)
        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 2)
        self.assertFalse(order.stock_reserved)
        self.assertEqual(order.status, Status.PENDING)
        self.assertEqual(OrderStatusHistory.objects.count(), 0)

    def test_second_order_for_the_last_unit_is_blocked(self):
        product = make_product("Last One", stock=1)
        first = make_order((product, 1))
        second = make_order((product, 1))
        change_status(first, Status.CONFIRMED)
        with self.assertRaises(ValidationError), transaction.atomic():
            change_status(second, Status.CONFIRMED)
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)

    def test_order_with_no_items_cannot_be_confirmed(self):
        order = make_order()
        with self.assertRaises(ValidationError) as caught, transaction.atomic():
            change_status(order, Status.CONFIRMED)
        self.assertIn("must contain an item", str(caught.exception))

    def test_stock_is_not_taken_twice_for_the_same_order(self):
        order = make_order((self.product, 3))
        change_status(order, Status.CONFIRMED)
        order.sync_stock_for_status()
        order.sync_stock_for_status()
        self.assertEqual(self.stock(), 7)

    def test_cancelling_a_confirmed_order_gives_the_stock_back(self):
        order = make_order((self.product, 3))
        change_status(order, Status.CONFIRMED)
        change_status(order, Status.CANCELLED)
        self.assertEqual(self.stock(), 10)
        self.assertFalse(order.stock_reserved)
        self.assertIsNotNone(order.cancelled_at)

    def test_stock_is_not_given_back_twice(self):
        order = make_order((self.product, 3))
        change_status(order, Status.CONFIRMED)
        change_status(order, Status.CANCELLED)
        order.sync_stock_for_status()
        self.assertEqual(self.stock(), 10)

    def test_cancelling_a_pending_order_does_not_add_stock(self):
        order = make_order((self.product, 3))
        change_status(order, Status.CANCELLED)
        self.assertEqual(self.stock(), 10)

    def test_shipping_and_delivery_keep_the_stock_taken(self):
        order = make_order((self.product, 3))
        for status in (Status.CONFIRMED, Status.SHIPPED, Status.DELIVERED):
            change_status(order, status)
        self.assertEqual(self.stock(), 7)
        self.assertIsNotNone(order.confirmed_at)
        self.assertIsNotNone(order.shipped_at)
        self.assertIsNotNone(order.delivered_at)

    def test_cancelled_order_can_free_the_last_unit_for_another_order(self):
        product = make_product("Last One", stock=1)
        first = make_order((product, 1))
        second = make_order((product, 1))
        change_status(first, Status.CONFIRMED)
        change_status(first, Status.CANCELLED)
        change_status(second, Status.CONFIRMED)
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)


class StatusHistoryTests(TestCase):
    def test_each_change_is_recorded_with_who_made_it(self):
        user = get_user_model().objects.create_user(username="staff_test", password="Test-pass-12345")
        order = make_order((make_product(), 1))
        change_status(order, Status.CONFIRMED, user=user)
        change_status(order, Status.SHIPPED, user=user)
        steps = {(h.previous_status, h.new_status) for h in order.status_history.all()}
        self.assertEqual(steps, {("pending", "confirmed"), ("confirmed", "shipped")})
        self.assertTrue(all(h.changed_by == user for h in order.status_history.all()))

    def test_saving_with_the_same_status_records_nothing(self):
        order = make_order((make_product(), 1))
        order.record_status_change(Status.PENDING)
        self.assertEqual(order.status_history.count(), 0)

    def test_history_survives_when_the_staff_user_is_deleted(self):
        user = get_user_model().objects.create_user(username="temp_staff", password="Test-pass-12345")
        order = make_order((make_product(), 1))
        change_status(order, Status.CONFIRMED, user=user)
        user.delete()
        entry = order.status_history.get()
        self.assertIsNone(entry.changed_by)


class DeletionRulesTests(TestCase):
    def test_product_that_was_ordered_cannot_be_deleted(self):
        product = make_product()
        make_order((product, 1))
        with self.assertRaises(ProtectedError):
            product.delete()

    def test_deleting_an_order_deletes_its_items_and_history(self):
        order = make_order((make_product(), 1))
        change_status(order, Status.CONFIRMED)
        order.delete()
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(OrderStatusHistory.objects.count(), 0)


class CheckoutFormTests(TestCase):
    valid = {
        "customer_name": "Rahim Uddin",
        "phone_number": "01712345678",
        "delivery_address": "House 5, Road 3, Mirpur, Dhaka",
        "notes": "",
    }

    def test_valid_form_saves_a_pending_unpaid_order(self):
        form = CheckoutForm(self.valid)
        self.assertTrue(form.is_valid(), form.errors)
        order = form.save()
        self.assertEqual(order.status, Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)

    def test_notes_are_optional(self):
        data = {k: v for k, v in self.valid.items() if k != "notes"}
        self.assertTrue(CheckoutForm(data).is_valid())

    def test_name_phone_and_address_are_required(self):
        for field in ("customer_name", "phone_number", "delivery_address"):
            with self.subTest(field=field):
                data = {**self.valid, field: ""}
                form = CheckoutForm(data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_overlong_phone_number_is_rejected(self):
        form = CheckoutForm({**self.valid, "phone_number": "0" * 21})
        self.assertFalse(form.is_valid())

    def test_customer_cannot_set_status_or_payment_through_the_form(self):
        data = {**self.valid, "status": "delivered", "payment_status": "paid", "total_amount": "1"}
        order = CheckoutForm(data).save()
        self.assertEqual(order.status, Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)
        self.assertEqual(order.total_amount, Decimal("0.00"))


class CheckoutViewTests(TestCase):
    def test_checkout_page_sends_visitors_to_order_by_message(self):
        response = self.client.get(reverse("checkout"))
        self.assertRedirects(response, reverse("order_by_message"))

    def test_posting_to_checkout_does_not_create_an_order(self):
        response = self.client.post(
            reverse("checkout"),
            {
                "customer_name": "Hacker",
                "phone_number": "01700000000",
                "delivery_address": "Anywhere",
            },
        )
        self.assertRedirects(response, reverse("order_by_message"))
        self.assertEqual(Order.objects.count(), 0)


class OrderSuccessPageTests(TestCase):
    def setUp(self):
        self.order = make_order((make_product(), 1))

    def remember(self, order_id):
        session = self.client.session
        session["last_order_id"] = order_id
        session.save()

    def test_visitor_without_a_recent_order_is_sent_home(self):
        response = self.client.get(reverse("order_success", args=[self.order.id]))
        self.assertRedirects(response, reverse("home"))

    def test_visitor_cannot_open_someone_elses_order(self):
        other = make_order((make_product("Other"), 1))
        self.remember(other.id)
        response = self.client.get(reverse("order_success", args=[self.order.id]))
        self.assertRedirects(response, reverse("home"))

    def test_visitor_sees_their_own_order(self):
        self.remember(self.order.id)
        response = self.client.get(reverse("order_success", args=[self.order.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["order"], self.order)

    def test_order_number_that_does_not_exist_gives_404(self):
        self.remember(999999)
        response = self.client.get(reverse("order_success", args=[999999]))
        self.assertEqual(response.status_code, 404)
