"""One-off development bootstrap: users for each role + demo data.

    uv run manage.py seed_demo
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import F

from apps.inventory.models import Asset, AssetStatus, Category, Consumable

DEMO_USERS = [
    ("admin", "admin-pass-123", "ADMIN", True),
    ("tech", "tech-pass-123", "TECHNICIAN", False),
    ("viewer", "viewer-pass-123", "VIEWER", False),
]

ASSETS = [
    ("AST-2026-0001", "Projector EPSON-100", "AV Equipment", "SN-0001", "Room 204", {"voltage": "220V", "bulb_hours": 1200}),
    ("AST-2026-0002", "Yamaha MX88 Console", "AV Equipment", "SN-0002", "Rack B", {"channels": 88}),
    ("AST-2026-0003", "MacBook Pro 16 M3", "Computers", "SN-0003", "Main Warehouse", {}),
]

CONSUMABLES = [
    ("6ft HDMI Cable", "HDMI-FT6-01", "Peripherals", 2, 5, "Drawer 3"),  # intentionally low
    ("USB-C Dongle", "USBC-DONGLE", "Peripherals", 24, 10, "Drawer 3"),
    ("HDMI Right-Angle Adapter", "HDMI-RA-01", "Peripherals", 8, 10, "Drawer 4"),  # intentionally low
]


class Command(BaseCommand):
    help = "Create RBAC demo users and starter inventory data."

    def handle(self, *args, **options):
        user_model = get_user_model()
        for username, password, role, is_staff in DEMO_USERS:
            user = user_model.objects.filter(username=username).first()
            if user:
                user.role = role
                user.is_staff = is_staff
                user.save(update_fields=["role", "is_staff"])
            else:
                user_model.objects.create_user(username, password=password, role=role, is_staff=is_staff)
            self.stdout.write(f"user {username} ({role}) ready")

        for tag, name, category_name, serial, location, custom in ASSETS:
            category, _ = Category.objects.get_or_create(name=category_name)
            _asset, created = Asset.objects.get_or_create(
                asset_tag=tag,
                defaults={
                    "name": name,
                    "category": category,
                    "serial_number": serial,
                    "location": location,
                    "status": AssetStatus.AVAILABLE,
                    "custom_fields": custom,
                },
            )
            self.stdout.write(f"asset {tag} {'created' if created else 'existed'}")

        for name, sku, category_name, qty, threshold, location in CONSUMABLES:
            category, _ = Category.objects.get_or_create(name=category_name)
            _consumable, created = Consumable.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": category,
                    "quantity_on_hand": qty,
                    "minimum_threshold": threshold,
                    "location": location,
                },
            )
            self.stdout.write(f"consumable {sku} {'created' if created else 'existed'}")

        low = Consumable.objects.filter(quantity_on_hand__lte=F("minimum_threshold")).count()
        self.stdout.write(self.style.SUCCESS(f"seed_demo done; {low} item(s) below threshold"))
