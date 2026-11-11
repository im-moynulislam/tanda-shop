import re

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.forms.models import BaseInlineFormSet
from django.utils.html import format_html

from config.admin import admin_site

from .models import Order, OrderItem, OrderStatusHistory


class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ("product", "quantity")

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        quantity = cleaned_data.get("quantity")

        if quantity is not None and quantity < 1:
            raise forms.ValidationError("Quantity must be at least 1.")

        if product and quantity:
            if not product.is_available:
                raise forms.ValidationError(
                    f"{product.name} is not available for sale."
                )
            if quantity > product.stock:
                raise forms.ValidationError(
                    f"Only {product.stock} unit(s) of {product.name} are in stock."
                )
        return cleaned_data


class OrderItemInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        selected_product_ids = set()
        item_count = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            if product is None:
                # Items of a stock-reserved order are locked, so they have no
                # editable product field. They still count as items.
                if form.instance.pk:
                    item_count += 1
                continue
            if product.pk in selected_product_ids:
                raise forms.ValidationError(
                    "Add each product only once; change its quantity instead."
                )
            selected_product_ids.add(product.pk)
            item_count += 1

        if item_count == 0:
            raise forms.ValidationError("Add at least one product to the order.")


class OrderItemInline(admin.TabularInline):

    model = OrderItem

    form = OrderItemForm
    formset = OrderItemInlineFormSet
    extra = 1
    min_num = 1
    validate_min = True
    autocomplete_fields = ("product",)
    fields = ("product", "quantity", "product_name", "product_price", "line_total")
    readonly_fields = ("product_name", "product_price", "line_total")

    @admin.display(description="Line total")
    def line_total(self, obj):
        if obj.pk:
            return f"৳{obj.line_total:,.2f}"
        return "Calculated after saving"

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj and obj.stock_reserved else 1

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.stock_reserved:
            return (
                "product",
                "quantity",
                "product_name",
                "product_price",
                "line_total",
            )
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return obj is None or not obj.stock_reserved


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    fields = ("previous_status", "new_status", "changed_by", "created_at")
    readonly_fields = fields
    verbose_name_plural = "Status history"

    def has_add_permission(self, request, obj=None):
        return False


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")

        if not self.instance.pk and status != Order.Status.PENDING:
            self.add_error(
                "status",
                "Create a message order as pending, add its items, then confirm it.",
            )

        if self.instance.pk and status == Order.Status.CONFIRMED:
            if not self.instance.stock_reserved:
                items = self.instance.items.select_related("product")
                if not items.exists():
                    self.add_error("status", "A confirmed order must contain an item.")
                for item in items:
                    if item.quantity > item.product.stock:
                        self.add_error(
                            "status",
                            f"Only {item.product.stock} unit(s) of "
                            f"{item.product.name} are in stock.",
                        )

        if self.instance.pk and status != self.instance.status:
            if status not in Order.allowed_next_statuses(self.instance.status):
                self.add_error(
                    "status",
                    f"An order cannot move from {self.instance.get_status_display()} "
                    f"to {Order.Status(status).label}.",
                )

        if (
            self.instance.pk
            and status in (Order.Status.SHIPPED, Order.Status.DELIVERED)
            and not self.instance.stock_reserved
        ):
            self.add_error(
                "status",
                "Confirm the order before marking it shipped or delivered.",
            )

        if status == Order.Status.SHIPPED and not cleaned_data.get("courier_name"):
            self.add_error(
                "courier_name",
                "Choose or enter the courier before marking an order shipped.",
            )

        if (
            self.instance.pk
            and self.instance.stock_reserved
            and status == Order.Status.PENDING
        ):
            self.add_error(
                "status",
                "A stock-reserved order cannot return to pending. Cancel it to return stock.",
            )

        return cleaned_data


