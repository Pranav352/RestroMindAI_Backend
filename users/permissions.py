from rest_framework import permissions

class HasActiveSubscription(permissions.BasePermission):
    """
    Allows read-only access for owners whose trial/subscription is not active.
    Allows write access only if their subscription is active.
    """
    message = "You must have an active subscription/trial to perform this action."

    def has_permission(self, request, view):
        # Authenticated requests check
        if not request.user or not request.user.is_authenticated:
            return False

        # Admin users have full access
        if request.user.is_staff or request.user.role == 'admin':
            return True

        # Customers are not bound by subscription limits (they only view anyway)
        if request.user.role == 'customer':
            return True

        # Check owner subscription
        if request.user.role == 'owner':
            # Safe methods (GET, HEAD, OPTIONS) are view-only, allowed even for inactive/expired/pending trials
            if request.method in permissions.SAFE_METHODS:
                return True

            subscription = getattr(request.user, 'subscription', None)
            if subscription and subscription.is_active():
                return True

        return False
