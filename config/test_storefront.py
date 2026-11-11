"""
Tests for storefront/views.py: home page, search, product page, static pages
and the session cart.

Run:  python manage.py test config.test_storefront -v 2
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product, ProductImage


def make_product(name="Cotton Shirt", price="500.00", stock=10, **extra):
    return Product.objects.create(
        name=name,
        description=extra.pop("description", "Test product"),
        price=Decimal(price),
        stock=stock,
        **extra,
    )


def page_names(response):
    return [product.name for product in response.context["page_obj"]]


def messages_of(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class HomePageTests(TestCase):
    def test_home_loads_with_no_products(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["hero_product"])

    def test_available_products_show_and_unavailable_are_hidden(self):
        make_product("Visible Shirt")
        make_product("Hidden Shirt", is_available=False)
        response = self.client.get(reverse("home"))
        self.assertEqual(page_names(response), ["Visible Shirt"])

    def test_out_of_stock_product_still_shows(self):
        make_product("Sold Out Shirt", stock=0)
        self.assertEqual(page_names(self.client.get(reverse("home"))), ["Sold Out Shirt"])

    def test_newest_product_comes_first(self):
        old = make_product("Old")
        new = make_product("New")
        now = timezone.now()
        Product.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=5))
        Product.objects.filter(pk=new.pk).update(created_at=now)
        self.assertEqual(page_names(self.client.get(reverse("home"))), ["New", "Old"])

    def test_search_matches_name_ignoring_case(self):
        make_product("Red Saree")
        make_product("Blue Shirt")
        response = self.client.get(reverse("home"), {"q": "SAREE"})
        self.assertEqual(page_names(response), ["Red Saree"])

    def test_search_matches_description(self):
        make_product("Plain Item", description="Soft silk cloth")
        make_product("Other Item", description="Heavy denim")
        response = self.client.get(reverse("home"), {"q": "silk"})
        self.assertEqual(page_names(response), ["Plain Item"])

    def test_search_ignores_spaces_around_the_word(self):
        make_product("Red Saree")
        response = self.client.get(reverse("home"), {"q": "   saree   "})
        self.assertEqual(page_names(response), ["Red Saree"])

    def test_search_with_no_match_shows_empty_page_not_error(self):
        make_product("Red Saree")
        response = self.client.get(reverse("home"), {"q": "zzzz"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(page_names(response), [])

    def test_search_text_is_escaped_in_the_page(self):
        attack = "<script>alert(1)</script>"
        response = self.client.get(reverse("home"), {"q": attack})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(attack.encode(), response.content)

    def test_sql_style_search_text_is_harmless(self):
        make_product("Red Saree")
        response = self.client.get(reverse("home"), {"q": "' OR 1=1 --"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(page_names(response), [])

    def test_category_filter_uses_the_category_slug(self):
        shirts = Category.objects.create(name="Shirts")
        bags = Category.objects.create(name="Bags")
        make_product("Cotton Shirt", category=shirts)
        make_product("Leather Bag", category=bags)
        response = self.client.get(reverse("home"), {"category": shirts.slug})
        self.assertEqual(page_names(response), ["Cotton Shirt"])

    def test_unknown_category_shows_empty_page_not_error(self):
        make_product("Cotton Shirt")
        response = self.client.get(reverse("home"), {"category": "no-such-category"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(page_names(response), [])

    def test_search_and_category_work_together(self):
        shirts = Category.objects.create(name="Shirts")
        make_product("Red Shirt", category=shirts)
        make_product("Blue Shirt", category=shirts)
        make_product("Red Bag")
        response = self.client.get(reverse("home"), {"q": "red", "category": shirts.slug})
        self.assertEqual(page_names(response), ["Red Shirt"])

    def test_twelve_products_per_page(self):
        for number in range(13):
            make_product(f"Product {number}")
        first = self.client.get(reverse("home"))
        second = self.client.get(reverse("home"), {"page": 2})
        self.assertEqual(len(page_names(first)), 12)
        self.assertEqual(len(page_names(second)), 1)

    def test_bad_page_numbers_do_not_crash(self):
        for number in range(13):
            make_product(f"Product {number}")
        too_high = self.client.get(reverse("home"), {"page": 999})
        not_a_number = self.client.get(reverse("home"), {"page": "abc"})
        self.assertEqual(too_high.status_code, 200)
        self.assertEqual(too_high.context["page_obj"].number, 2)
        self.assertEqual(not_a_number.status_code, 200)
        self.assertEqual(not_a_number.context["page_obj"].number, 1)

    def test_home_loads_for_products_with_and_without_images(self):
        with_image = make_product("With Image")
        ProductImage.objects.create(product=with_image, image="products/a.jpg", is_primary=True)
        make_product("Without Image")
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)


class ProductDetailTests(TestCase):
    def test_available_product_page_loads_and_shows_the_name(self):
        product = make_product("Blue Panjabi")
        response = self.client.get(reverse("product_detail", args=[product.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Blue Panjabi")

    def test_unavailable_product_gives_404(self):
        product = make_product("Hidden", is_available=False)
        response = self.client.get(reverse("product_detail", args=[product.slug]))
        self.assertEqual(response.status_code, 404)

    def test_unknown_slug_gives_404(self):
        response = self.client.get(reverse("product_detail", args=["no-such-product"]))
        self.assertEqual(response.status_code, 404)

    def test_out_of_stock_product_page_still_loads(self):
        product = make_product("Sold Out", stock=0)
        response = self.client.get(reverse("product_detail", args=[product.slug]))
        self.assertEqual(response.status_code, 200)

    def test_product_page_loads_with_and_without_images(self):
        with_image = make_product("With Image")
        ProductImage.objects.create(product=with_image, image="products/a.jpg", is_primary=True)
        without_image = make_product("Without Image")
        for product in (with_image, without_image):
            response = self.client.get(reverse("product_detail", args=[product.slug]))
            self.assertEqual(response.status_code, 200)


class InfoPageTests(TestCase):
    def test_order_by_message_page_has_whatsapp_and_messenger(self):
        response = self.client.get(reverse("order_by_message"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode().lower()
        self.assertTrue("wa.me" in html or "whatsapp" in html, "No WhatsApp contact on the page")
        self.assertTrue("m.me" in html or "messenger" in html, "No Messenger contact on the page")

    def test_return_exchange_policy_page_loads(self):
        self.assertEqual(self.client.get(reverse("return_exchange_policy")).status_code, 200)

    def test_cart_page_sends_the_visitor_to_order_by_message(self):
        response = self.client.get(reverse("cart_detail"))
        self.assertRedirects(response, reverse("order_by_message"))
        self.assertTrue(any("contact" in text.lower() for text in messages_of(response)))


class AddToCartTests(TestCase):
    def setUp(self):
        self.product = make_product("Cotton Shirt", stock=5)
        self.url = reverse("add_to_cart", args=[self.product.id])

    def cart(self):
        return self.client.session.get("cart", {})

    def test_valid_quantity_goes_into_the_cart(self):
        response = self.client.post(self.url, {"quantity": "2"})
        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(self.cart(), {str(self.product.id): 2})

    def test_quantity_equal_to_stock_is_accepted_without_warning(self):
        response = self.client.post(self.url, {"quantity": "5"})
        self.assertEqual(self.cart(), {str(self.product.id): 5})
        self.assertFalse(any("available stock" in text for text in messages_of(response)))

    def test_quantity_above_stock_is_lowered_to_stock_with_a_warning(self):
        response = self.client.post(self.url, {"quantity": "50"})
        self.assertEqual(self.cart(), {str(self.product.id): 5})
        self.assertTrue(any("available stock" in text for text in messages_of(response)))

    def test_zero_negative_and_non_number_quantities_are_rejected(self):
        for bad in ("0", "-3", "abc", "", "2.5"):
            with self.subTest(quantity=bad):
                response = self.client.post(self.url, {"quantity": bad})
                self.assertRedirects(
                    response,
                    reverse("product_detail", args=[self.product.slug]),
                    fetch_redirect_response=False,
                )
                self.assertEqual(self.cart(), {})
                self.assertTrue(messages_of(response))

    def test_missing_quantity_is_rejected(self):
        self.client.post(self.url, {})
        self.assertEqual(self.cart(), {})

    def test_out_of_stock_product_cannot_be_added(self):
        empty = make_product("Sold Out", stock=0)
        response = self.client.post(reverse("add_to_cart", args=[empty.id]), {"quantity": "1"})
        self.assertEqual(self.cart(), {})
        self.assertTrue(any("out of stock" in text for text in messages_of(response)))

    def test_unavailable_product_gives_404(self):
        hidden = make_product("Hidden", is_available=False)
        response = self.client.post(reverse("add_to_cart", args=[hidden.id]), {"quantity": "1"})
        self.assertEqual(response.status_code, 404)

    def test_unknown_product_gives_404(self):
        response = self.client.post(reverse("add_to_cart", args=[999999]), {"quantity": "1"})
        self.assertEqual(response.status_code, 404)

    def test_opening_the_add_link_without_posting_changes_nothing(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(self.cart(), {})

    def test_adding_the_same_product_again_replaces_the_quantity(self):
        # Current behaviour: the second add replaces the first (2 then 3 gives 3, not 5).
        self.client.post(self.url, {"quantity": "2"})
        self.client.post(self.url, {"quantity": "3"})
        self.assertEqual(self.cart(), {str(self.product.id): 3})

    def test_different_products_stay_together_in_the_cart(self):
        other = make_product("Leather Bag", stock=4)
        self.client.post(self.url, {"quantity": "1"})
        self.client.post(reverse("add_to_cart", args=[other.id]), {"quantity": "2"})
        self.assertEqual(self.cart(), {str(self.product.id): 1, str(other.id): 2})

    def test_each_visitor_has_a_separate_cart(self):
        other_visitor = Client()
        self.client.post(self.url, {"quantity": "2"})
        self.assertEqual(other_visitor.session.get("cart", {}), {})

    def test_post_without_csrf_token_is_blocked(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(self.url, {"quantity": "1"})
        self.assertEqual(response.status_code, 403)


class UpdateCartTests(TestCase):
    def setUp(self):
        self.product = make_product("Cotton Shirt", stock=5)
        self.url = reverse("update_cart", args=[self.product.id])
        self.client.post(reverse("add_to_cart", args=[self.product.id]), {"quantity": "2"})

    def cart(self):
        return self.client.session.get("cart", {})

    def test_quantity_can_be_changed(self):
        response = self.client.post(self.url, {"quantity": "4"})
        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(self.cart(), {str(self.product.id): 4})

    def test_quantity_above_stock_is_lowered_with_a_warning(self):
        response = self.client.post(self.url, {"quantity": "99"})
        self.assertEqual(self.cart(), {str(self.product.id): 5})
        self.assertTrue(any("available stock" in text for text in messages_of(response)))

    def test_zero_or_negative_quantity_removes_the_product(self):
        for value in ("0", "-2"):
            with self.subTest(quantity=value):
                self.client.post(reverse("add_to_cart", args=[self.product.id]), {"quantity": "2"})
                self.client.post(self.url, {"quantity": value})
                self.assertEqual(self.cart(), {})

    def test_product_that_ran_out_of_stock_is_removed(self):
        Product.objects.filter(pk=self.product.pk).update(stock=0)
        response = self.client.post(self.url, {"quantity": "2"})
        self.assertEqual(self.cart(), {})
        self.assertTrue(any("out of stock" in text for text in messages_of(response)))

    def test_non_number_quantity_keeps_the_cart_and_shows_an_error(self):
        response = self.client.post(self.url, {"quantity": "abc"})
        self.assertEqual(self.cart(), {str(self.product.id): 2})
        self.assertTrue(messages_of(response))

    def test_opening_the_update_link_without_posting_changes_nothing(self):
        self.client.get(self.url)
        self.assertEqual(self.cart(), {str(self.product.id): 2})

    def test_unknown_product_gives_404(self):
        response = self.client.post(reverse("update_cart", args=[999999]), {"quantity": "1"})
        self.assertEqual(response.status_code, 404)

    def test_update_only_touches_the_chosen_product(self):
        other = make_product("Leather Bag", stock=4)
        self.client.post(reverse("add_to_cart", args=[other.id]), {"quantity": "1"})
        self.client.post(self.url, {"quantity": "3"})
        self.assertEqual(self.cart(), {str(self.product.id): 3, str(other.id): 1})


class RemoveFromCartTests(TestCase):
    def setUp(self):
        self.first = make_product("Cotton Shirt", stock=5)
        self.second = make_product("Leather Bag", stock=5)
        for product in (self.first, self.second):
            self.client.post(reverse("add_to_cart", args=[product.id]), {"quantity": "1"})

    def cart(self):
        return self.client.session.get("cart", {})

    def test_removes_only_the_chosen_product(self):
        response = self.client.get(reverse("remove_from_cart", args=[self.first.id]))
        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(self.cart(), {str(self.second.id): 1})

    def test_removing_a_product_not_in_the_cart_is_harmless(self):
        response = self.client.get(reverse("remove_from_cart", args=[999999]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.cart()), 2)

    def test_removing_from_an_empty_cart_is_harmless(self):
        fresh = Client()
        response = fresh.get(reverse("remove_from_cart", args=[self.first.id]))
        self.assertEqual(response.status_code, 302)