@admin.register(Order, site=admin_site)
class OrderAdmin(admin.ModelAdmin):

    form = OrderAdminForm

    list_display = (
        "id",
        "customer_name",
        "customer_phone",
        "total_amount",
        "status_badge",
        "payment_status",
        "delivery_advance_status",
        "courier_name",
        "item_count",
        "created_at",
    )

    list_filter = (
        "status",
        "payment_status",
        "delivery_advance_status",
        "created_at",
    )

    search_fields = (
        "=id",
        "customer_name",
        "phone_number",
        "tracking_id",
    )

    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 25

    actions = (
        "mark_as_confirmed",
        "mark_delivery_advance_paid",
        "mark_as_shipped",
        "mark_as_delivered",
        "mark_as_cancelled",
    )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            Order.Status.PENDING: "#9a6700",
            Order.Status.CONFIRMED: "#0b57d0",
            Order.Status.SHIPPED: "#6f42c1",
            Order.Status.DELIVERED: "#137333",
            Order.Status.CANCELLED: "#b3261e",
        }
        return format_html(
            '<strong style="color: {}">{}</strong>',
            colors[obj.status],
            obj.get_status_display(),
        )

    @admin.display(description="Items", ordering="item_count")
    def item_count(self, obj):
        return obj.item_count

    @admin.display(description="Phone")
    def customer_phone(self, obj):
        digits = re.sub(r"\D", "", obj.phone_number)
        if digits.startswith("0"):
            digits = f"88{digits}"
        return format_html(
            '<a href="https://wa.me/{}" target="_blank" rel="noopener">{}</a>',
            digits,
            obj.phone_number,
        )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(item_count=Count("items"))

    @admin.action(description="Mark selected orders as delivery advance paid")
    def mark_delivery_advance_paid(self, request, queryset):
        queryset.update(
            delivery_advance_status=Order.DeliveryAdvanceStatus.PAID
        )

    def _change_status(self, request, queryset, status, label):
        changed = 0
        errors = []
        for order in queryset:
            try:
                if status == Order.Status.SHIPPED and not order.courier_name:
                    raise ValidationError(
                        "Add a courier name before marking this order shipped."
                    )
                with transaction.atomic():
                    previous_status = order.status
                    if status not in Order.allowed_next_statuses(previous_status):
                        raise ValidationError(
                            f"Cannot move from {order.get_status_display()} to "
                            f"{Order.Status(status).label}."
                        )
                    order.status = status
                    order.save(update_fields=("status", "updated_at"))
                    order.record_status_change(previous_status, request.user)
                changed += 1
            except ValidationError as error:
                errors.append(f"Order #{order.pk}: {error.messages[0]}")

        if changed:
            self.message_user(
                request,
                f"{changed} order(s) marked as {label}.",
                messages.SUCCESS,
            )
        for error in errors:
            self.message_user(request, error, messages.ERROR)

    @admin.action(description="Confirm selected orders and reserve stock")
    def mark_as_confirmed(self, request, queryset):
        self._change_status(request, queryset, Order.Status.CONFIRMED, "confirmed")

    @admin.action(description="Mark selected orders as shipped")
    def mark_as_shipped(self, request, queryset):
        unreserved = queryset.filter(stock_reserved=False)
        if unreserved.exists():
            self.message_user(
                request,
                "Confirm an order before marking it shipped.",
                messages.ERROR,
            )
            queryset = queryset.exclude(pk__in=unreserved.values("pk"))
        self._change_status(request, queryset, Order.Status.SHIPPED, "shipped")

    @admin.action(description="Mark selected orders as delivered")
    def mark_as_delivered(self, request, queryset):
        unreserved = queryset.filter(stock_reserved=False)
        if unreserved.exists():
            self.message_user(
                request,
                "Confirm an order before marking it delivered.",
                messages.ERROR,
            )
            queryset = queryset.exclude(pk__in=unreserved.values("pk"))
        self._change_status(request, queryset, Order.Status.DELIVERED, "delivered")

    @admin.action(description="Cancel selected orders and return reserved stock")
    def mark_as_cancelled(self, request, queryset):
        self._change_status(request, queryset, Order.Status.CANCELLED, "cancelled")

    readonly_fields = (
        "total_amount",
        "stock_reserved",
        "confirmed_at",
        "shipped_at",
        "delivered_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Customer Details",
            {
                "fields": (
                    "customer_name",
                    "phone_number",
                    "delivery_address",
                    "notes",
                )
            },
        ),
        (
            "Order Processing",
            {
                "fields": (
                    "status",
                    "payment_status",
                    "delivery_advance_status",
                    "courier_name",
                    "tracking_id",
                    "courier_booking_date",
                    "staff_note",
                )
            },
        ),
        (
            "Order items",
            {
                "description": (
                    "Add each product and quantity below. Product prices and the "
                    "total are captured automatically when the order is saved."
                ),
                "fields": (),
            },
        ),
        (
            "Order Record",
            {
                "fields": (
                    "total_amount",
                    "stock_reserved",
                    "confirmed_at",
                    "shipped_at",
                    "delivered_at",
                    "cancelled_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    inlines = [OrderItemInline, OrderStatusHistoryInline]

    def save_model(self, request, obj, form, change):
        if change:
            obj._previous_status = type(obj).objects.only("status").get(
                pk=obj.pk
            ).status
        else:
            obj._previous_status = ""
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """Snapshot product details before saving newly entered message-order items."""
        instances = formset.save(commit=False)
        for item in instances:
            if not form.instance.stock_reserved:
                item.product_name = item.product.name
                item.product_price = item.product.price
            item.save()
        for item in formset.deleted_objects:
            item.delete()
        formset.save_m2m()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        order = form.instance
        order.recalculate_total()
        order.record_status_change(order._previous_status, request.user)