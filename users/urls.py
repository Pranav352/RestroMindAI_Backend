from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, LoginView, LogoutView, MeView, MockUpgradeView,
    ResetPasswordWithPinView, ChangePasswordView, SystemSettingView,
    SystemDiagnosticsView, VapidPublicKeyView, SubscribePushView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', LoginView.as_view(), name='auth_login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('me/', MeView.as_view(), name='auth_me'),
    path('change-password/', ChangePasswordView.as_view(), name='auth_change_password'),
    path('system-settings/', SystemSettingView.as_view(), name='system_settings'),
    path('system-diagnostics/', SystemDiagnosticsView.as_view(), name='system_diagnostics'),
    path('mock-upgrade/', MockUpgradeView.as_view(), name='auth_mock_upgrade'),
    path('reset-password-with-pin/', ResetPasswordWithPinView.as_view(), name='auth_reset_password_with_pin'),
    
    # Web Push Notification endpoints
    path('push/vapid-public-key/', VapidPublicKeyView.as_view(), name='push_vapid_public_key'),
    path('push/subscribe/', SubscribePushView.as_view(), name='push_subscribe'),
]



