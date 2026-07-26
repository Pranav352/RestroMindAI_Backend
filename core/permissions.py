from rest_framework import permissions
from .models import Restaurant, Category, MenuItem, Table, Order

class IsRestaurantOwner(permissions.BasePermission):
    """
    Custom permission to check if the user is the owner of the restaurant.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.role in ['owner', 'admin'] or request.user.is_superuser)
        )

    def has_object_permission(self, request, view, obj):
        # Allow superuser / admin bypass if necessary, but keep it owner-scoped for MVP
        if request.user.is_superuser:
            return True
            
        if isinstance(obj, Restaurant):
            return obj.owner == request.user
        elif isinstance(obj, Category):
            return obj.restaurant.owner == request.user
        elif isinstance(obj, MenuItem):
            return obj.category.restaurant.owner == request.user
        elif isinstance(obj, Table):
            return obj.restaurant.owner == request.user
        elif isinstance(obj, Order):
            return obj.restaurant.owner == request.user
        return False


class IsSystemAdmin(permissions.BasePermission):
    """
    Permission to allow access only to platform owners / admins.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.role == 'admin' or request.user.is_superuser))

