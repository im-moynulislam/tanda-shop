"""
Tests for catalog/models.py: slugs, price and stock rules, product images.

Run:  python manage.py test config.test_catalog -v 2
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.models import Category, Product, ProductImage


def make_product(name="Cotton Shirt", price="500.00", stock=10, **extra):
    return Product.objects.create(
        name=name,
        description="Test product",
        price=Decimal(price),
        stock=stock,
        **extra,
    )


class CategoryTests(TestCase):
    def test_slug_is_created_from_name(self):
        category = Category.objects.create(name="Men Shirts")
        self.assertEqual(category.slug, "men-shirts")

    def test_two_names_that_make_the_same_slug_get_different_slugs(self):
        first = Category.objects.create(name="T Shirts")
        second = Category.objects.create(name="T-Shirts")
        self.assertEqual(first.slug, "t-shirts")
        self.assertEqual(second.slug, "t-shirts-2")

    def test_category_name_must_be_unique(self):
        Category.objects.create(name="Shoes")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Category.objects.create(name="Shoes")

    def test_deleting_a_category_keeps_its_products(self):
        category = Category.objects.create(name="Bags")
        product = make_product(category=category)
        category.delete()
        product.refresh_from_db()
        self.assertIsNone(product.category)


class ProductTests(TestCase):
    def test_slug_is_created_from_name(self):
        self.assertEqual(make_product("Blue Panjabi").slug, "blue-panjabi")

    def test_same_name_gets_a_different_slug(self):
        first = make_product("Blue Panjabi")
        second = make_product("Blue Panjabi")
        self.assertEqual(first.slug, "blue-panjabi")
        self.assertEqual(second.slug, "blue-panjabi-2")

    def test_slug_does_not_change_when_product_is_saved_again(self):
        product = make_product("Blue Panjabi")
        product.price = Decimal("650.00")
        product.save()
        self.assertEqual(product.slug, "blue-panjabi")

    def test_new_product_is_available_with_default_low_stock_threshold(self):
        product = make_product()
        self.assertTrue(product.is_available)
        self.assertEqual(product.low_stock_threshold, 3)

    def test_str_is_the_product_name(self):
        self.assertEqual(str(make_product("Red Saree")), "Red Saree")

    def test_negative_price_is_rejected_by_validation(self):
        product = Product(name="Bad", description="d", price=Decimal("-1.00"), stock=1)
        with self.assertRaises(ValidationError):
            product.clean()

    def test_negative_price_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_product(price="-5.00")

    def test_original_price_lower_than_price_is_rejected_by_validation(self):
        product = Product(
            name="Bad",
            description="d",
            price=Decimal("500.00"),
            original_price=Decimal("400.00"),
            stock=1,
        )
        with self.assertRaises(ValidationError):
            product.clean()

    def test_original_price_lower_than_price_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_product(price="500.00", original_price=Decimal("400.00"))

    def test_original_price_equal_or_higher_is_allowed(self):
        make_product("Same", price="500.00", original_price=Decimal("500.00"))
        make_product("Higher", price="500.00", original_price=Decimal("700.00"))
        self.assertEqual(Product.objects.count(), 2)

    def test_negative_stock_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_product(stock=-1)

    def test_zero_stock_is_allowed(self):
        self.assertEqual(make_product(stock=0).stock, 0)


class ProductImageTests(TestCase):
    def test_only_one_primary_image_per_product(self):
        product = make_product()
        ProductImage.objects.create(product=product, image="products/a.jpg", is_primary=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductImage.objects.create(product=product, image="products/b.jpg", is_primary=True)

    def test_many_non_primary_images_are_allowed(self):
        product = make_product()
        for number in range(3):
            ProductImage.objects.create(product=product, image=f"products/{number}.jpg")
        self.assertEqual(product.images.count(), 3)

    def test_two_products_can_each_have_a_primary_image(self):
        for name in ("One", "Two"):
            ProductImage.objects.create(
                product=make_product(name), image=f"products/{name}.jpg", is_primary=True
            )
        self.assertEqual(ProductImage.objects.filter(is_primary=True).count(), 2)

    def test_images_come_back_in_display_order(self):
        product = make_product()
        ProductImage.objects.create(product=product, image="products/c.jpg", display_order=2)
        ProductImage.objects.create(product=product, image="products/a.jpg", display_order=0)
        ProductImage.objects.create(product=product, image="products/b.jpg", display_order=1)
        names = [image.image.name for image in product.images.all()]
        self.assertEqual(names, ["products/a.jpg", "products/b.jpg", "products/c.jpg"])

    def test_deleting_a_product_deletes_its_images(self):
        product = make_product()
        ProductImage.objects.create(product=product, image="products/a.jpg")
        product.delete()
        self.assertEqual(ProductImage.objects.count(), 0)
