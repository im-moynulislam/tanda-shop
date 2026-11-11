"""
Tests for the new Tanda features: discount percent, low-stock and trending tags,
star rating fields, category product counts.

Run:  python manage.py test config.test_new_features -v 2
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from config.admin import admin_site
from config.test_catalog import make_product
from config.test_catalog_admin import product_form_data

ADMIN = admin_site.name  # "store_admin"


class DiscountTests(TestCase):
    def test_percent_off_is_worked_out_from_original_price(self):
        product = make_product(price="850.00", original_price=Decimal("1000.00"))
        self.assertEqual(product.discount_percent, 15)

    def test_no_original_price_means_no_discount(self):
        self.assertEqual(make_product().discount_percent, 0)

    def test_same_original_and_sale_price_means_no_discount(self):
        product = make_product(price="500.00", original_price=Decimal("500.00"))
        self.assertEqual(product.discount_percent, 0)

    def test_tiny_difference_rounds_to_no_discount(self):
        product = make_product(price="996.00", original_price=Decimal("1000.00"))
        self.assertEqual(product.discount_percent, 0)

    def test_percent_is_rounded_to_a_whole_number(self):
        half = make_product("Half", price="995.00", original_price=Decimal("1000.00"))
        third = make_product("Third", price="667.00", original_price=Decimal("1000.00"))
        self.assertEqual(half.discount_percent, 1)
        self.assertEqual(third.discount_percent, 33)


class StockTagTests(TestCase):
    def test_low_stock_at_or_below_the_threshold(self):
        for stock, expected in ((0, False), (1, True), (3, True), (4, False), (50, False)):
            with self.subTest(stock=stock):
                self.assertEqual(make_product(f"P{stock}", stock=stock).is_low_stock, expected)

    def test_low_stock_uses_the_products_own_threshold(self):
        product = make_product(stock=8, low_stock_threshold=10)
        self.assertTrue(product.is_low_stock)

    def test_trending_needs_the_featured_switch_and_stock(self):
        featured = make_product("Featured", stock=5, is_featured=True)
        sold_out = make_product("Sold Out", stock=0, is_featured=True)
        normal = make_product("Normal", stock=5)
        self.assertTrue(featured.show_trending)
        self.assertFalse(sold_out.show_trending)
        self.assertFalse(normal.show_trending)


class RatingTests(TestCase):
    def build(self, **extra):
        values = dict(name="Rated", description="d", price=Decimal("10.00"), stock=1)
        values.update(extra)
        return Product(**values)

    def test_product_has_no_rating_by_default(self):
        product = make_product()
        self.assertIsNone(product.rating)
        self.assertEqual(product.review_count, 0)
        self.assertFalse(product.has_rating)

    def test_rating_with_reviews_is_shown(self):
        product = make_product(rating=Decimal("4.8"), review_count=42)
        self.assertTrue(product.has_rating)

    def test_rating_without_review_count_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self.build(rating=Decimal("4.8"), review_count=0).full_clean()
        self.assertIn("review_count", caught.exception.message_dict)

    def test_review_count_without_rating_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self.build(review_count=5).full_clean()
        self.assertIn("rating", caught.exception.message_dict)

    def test_rating_must_be_between_0_and_5(self):
        for bad in ("5.1", "-0.5"):
            with self.subTest(rating=bad):
                with self.assertRaises(ValidationError) as caught:
                    self.build(rating=Decimal(bad), review_count=3).full_clean()
                self.assertIn("rating", caught.exception.message_dict)

    def test_valid_rating_passes(self):
        self.build(rating=Decimal("5.0"), review_count=1).full_clean()
        self.build(rating=Decimal("0.0"), review_count=1).full_clean()

    def test_database_blocks_a_rating_above_5(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_product(rating=Decimal("5.5"), review_count=2)

    def test_empty_review_count_is_saved_as_zero(self):
        product = make_product(review_count=None)
        product.refresh_from_db()
        self.assertEqual(product.review_count, 0)


class CategoryCountTests(TestCase):
    def test_home_page_counts_only_available_products_and_sorts_by_name(self):
        shirts = Category.objects.create(name="Shirts")
        bags = Category.objects.create(name="Bags")
        Category.objects.create(name="Empty")
        make_product("S1", category=shirts)
        make_product("S2", category=shirts)
        make_product("S3", category=shirts, is_available=False)
        make_product("B1", category=bags)
        response = self.client.get(reverse("home"))
        counts = [(c.name, c.product_count) for c in response.context["categories"]]
        self.assertEqual(counts, [("Bags", 1), ("Empty", 0), ("Shirts", 2)])


class RatingAdminTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_superuser("boss", "boss@example.com", "Test-pass-12345")
        self.client.force_login(staff)
        self.add_url = reverse(f"{ADMIN}:catalog_product_add")

    def test_rating_fields_appear_on_the_product_form(self):
        response = self.client.get(self.add_url)
        self.assertContains(response, 'name="rating"')
        self.assertContains(response, 'name="review_count"')

    def test_staff_can_save_a_real_rating(self):
        response = self.client.post(self.add_url, product_form_data(rating="4.8", review_count="42"))
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get()
        self.assertEqual(product.rating, Decimal("4.8"))
        self.assertEqual(product.review_count, 42)

    def test_product_can_still_be_saved_without_a_rating(self):
        response = self.client.post(self.add_url, product_form_data())
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get()
        self.assertIsNone(product.rating)
        self.assertEqual(product.review_count, 0)

    def test_rating_without_reviews_is_refused_in_the_admin(self):
        response = self.client.post(self.add_url, product_form_data(rating="4.8", review_count="0"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_reviews_without_rating_is_refused_in_the_admin(self):
        response = self.client.post(self.add_url, product_form_data(rating="", review_count="5"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)