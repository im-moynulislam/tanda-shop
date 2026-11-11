from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.text import slugify


class Category(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    slug = models.SlugField(
        max_length=120,
        unique=True,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._create_unique_slug(self.name)

        super().save(*args, **kwargs)

    def _create_unique_slug(self, value):
        base_slug = slugify(value) or "category"
        candidate = base_slug
        number = 2
        while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
            candidate = f"{base_slug}-{number}"
            number += 1
        return candidate

    def __str__(self):
        return self.name


class Product(models.Model):

    name = models.CharField(max_length=200)

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products"
    )

    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True
    )

    description = models.TextField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    stock = models.PositiveIntegerField(default=0)

    low_stock_threshold = models.PositiveIntegerField(default=3)

    is_available = models.BooleanField(default=True)

    is_featured = models.BooleanField(default=False)

    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("5"))],
        help_text="Average customer rating from 0 to 5. Leave empty if you have no real reviews yet.",
    )

    review_count = models.PositiveIntegerField(
        default=0,
        blank=True,
        help_text="How many real reviews this rating is based on.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="catalog_product_price_is_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(stock__gte=0),
                name="catalog_product_stock_is_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(original_price__isnull=True)
                | Q(original_price__gte=F("price")),
                name="catalog_product_original_price_is_not_less_than_price",
            ),
            models.CheckConstraint(
                condition=Q(rating__isnull=True)
                | (Q(rating__gte=0) & Q(rating__lte=5)),
                name="catalog_product_rating_is_between_0_and_5",
            ),
        ]

    def save(self, *args, **kwargs):

        if self.review_count is None:
            self.review_count = 0

        if not self.slug:
            self.slug = self._create_unique_slug(self.name)

        super().save(*args, **kwargs)

    def _create_unique_slug(self, value):
        base_slug = slugify(value) or "product"
        candidate = base_slug
        number = 2
        while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
            candidate = f"{base_slug}-{number}"
            number += 1
        return candidate

    def clean(self):
        super().clean()
        if self.review_count is None:
            self.review_count = 0
        if self.rating is not None and self.review_count < 1:
            raise ValidationError(
                {"review_count": "Enter how many reviews this rating is based on."}
            )
        if self.rating is None and self.review_count > 0:
            raise ValidationError(
                {"rating": "Enter the average rating, or set the review count to 0."}
            )
        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "Price cannot be negative."})
        if (
            self.original_price is not None
            and self.price is not None
            and self.original_price < self.price
        ):
            raise ValidationError(
                {"original_price": "Original price cannot be lower than sale price."}
            )

    @property
    def discount_percent(self):
        """Whole-number percent off, or 0 when there is no real discount."""
        if not self.original_price or self.price is None:
            return 0
        original = Decimal(str(self.original_price))
        price = Decimal(str(self.price))
        if original <= price:
            return 0
        percent = (original - price) / original * 100
        return int(percent.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @property
    def is_low_stock(self):
        return 0 < self.stock <= self.low_stock_threshold

    @property
    def show_trending(self):
        """The admin Featured switch shows the Trending tag (only while in stock)."""
        return self.is_featured and self.stock > 0

    @property
    def has_rating(self):
        return self.rating is not None and self.review_count > 0


    def __str__(self):
        return self.name


class ProductImage(models.Model):

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = models.ImageField(upload_to="products/")

    alt_text = models.CharField(
        max_length=200,
        blank=True
    )

    is_primary = models.BooleanField(default=False)

    display_order = models.PositiveIntegerField(default=0)


    class Meta:
        ordering = ["display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="catalog_one_primary_image_per_product",
            )
        ]


    def __str__(self):
        return f"Image for {self.product.name}"