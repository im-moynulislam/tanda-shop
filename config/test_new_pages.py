"""
Tests that the new page features show up: trust badges, discount / low stock /
trending tags, star ratings, category counts, delivery charges, chat hints.

Run:  python manage.py test config.test_new_pages -v 2

These need the new home.html, product_detail.html and return_exchange_policy.html,
plus the new catalog models and storefront views.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

import re
from datetime import timedelta

from django.utils import timezone

from catalog.models import Category, Product
from config.test_catalog import make_product

HINT = "Click to chat &amp; confirm order instantly"


class HomeHeroTests(TestCase):
    def test_subtitle_and_trust_badges_are_shown(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Curated daily essentials delivered right to your doorstep.")
        self.assertContains(response, "Fast Home Delivery")
        self.assertContains(response, "100% Genuine Products")

    def test_payment_messages_are_not_in_the_hero(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Pay product price on delivery")
        self.assertNotContains(response, "Delivery charge is paid in advance.")

    def test_chat_hint_is_shown_next_to_the_contact_button(self):
        self.assertContains(self.client.get(reverse("home")), HINT)


class HomeProductCardTests(TestCase):
    def home(self):
        return self.client.get(reverse("home"))

    def test_discount_badge_shows_the_percent_and_the_old_price(self):
        make_product(price="850.00", original_price=Decimal("1000.00"))
        response = self.home()
        self.assertContains(response, "-15%")
        self.assertContains(response, "product-old-price")

    def test_no_discount_badge_without_a_real_discount(self):
        make_product("Plain")
        make_product("Equal", price="500.00", original_price=Decimal("500.00"))
        self.assertNotContains(self.home(), "badge-sale")

    def test_low_stock_badge(self):
        make_product("Few", stock=2)
        self.assertContains(self.home(), "Low stock")

    def test_no_low_stock_badge_when_stock_is_healthy(self):
        make_product("Many", stock=20)
        self.assertNotContains(self.home(), "badge-low")

    def test_trending_badge_for_featured_products(self):
        make_product("Hot", stock=20, is_featured=True)
        response = self.home()
        self.assertContains(response, "Trending")

    def test_no_trending_badge_for_normal_products(self):
        make_product("Normal", stock=20)
        self.assertNotContains(self.home(), "badge-trending")

    def test_low_stock_wins_over_trending(self):
        make_product("Hot but few", stock=2, is_featured=True)
        response = self.home()
        self.assertContains(response, "badge-low")
        self.assertNotContains(response, "badge-trending")

    def test_rating_shows_only_when_real_numbers_exist(self):
        make_product("Rated", rating=Decimal("4.8"), review_count=42)
        response = self.home()
        self.assertContains(response, "4.8")
        self.assertContains(response, "(42)")

    def test_no_rating_row_without_a_rating(self):
        make_product("Unrated")
        self.assertNotContains(self.home(), "product-rating")


class HomeCategoryTests(TestCase):
    def test_category_tiles_show_item_counts(self):
        many = Category.objects.create(name="Many Things")
        one = Category.objects.create(name="One Thing")
        Category.objects.create(name="Nothing Yet")
        make_product("A", category=many)
        make_product("B", category=many)
        make_product("C", category=one)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "2 items")
        self.assertContains(response, "1 item<")
        self.assertContains(response, "Coming soon")


class ProductPageTests(TestCase):
    def page(self, product):
        return self.client.get(reverse("product_detail", args=[product.slug]))

    def test_discount_and_rating_are_shown(self):
        product = make_product(
            price="850.00", original_price=Decimal("1000.00"), rating=Decimal("4.5"), review_count=12
        )
        response = self.page(product)
        self.assertContains(response, "-15%")
        self.assertContains(response, "4.5")
        self.assertContains(response, "12 reviews")

    def test_no_discount_or_rating_when_there_is_none(self):
        response = self.page(make_product())
        self.assertNotContains(response, "detail-discount")
        self.assertNotContains(response, "detail-rating")

    def test_low_stock_and_trending_tags(self):
        low = self.page(make_product("Few", stock=2))
        trending = self.page(make_product("Hot", stock=20, is_featured=True))
        self.assertContains(low, "tag-low")
        self.assertContains(trending, "tag-trending")

    def test_chat_hint_and_payment_note_are_shown(self):
        response = self.page(make_product())
        self.assertContains(response, HINT)
        self.assertContains(response, "the delivery charge is paid in advance")

    def test_sold_out_product_has_no_order_buttons(self):
        response = self.page(make_product("Gone", stock=0))
        self.assertNotContains(response, "detail-order-card")


class PolicyPageTests(TestCase):
    def test_delivery_charges_and_payment_rules_are_shown(self):
        response = self.client.get(reverse("return_exchange_policy"))
        self.assertContains(response, "Inside Dhaka")
        self.assertContains(response, "Outside Dhaka")
        self.assertContains(response, "৳80")
        self.assertContains(response, "৳130")
        self.assertContains(response, "paid in advance")
        self.assertContains(response, "3-Day Return")


class HeroSliderTests(TestCase):
    def home(self):
        return self.client.get(reverse("home"))

    def slides(self, response):
        return len(re.findall(r'class="hero-slide(?: is-active)?"', response.content.decode()))

    def dots(self, response):
        return len(re.findall(r'class="hero-dot(?: is-active)?"', response.content.decode()))

    def test_only_featured_in_stock_available_products_are_used(self):
        make_product("Featured", stock=5, is_featured=True)
        make_product("Plain", stock=5)
        make_product("Featured sold out", stock=0, is_featured=True)
        make_product("Featured hidden", stock=5, is_featured=True, is_available=False)
        names = [p.name for p in self.home().context["hero_products"]]
        self.assertEqual(names, ["Featured"])

    def test_at_most_five_slides(self):
        for number in range(7):
            make_product(f"F{number}", stock=5, is_featured=True)
        response = self.home()
        self.assertEqual(len(response.context["hero_products"]), 5)
        self.assertEqual(self.slides(response), 5)

    def test_newest_featured_products_come_first(self):
        old = make_product("Old", stock=5, is_featured=True)
        new = make_product("New", stock=5, is_featured=True)
        now = timezone.now()
        Product.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=3))
        Product.objects.filter(pk=new.pk).update(created_at=now)
        names = [p.name for p in self.home().context["hero_products"]]
        self.assertEqual(names, ["New", "Old"])

    def test_without_featured_products_the_newest_in_stock_ones_are_used(self):
        make_product("Normal", stock=5)
        make_product("Sold out", stock=0)
        names = {p.name for p in self.home().context["hero_products"]}
        self.assertEqual(names, {"Normal"})

    def test_page_loads_with_no_products(self):
        response = self.home()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["hero_products"], [])
        self.assertEqual(self.slides(response), 0)

    def test_first_slide_is_active_and_dots_match_the_slides(self):
        for number in range(3):
            make_product(f"F{number}", stock=5, is_featured=True)
        response = self.home()
        self.assertEqual(response.content.decode().count("hero-slide is-active"), 1)
        self.assertEqual(self.slides(response), 3)
        self.assertEqual(self.dots(response), 3)

    def test_one_product_means_no_dots(self):
        make_product("Only", stock=5, is_featured=True)
        response = self.home()
        self.assertEqual(self.slides(response), 1)
        self.assertEqual(self.dots(response), 0)

    def test_slider_and_its_script_are_on_the_page(self):
        response = self.home()
        self.assertContains(response, 'id="hero-slider"')
        self.assertContains(response, "var DELAY=2000")