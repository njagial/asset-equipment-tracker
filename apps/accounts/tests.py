import pytest

from apps.accounts.models import User
from apps.accounts.permissions import (
    IsAdminOnly,
    IsTechnicianOrAdmin,
    min_role,
)

pytestmark = pytest.mark.django_db


class _Req:
    METHOD_MAP = {"GET": "GET", "POST": "POST", "DELETE": "DELETE"}

    def __init__(self, user, method="GET"):
        self.user = user
        self.method = self.METHOD_MAP.get(method, method)


def test_role_ranks():
    viewer = User(username="v", role=User.Role.VIEWER, password="x")
    tech = User(username="t", role=User.Role.TECHNICIAN, password="x")
    admin = User(username="a", role=User.Role.ADMIN, password="x", is_superuser=False)

    assert min_role("TECHNICIAN", "ADMIN")(tech)
    assert not min_role("TECHNICIAN", "ADMIN")(viewer)
    assert min_role("ADMIN")(admin)
    assert not min_role("ADMIN")(tech)


def test_drf_writer_permissions():
    viewer = User(username="v", role=User.Role.VIEWER, password="x")
    tech = User(username="t", role=User.Role.TECHNICIAN, password="x")
    admin = User(username="a", role=User.Role.ADMIN, password="x", is_superuser=False)

    write_view = {"__name__": "create"}
    p_tech = IsTechnicianOrAdmin()
    p_admin = IsAdminOnly()

    assert p_tech.has_permission(_Req(viewer, "POST"), write_view) is False
    assert p_tech.has_permission(_Req(tech, "POST"), write_view) is True
    assert p_tech.has_permission(_Req(viewer, "GET"), write_view) is True
    assert p_admin.has_permission(_Req(tech, "POST"), write_view) is False
    assert p_admin.has_permission(_Req(admin, "DELETE"), write_view) is True
