from decimal import Decimal

from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from catalog.models import Product


class Order(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PAID = "paid", "Paid"

    class DeliveryAdvanceStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"

    customer_name = models.CharField(max_length=200)

    phone_number = models.CharField(max_length=20)

    delivery_address = models.TextField()

    notes = models.TextField(
        blank=True
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID
    )

    delivery_advance_status = models.CharField(
        max_length=20,
        choices=DeliveryAdvanceStatus.choices,
        default=DeliveryAdvanceStatus.PENDING
    )

    courier_name = models.CharField(
        max_length=100,
        blank=True
    )

    tracking_id = models.CharField(
        max_length=100,
        blank=True
    )

    courier_booking_date = models.DateField(
        null=True,
        blank=True
    )

    staff_note = models.TextField(
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # This records whether this order has already reduced product stock.  It
    # prevents an edit to a confirmed order from deducting stock a second time.
    stock_reserved = models.BooleanField(default=False, editable=False)

    confirmed_at = models.DateTimeField(null=True, blank=True, editable=False)
    shipped_at = models.DateTimeField(null=True, blank=True, editable=False)
    delivered_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["delivery_advance_status", "created_at"]),
        ]

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"

    def recalculate_total(self):
        """Calculate the order total from the price snapshots on its items."""
        total = sum(
            (item.line_total for item in self.items.all()),
            Decimal("0.00"),
        )
        self.total_amount = total
        self.save(update_fields=("total_amount", "updated_at"))

    @classmethod
    def allowed_next_statuses(cls, status):
        return {
            cls.Status.PENDING: {cls.Status.CONFIRMED, cls.Status.CANCELLED},
            cls.Status.CONFIRMED: {cls.Status.SHIPPED, cls.Status.CANCELLED},
            cls.Status.SHIPPED: {cls.Status.DELIVERED, cls.Status.CANCELLED},
            cls.Status.DELIVERED: set(),
            cls.Status.CANCELLED: set(),
        }[status]

    @transaction.atomic
    def record_status_change(self, previous_status, changed_by=None):
        """Save the status timestamp, stock result, and immutable audit entry."""
        if previous_status == self.status:
            return

        timestamp_field = {
            self.Status.CONFIRMED: "confirmed_at",
            self.Status.SHIPPED: "shipped_at",
            self.Status.DELIVERED: "delivered_at",
            self.Status.CANCELLED: "cancelled_at",
        }.get(self.status)
        if timestamp_field and getattr(self, timestamp_field) is None:
            setattr(self, timestamp_field, timezone.now())
            self.save(update_fields=(timestamp_field, "updated_at"))

        self.sync_stock_for_status()
        OrderStatusHistory.objects.create(
            order=self,
            previous_status=previous_status,
            new_status=self.status,
            changed_by=changed_by,
        )

    @transaction.atomic
    def sync_stock_for_status(self):
        """Reserve stock on confirmation and return it if the order is cancelled.

        This is intentionally called after order items have been saved.  Product
        rows are locked while stock is checked and changed, so two staff members
        cannot confirm the last unit at the same time.
        """
        locked_order = type(self).objects.select_for_update().get(pk=self.pk)
        items = list(
            locked_order.items.select_related("product").select_for_update()
        )

        if (
            locked_order.status == self.Status.CONFIRMED
            and not locked_order.stock_reserved
        ):
            if not items:
                raise ValidationError("A confirmed order must contain an item.")

            products = {
                product.pk: product
                for product in Product.objects.select_for_update().filter(
                    pk__in=[item.product_id for item in items]
                )
            }
            quantities_by_product = {}
            for item in items:
                quantities_by_product[item.product_id] = (
                    quantities_by_product.get(item.product_id, 0) + item.quantity
                )
            for product_id, requested_quantity in quantities_by_product.items():
                product = products[product_id]
                if product.stock < requested_quantity:
                    raise ValidationError(
                        f"Only {product.stock} unit(s) of {product.name} "
                        "are currently in stock."
                    )

            for product_id, requested_quantity in quantities_by_product.items():
                product = products[product_id]
                product.stock -= requested_quantity
                product.save(update_fields=("stock", "updated_at"))

            locked_order.stock_reserved = True
            locked_order.save(update_fields=("stock_reserved", "updated_at"))

        elif (
            locked_order.status == self.Status.CANCELLED
            and locked_order.stock_reserved
        ):
            products = {
                product.pk: product
                for product in Product.objects.select_for_update().filter(
                    pk__in=[item.product_id for item in items]
                )
            }
            quantities_by_product = {}
            for item in items:
                quantities_by_product[item.product_id] = (
                    quantities_by_product.get(item.product_id, 0) + item.quantity
                )
            for product_id, returned_quantity in quantities_by_product.items():
                product = products[product_id]
                product.stock += returned_quantity
                product.save(update_fields=("stock", "updated_at"))

            locked_order.stock_reserved = False
            locked_order.save(update_fields=("stock_reserved", "updated_at"))

        self.stock_reserved = locked_order.stock_reserved


class OrderItem(models.Model):

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    product_name = models.CharField(
        max_length=200
    )

    product_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    @property
    def line_total(self):
        return self.product_price * self.quantity


class OrderStatusHistory(models.Model):
    """A permanent record of each operational order-status transition."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, choices=Order.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Order #{self.order_id}: {self.previous_status} → {self.new_status}"
