"""
Tests for the staff side of the catalog (catalog/admin.py).

Run:  python manage.py test config.test_catalog_admin -v 2
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from config.admin import admin_site

from catalog.models import Category, Product, ProductImage
from config.test_catalog import make_product

ADMIN = admin_site.name  # "store_admin"


def product_form_data(**overrides):
    data = {
        "name": "Blue Panjabi",
        "slug": "",
        "category": "",
        "description": "Soft cotton panjabi",
        "price": "1200.00",
        "original_price": "",
        "stock": "5",
        "low_stock_threshold": "3",
        "is_available": "on",
        "images-TOTAL_FORMS": "0",
        "images-INITIAL_FORMS": "0",
        "images-MIN_NUM_FORMS": "0",
        "images-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


class CatalogAdminTestCase(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_superuser("boss", "boss@example.com", "Test-pass-12345")
        self.client.force_login(staff)
        self.product_list = reverse(f"{ADMIN}:catalog_product_changelist")
        self.product_add = reverse(f"{ADMIN}:catalog_product_add")

    def names_on(self, response):
        return {product.name for product in response.context["cl"].queryset}


class StockFilterTests(CatalogAdminTestCase):
    def setUp(self):
        super().setUp()
        make_product("Plenty", stock=10)       # threshold 3: in stock
        make_product("Sold Out", stock=0)      # out of stock, also low
        make_product("Exactly Low", stock=3)   # equal to threshold: low
        make_product("Nearly Out", stock=2)    # below threshold: low

    def test_in_stock(self):
        response = self.client.get(self.product_list, {"stock_status": "in_stock"})
        self.assertEqual(self.names_on(response), {"Plenty", "Exactly Low", "Nearly Out"})

    def test_out_of_stock(self):
        response = self.client.get(self.product_list, {"stock_status": "out_of_stock"})
        self.assertEqual(self.names_on(response), {"Sold Out"})

    def test_low_stock_includes_products_at_the_threshold(self):
        response = self.client.get(self.product_list, {"stock_status": "low_stock"})
        self.assertEqual(self.names_on(response), {"Sold Out", "Exactly Low", "Nearly Out"})

    def test_no_filter_shows_everything(self):
        self.assertEqual(len(self.names_on(self.client.get(self.product_list))), 4)


class ProductAdminTests(CatalogAdminTestCase):
    def test_staff_can_add_a_product_and_the_slug_is_created(self):
        response = self.client.post(self.product_add, product_form_data())
        self.assertRedirects(response, self.product_list)
        product = Product.objects.get()
        self.assertEqual(product.slug, "blue-panjabi")
        self.assertTrue(product.is_available)
        self.assertFalse(product.is_featured)

    def test_original_price_below_price_is_refused(self):
        response = self.client.post(
            self.product_add, product_form_data(price="1200.00", original_price="900.00")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_negative_price_is_refused(self):
        response = self.client.post(self.product_add, product_form_data(price="-10.00"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_negative_stock_is_refused(self):
        response = self.client.post(self.product_add, product_form_data(stock="-1"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_search_finds_by_name_and_description(self):
        make_product("Red Saree")
        Product.objects.create(name="Plain", description="Soft silk cloth", price=100, stock=1)
        by_name = self.client.get(self.product_list, {"q": "saree"})
        by_description = self.client.get(self.product_list, {"q": "silk"})
        self.assertEqual(self.names_on(by_name), {"Red Saree"})
        self.assertEqual(self.names_on(by_description), {"Plain"})

    def test_change_page_loads_for_a_product_with_images(self):
        product = make_product()
        ProductImage.objects.create(product=product, image="products/a.jpg", is_primary=True)
        url = reverse(f"{ADMIN}:catalog_product_change", args=[product.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_image_list_page_loads(self):
        product = make_product()
        ProductImage.objects.create(product=product, image="products/a.jpg")
        url = reverse(f"{ADMIN}:catalog_productimage_changelist")
        self.assertEqual(self.client.get(url).status_code, 200)


class CategoryAdminTests(CatalogAdminTestCase):
    def test_staff_can_add_a_category_and_the_slug_is_created(self):
        url = reverse(f"{ADMIN}:catalog_category_add")
        response = self.client.post(url, {"name": "Men Shirts", "slug": "", "description": ""})
        self.assertRedirects(response, reverse(f"{ADMIN}:catalog_category_changelist"))
        self.assertEqual(Category.objects.get().slug, "men-shirts")
