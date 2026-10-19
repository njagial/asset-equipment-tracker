import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user with coarse-grained RBAC roles.

    Admin    : full control (delete, role grants, settings)
    Technician: operate assets (check-in/out, maintenance logs) and edit metadata
    Viewer   : read-only access across the system
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TECHNICIAN = "TECHNICIAN", "Technician"
        VIEWER = "VIEWER", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.VIEWER,
        db_index=True,
    )

    @property
    def is_admin_role(self):
        return self.is_superuser or self.role == self.Role.ADMIN
