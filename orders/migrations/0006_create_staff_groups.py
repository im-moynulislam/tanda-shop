from django.db import migrations


def create_staff_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group_permissions = {
        "Catalog managers": {
            "catalog": {"category", "product", "productimage"},
        },
        "Order processors": {
            "catalog": {"category", "product", "productimage"},
            "orders": {"order", "orderitem", "orderstatushistory"},
        },
    }
    for group_name, app_models in group_permissions.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        permissions = Permission.objects.none()
        for app_label, models in app_models.items():
            codenames = []
            for model in models:
                actions = ("view",) if group_name == "Order processors" and app_label == "catalog" else ("add", "change", "view", "delete")
                if group_name == "Order processors" and app_label == "orders":
                    actions = ("add", "change", "view")
                codenames.extend(f"{action}_{model}" for action in actions)
            permissions = permissions | Permission.objects.filter(
                content_type__app_label=app_label,
                codename__in=codenames,
            )
        group.permissions.set(permissions)


def remove_staff_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=("Catalog managers", "Order processors")).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_orderstatushistory_order_cancelled_at_and_more"),
        ("catalog", "0003_product_low_stock_threshold_and_more"),
    ]

    operations = [
        migrations.RunPython(create_staff_groups, remove_staff_groups),
    ]
