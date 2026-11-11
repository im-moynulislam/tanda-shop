from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self):
        from django.contrib.auth.models import Group, Permission
        from django.db.models.signals import post_migrate

        def create_staff_groups(sender, **kwargs):
            # Django creates model permissions during post_migrate. Registering
            # here ensures the groups work in both fresh databases and upgrades.
            if sender.label != "orders":
                return

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
                        actions = (
                            ("view",)
                            if group_name == "Order processors"
                            and app_label == "catalog"
                            else ("add", "change", "view", "delete")
                        )
                        if group_name == "Order processors" and app_label == "orders":
                            actions = ("add", "change", "view")
                        codenames.extend(
                            f"{action}_{model}" for action in actions
                        )
                    permissions = permissions | Permission.objects.filter(
                        content_type__app_label=app_label,
                        codename__in=codenames,
                    )
                group.permissions.set(permissions)

        post_migrate.connect(
            create_staff_groups,
            sender=self,
            dispatch_uid="orders.create_staff_groups",
            # Keep the function alive. Django stores signal receivers as weak
            # references, so without this the local function can be garbage
            # collected and the staff groups end up with no permissions.
            weak=False,
        )
