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


class HasTenantAccess(permissions.BasePermission):
    """
    Validates the X-Tenant-ID header and ensures the user has access to it.
    Sets request.tenant_id if valid.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        tenant_id = request.headers.get('X-Tenant-ID')
        if not tenant_id:
            # If no tenant ID is provided, we allow the request to proceed.
            # Endpoints will gracefully handle the missing request.tenant_id
            # (e.g. by returning empty querysets or a "no restaurant" payload).
            return True

        try:
            tenant_id = int(tenant_id)
        except ValueError:
            return False

        if request.user.role == 'admin' or request.user.is_superuser:
            request.tenant_id = tenant_id
            return True

        # For owners, ensure they own the requested tenant
        if Restaurant.objects.filter(id=tenant_id, owner=request.user).exists():
            request.tenant_id = tenant_id
            return True
            
        return False

    def has_object_permission(self, request, view, obj):
        # We don't really need object permissions if we strictly filter the queryset by tenant_id,
        # but as a fallback, ensure the object belongs to the tenant.
        tenant_id = getattr(request, 'tenant_id', None)
        if not tenant_id:
            return False
            
        if isinstance(obj, Restaurant):
            return obj.id == tenant_id
        elif isinstance(obj, Category):
            return obj.restaurant_id == tenant_id
        elif isinstance(obj, MenuItem):
            return obj.category.restaurant_id == tenant_id
        elif isinstance(obj, Table):
            return obj.restaurant_id == tenant_id
        elif isinstance(obj, Order):
            return obj.restaurant_id == tenant_id
        return False

