import pytest
from django.contrib.auth.models import AnonymousUser

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


def test_rolepermission_blocks_anonymous():
    view = {"__name__": "list"}
    assert IsTechnicianOrAdmin().has_permission(_Req(AnonymousUser(), "GET"), view) is False
    assert IsAdminOnly().has_permission(_Req(AnonymousUser(), "POST"), view) is False


def test_drf_permission_never_grants_anonymous_writes():
    p = IsTechnicianOrAdmin()
    assert p.has_permission(_Req(AnonymousUser(), "DELETE"), {"__name__": "destroy"}) is False


def test_is_admin_role_property():
    assert User(username="a", role=User.Role.ADMIN).is_admin_role
    assert User(username="s", role=User.Role.VIEWER, is_superuser=True).is_admin_role
    assert not User(username="v", role=User.Role.VIEWER).is_admin_role


def test_min_role_anonymous_is_denied():
    assert not min_role("VIEWER")(AnonymousUser())
    assert not min_role("TECHNICIAN", "ADMIN")(AnonymousUser())


def test_min_role_tier_boundaries():
    viewer = User(username="v", role=User.Role.VIEWER, password="x")
    tech = User(username="t", role=User.Role.TECHNICIAN, password="x")
    admin = User(username="a", role=User.Role.ADMIN, password="x")

    assert min_role("VIEWER")(viewer)
    assert not min_role("TECHNICIAN")(viewer)
    assert min_role("VIEWER", "TECHNICIAN")(tech)
    assert min_role("VIEWER", "TECHNICIAN", "ADMIN")(admin)
    assert not admin.is_superuser  # role != superuser; rank map drives the gate
