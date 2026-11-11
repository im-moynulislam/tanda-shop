from django.contrib import admin
from django.db.models import F

from config.admin import admin_site

from .models import Category, Product, ProductImage


class StockStatusFilter(admin.SimpleListFilter):

    title = "stock status"
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return (
            ("in_stock", "In stock"),
            ("out_of_stock", "Out of stock"),
            ("low_stock", "At or below restock threshold"),
        )

    def queryset(self, request, queryset):
        if self.value() == "in_stock":
            return queryset.filter(stock__gt=0)
        if self.value() == "out_of_stock":
            return queryset.filter(stock=0)
        if self.value() == "low_stock":
            return queryset.filter(stock__lte=F("low_stock_threshold"))
        return queryset


@admin.register(Category, site=admin_site)
class CategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "slug",
    )

    search_fields = (
        "name",
    )

    prepopulated_fields = {
        "slug": ("name",)
    }


class ProductImageInline(admin.TabularInline):

    model = ProductImage

    extra = 1


@admin.register(Product, site=admin_site)
class ProductAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
        "price",
        "stock",
        "low_stock_threshold",
        "is_available",
        "is_featured",
    )

    list_filter = (
        "category",
        StockStatusFilter,
        "is_available",
        "is_featured",
    )

    search_fields = (
        "name",
        "description",
    )

    prepopulated_fields = {
        "slug": ("name",)
    }

    inlines = [ProductImageInline]

    fieldsets = (
        ("Product details", {"fields": ("name", "slug", "category", "description")} ),
        ("Pricing and inventory", {"fields": ("price", "original_price", "stock", "low_stock_threshold")} ),
        (
            "Customer rating (optional)",
            {
                "fields": ("rating", "review_count"),
                "description": "Fill these only with real customer ratings. If left empty, no stars are shown in the shop.",
            },
        ),
        ("Storefront visibility", {"fields": ("is_available", "is_featured")} ),
    )


admin_site.register(ProductImage)