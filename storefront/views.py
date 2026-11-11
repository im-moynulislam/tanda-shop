from decimal import Decimal
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from catalog.models import Category, Product, ProductImage
def home(request):
    search_query = request.GET.get("q", "").strip()
    selected_category = request.GET.get(
        "category",
        ""
    ).strip()

    products = Product.objects.filter(
        is_available=True
    ).prefetch_related(
        Prefetch(
            "images",
            queryset=ProductImage.objects.order_by(
                "-is_primary",
                "display_order"
            ),
            to_attr="display_images"
        )
    )

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if selected_category:
        products = products.filter(
            category__slug=selected_category
        )

    products = products.order_by("-created_at")
    paginator = Paginator(products, 12)

    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    # Featured products rotate in the hero banner. If none are marked Featured,
    # the newest in-stock products are used so the banner is never empty.
    hero_queryset = Product.objects.filter(
        is_available=True,
        stock__gt=0,
    ).prefetch_related(
        Prefetch(
            "images",
            queryset=ProductImage.objects.order_by(
                "-is_primary",
                "display_order"
            ),
            to_attr="display_images"
        )
    ).order_by("-created_at")
    hero_products = list(hero_queryset.filter(is_featured=True)[:5])
    if not hero_products:
        hero_products = list(hero_queryset[:5])

    return render(
        request,
        "storefront/home.html",
        {
            "page_obj": page_obj,
            "hero_products": hero_products,
            "hero_product": page_obj.object_list[0] if page_obj.object_list else None,
            "categories": Category.objects.annotate(
                product_count=Count(
                    "products",
                    filter=Q(products__is_available=True),
                )
            ).order_by("name"),
            "search_query": search_query,
            "selected_category": selected_category,
        }
    )


def return_exchange_policy(request):
    return render(request, "storefront/return_exchange_policy.html")


def order_by_message(request):
    return render(request, "storefront/order_by_message.html")


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by(
                    "-is_primary",
                    "display_order"
                ),
                to_attr="display_images"
            )
        ),
        slug=slug,
        is_available=True
    )

    return render(
        request,
        "storefront/product_detail.html",
        {"product": product}
    )


# ==========================================
# CART VIEWS (Session-based)
# ==========================================

def cart_detail(request):
    messages.info(
        request,
        "To place an order, please contact us on WhatsApp or Messenger."
    )
    return redirect("order_by_message")

def add_to_cart(request, product_id):
    product = get_object_or_404(
        Product,
        id=product_id,
        is_available=True
    )

    if request.method == "POST":
        raw_quantity = request.POST.get(
            "quantity",
            ""
        )

        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            messages.error(
                request,
                "Please enter a valid quantity."
            )
            return redirect(
                "product_detail",
                slug=product.slug
            )

        if quantity < 1:
            messages.error(
                request,
                "Quantity must be at least 1."
            )
            return redirect(
                "product_detail",
                slug=product.slug
            )

        quantity_to_set = min(
            quantity,
            product.stock
        )

        if quantity_to_set == 0:
            messages.error(
                request,
                "This product is out of stock."
            )
            return redirect(
                "product_detail",
                slug=product.slug
            )

        cart = request.session.get("cart", {})

        cart[str(product.id)] = quantity_to_set

        request.session["cart"] = cart
        request.session.modified = True

        if quantity_to_set < quantity:
            messages.warning(
                request,
                f"Quantity was changed to {quantity_to_set}, the available stock."
            )
        else:
            messages.success(
                request,
                "Cart quantity updated."
            )

    return redirect("cart_detail")
     

def update_cart(request, product_id):
    if request.method == "POST":
        product = get_object_or_404(
            Product,
            id=product_id
        )

        raw_quantity = request.POST.get(
            "quantity",
            ""
        )

        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            messages.error(
                request,
                "Please enter a valid quantity."
            )
            return redirect("cart_detail")

        cart = request.session.get("cart", {})
        product_id_str = str(product.id)

        if quantity < 1:
            cart.pop(product_id_str, None)

            messages.info(
                request,
                "Product removed from your cart."
            )
        else:
            allowed_quantity = min(
                quantity,
                product.stock
            )

            if allowed_quantity == 0:
                cart.pop(product_id_str, None)

                messages.error(
                    request,
                    "This product is out of stock."
                )
            else:
                cart[product_id_str] = allowed_quantity

                if allowed_quantity < quantity:
                    messages.warning(
                        request,
                        f"Quantity was changed to {allowed_quantity}, the available stock."
                    )

        request.session["cart"] = cart
        request.session.modified = True

    return redirect("cart_detail")


def remove_from_cart(request, product_id):
    cart = request.session.get("cart", {})
    cart.pop(str(product_id), None)

    request.session["cart"] = cart
    request.session.modified = True

    return redirect("cart_detail")