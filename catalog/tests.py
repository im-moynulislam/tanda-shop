from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Product


class ProductAdminTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )
        Product.objects.create(
            name="Available product",
            description="Available for sale.",
            price=Decimal("100.00"),
            stock=3,
            low_stock_threshold=2,
            is_available=True,
        )
        Product.objects.create(
            name="Sold out product",
            description="Currently unavailable.",
            price=Decimal("100.00"),
            stock=0,
            is_available=False,
        )

    def test_out_of_stock_filter_only_shows_sold_out_products(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("store_admin:catalog_product_changelist"),
            {"stock_status": "out_of_stock"},
        )

        self.assertContains(response, "Sold out product")
        self.assertNotContains(response, "Available product")

    def test_low_stock_filter_uses_each_product_restock_threshold(self):
        Product.objects.create(
            name="Low stock product",
            description="Needs restocking.",
            price=Decimal("100.00"),
            stock=3,
            low_stock_threshold=3,
            is_available=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("store_admin:catalog_product_changelist"),
            {"stock_status": "low_stock"},
        )

        self.assertContains(response, "Low stock product")
        self.assertNotContains(response, "Available product")

    def test_product_rejects_an_original_price_below_sale_price(self):
        product = Product(
            name="Invalid sale price",
            description="Validation test.",
            price=Decimal("100.00"),
            original_price=Decimal("90.00"),
        )

        with self.assertRaises(ValidationError):
            product.full_clean()
