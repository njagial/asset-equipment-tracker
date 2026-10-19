from rest_framework.permissions import SAFE_METHODS, BasePermission


class RolePermission(BasePermission):
    """DRF permission gated on the custom User.role enum.

    Read methods are allowed for every authenticated user; write methods
    require the minimum role ranks listed in `write_roles`.
    """

    write_roles: set[str] = set()
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        rank = {"VIEWER": 0, "TECHNICIAN": 1, "ADMIN": 2}
        user_rank = rank.get(getattr(request.user, "role", "VIEWER"), 0)
        return any(user_rank >= rank[r] for r in self.write_roles)


class IsTechnicianOrAdmin(RolePermission):
    write_roles = {"TECHNICIAN", "ADMIN"}


class IsAdminOnly(RolePermission):
    write_roles = {"ADMIN"}


# --- Django web-layer helpers -------------------------------------------------
ROLE_RANK = {"VIEWER": 0, "TECHNICIAN": 1, "ADMIN": 2}


def min_role(*roles):
    """Decorator factory used by HTMX views, mirroring the DRF gates."""

    def has(user):
        if not user.is_authenticated:
            return False
        uname = user.role
        return any(ROLE_RANK[uname] >= ROLE_RANK[r] for r in roles)

    return has
