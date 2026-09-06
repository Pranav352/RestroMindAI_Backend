from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RestaurantViewSet,
    CategoryViewSet,
    MenuItemViewSet,
    TableViewSet,
    QRGenerateView,
    BulkQRGenerateView,
    QRDetailView,
    PublicMenuView,
    AdminDashboardStatsView,
    AdminUserViewSet,
    AdminRestaurantViewSet,
    OrderViewSet,
    OwnerDashboardStatsView
)

router = DefaultRouter()
router.register(r'restaurants', RestaurantViewSet, basename='restaurant')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'menu', MenuItemViewSet, basename='menu-item')
router.register(r'tables', TableViewSet, basename='table')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'admin/users', AdminUserViewSet, basename='admin-user')
router.register(r'admin/restaurants', AdminRestaurantViewSet, basename='admin-restaurant')

urlpatterns = [
    # Match the public menu first to avoid routing collision with menu-item detail (menu/<pk>/)
    path('menu/public/<int:restaurant_id>/', PublicMenuView.as_view(), name='public-menu'),
    path('qr/generate/', QRGenerateView.as_view(), name='qr-generate'),
    path('qr/bulk-generate/', BulkQRGenerateView.as_view(), name='qr-bulk-generate'),
    path('qr/<int:pk>/', QRDetailView.as_view(), name='qr-detail'),
    path('admin/stats/', AdminDashboardStatsView.as_view(), name='admin-stats'),
    path('owner/stats/', OwnerDashboardStatsView.as_view(), name='owner-stats'),
    path('', include(router.urls)),
]


