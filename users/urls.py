from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, LoginView, LogoutView, MeView, MockUpgradeView, ResetPasswordWithPinView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', LoginView.as_view(), name='auth_login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('me/', MeView.as_view(), name='auth_me'),
    path('mock-upgrade/', MockUpgradeView.as_view(), name='auth_mock_upgrade'),
    path('reset-password-with-pin/', ResetPasswordWithPinView.as_view(), name='auth_reset_password_with_pin'),
]

