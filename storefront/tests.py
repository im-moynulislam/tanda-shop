from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalog.models import Product


class CartQuantityTests(TestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name="Test Product",
            description="A product used for cart tests.",
            price=Decimal("100.00"),
            stock=3,
            is_available=True,
        )

    def test_blank_quantity_does_not_add_product(self):
        response = self.client.post(
            reverse("add_to_cart", args=[self.product.id]),
            {"quantity": ""},
        )

        cart = self.client.session.get("cart", {})

        self.assertRedirects(
            response,
            reverse(
                "product_detail",
                args=[self.product.slug],
            ),
        )

        self.assertNotIn(
            str(self.product.id),
            cart,
        )

    def test_quantity_cannot_exceed_stock(self):
        self.client.post(
            reverse("add_to_cart", args=[self.product.id]),
            {"quantity": 10},
        )

        cart = self.client.session["cart"]

        self.assertEqual(
            cart[str(self.product.id)],
            3,
        )

    def test_new_quantity_replaces_old_quantity(self):
        self.client.post(
            reverse("add_to_cart", args=[self.product.id]),
            {"quantity": 2},
        )

        self.client.post(
            reverse("add_to_cart", args=[self.product.id]),
            {"quantity": 1},
        )

        cart = self.client.session["cart"]

        self.assertEqual(
            cart[str(self.product.id)],
            1,
        )
