import os
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status, generics, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action

try:
    import qrcode
except ImportError:
    qrcode = None

from .models import Restaurant, Category, MenuItem, Table, Order, OrderItem
from .permissions import IsRestaurantOwner, IsSystemAdmin, HasTenantAccess
from users.permissions import HasActiveSubscription
from .serializers import (
    RestaurantSerializer,
    CategorySerializer,
    MenuItemSerializer,
    TableSerializer,
    PublicRestaurantSerializer,
    AdminUserSerializer,
    AdminRestaurantSerializer,
    OrderSerializer,
    OrderItemSerializer
)
from django.contrib.auth import get_user_model
User = get_user_model()


class RestaurantViewSet(viewsets.ModelViewSet):
    serializer_class = RestaurantSerializer
    permission_classes = [permissions.IsAuthenticated, IsRestaurantOwner, HasActiveSubscription]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == 'admin':
            tenant_id = self.request.headers.get('X-Tenant-ID')
            if tenant_id:
                return Restaurant.objects.filter(id=tenant_id)
            return Restaurant.objects.all()
        return Restaurant.objects.filter(owner=user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated, HasTenantAccess, HasActiveSubscription]

    def get_queryset(self):
        if hasattr(self.request, 'tenant_id'):
            return Category.objects.filter(restaurant_id=self.request.tenant_id)
        return Category.objects.none()


class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer
    permission_classes = [permissions.IsAuthenticated, HasTenantAccess, HasActiveSubscription]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        if hasattr(self.request, 'tenant_id'):
            return MenuItem.objects.filter(category__restaurant_id=self.request.tenant_id)
        return MenuItem.objects.none()


class QRGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveSubscription]


    def post(self, request):
        restaurant_id = request.data.get("restaurant_id")
        table_number = request.data.get("table_number", 1)

        if not restaurant_id:
            return Response(
                {"restaurant_id": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        restaurant = get_object_or_404(Restaurant, id=restaurant_id)

        # Enforce owner scope
        if restaurant.owner != request.user:
            return Response(
                {"error": "You do not own this restaurant."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            table_number = int(table_number)
            if table_number <= 0:
                raise ValueError()
        except ValueError:
            return Response(
                {"table_number": ["Must be a positive integer."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        if qrcode is None:
            return Response(
                {"error": "qrcode library is not installed on the system. Run: pip install qrcode[pil]"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


        # Get or create the Table
        table, created = Table.objects.get_or_create(
            restaurant=restaurant,
            table_number=table_number
        )

        # Build target public menu URL using FRONTEND_BASE_URL env var
        frontend_base = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:3000').rstrip('/')
        target_url = f"{frontend_base}/menu/{restaurant.id}?table={table.table_number}"

        # Generate QR Code image
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(target_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Save to media folder under qrcodes/
        qr_dir = os.path.join(settings.MEDIA_ROOT, 'qrcodes')
        os.makedirs(qr_dir, exist_ok=True)
        
        file_name = f"restaurant_{restaurant.id}_table_{table_number}.png"
        file_path = os.path.join(qr_dir, file_name)
        img.save(file_path)

        # Save relative URL/path in database
        table.qr_code = f"qrcodes/{file_name}"
        table.save()

        serializer = TableSerializer(table, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class QRDetailView(generics.RetrieveAPIView):
    serializer_class = TableSerializer
    permission_classes = [permissions.IsAuthenticated, HasTenantAccess]
    queryset = Table.objects.all()

    def get_queryset(self):
        if hasattr(self.request, 'tenant_id'):
            return Table.objects.filter(restaurant_id=self.request.tenant_id)
        return Table.objects.none()


class PublicMenuView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, restaurant_id):
        # Prefetch categories and menu items in a single query for sub-second performance
        try:
            restaurant = Restaurant.objects.prefetch_related(
                'categories',
                'categories__menu_items'
            ).get(id=restaurant_id)
        except Restaurant.DoesNotExist:
            return Response(
                {"error": "Restaurant not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = PublicRestaurantSerializer(restaurant, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminDashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSystemAdmin]

    def get(self, request):
        from users.models import Subscription
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Basic counts
        total_users = User.objects.count()
        total_restaurants = Restaurant.objects.count()
        total_categories = Category.objects.count()
        total_menu_items = MenuItem.objects.count()
        total_tables = Table.objects.count()

        # Growth metrics
        new_users_7_days = User.objects.filter(date_joined__gte=seven_days_ago).count()
        new_restaurants_7_days = Restaurant.objects.filter(created_at__gte=seven_days_ago).count()
        total_orders_today = Order.objects.filter(created_at__gte=today_start).count()

        # Subscriptions breakdown
        pending_approvals = Subscription.objects.filter(status='pending').count()
        active_subscriptions = Subscription.objects.filter(status='active').count()
        expired_subscriptions = Subscription.objects.filter(status__in=['expired', 'stopped']).count()

        # Recent 5 signups
        recent_users = User.objects.all().order_by('-date_joined')[:5]
        recent_signups_data = []
        for u in recent_users:
            sub_status = 'N/A'
            if hasattr(u, 'subscription'):
                sub_status = u.subscription.status
            recent_signups_data.append({
                "id": u.id,
                "email": u.email,
                "role": u.role,
                "date_joined": u.date_joined.isoformat(),
                "subscription_status": sub_status
            })

        stats = {
            "total_users": total_users,
            "total_restaurants": total_restaurants,
            "total_categories": total_categories,
            "total_menu_items": total_menu_items,
            "total_tables": total_tables,
            "new_users_7_days": new_users_7_days,
            "new_restaurants_7_days": new_restaurants_7_days,
            "total_orders_today": total_orders_today,
            "pending_approvals": pending_approvals,
            "active_subscriptions": active_subscriptions,
            "expired_subscriptions": expired_subscriptions,
            "recent_signups": recent_signups_data,
        }
        return Response(stats, status=status.HTTP_200_OK)



from rest_framework.pagination import PageNumberPagination

class AdminPagination(PageNumberPagination):
    page_size = int(os.getenv('ADMIN_PAGINATION_PAGE_SIZE', '10'))
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminUserViewSet(viewsets.ModelViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [permissions.IsAuthenticated, IsSystemAdmin]
    pagination_class = AdminPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['email']
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        queryset = User.objects.all().order_by('-date_joined')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(subscription__status=status_filter)
        return queryset



class AdminRestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.all().order_by('-created_at')
    serializer_class = AdminRestaurantSerializer
    permission_classes = [permissions.IsAuthenticated, IsSystemAdmin]
    pagination_class = AdminPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'owner__email']
    http_method_names = ['get', 'delete', 'head', 'options']


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer

    def get_permissions(self):
        if self.action in ['create', 'status', 'cancel']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), HasTenantAccess(), HasActiveSubscription()]

    def get_queryset(self):
        if hasattr(self.request, 'tenant_id'):
            return Order.objects.filter(restaurant_id=self.request.tenant_id).prefetch_related('items__menu_item')
        return Order.objects.none()

    def perform_update(self, serializer):
        order = serializer.save()
        new_status = serializer.validated_data.get('status')
        if new_status:
            # Propagate status to line items if whole order transitioned
            if new_status == 'served':
                order.items.exclude(status='cancelled').update(status='served')
            elif new_status == 'preparing':
                order.items.filter(status='pending').update(status='preparing')
            elif new_status == 'cancelled':
                order.items.update(status='cancelled')
                order.recalculate_total()
            elif new_status == 'completed':
                order.items.exclude(status='cancelled').update(status='served')

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def status(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({"error": "Tracking token is required."}, status=status.HTTP_400_BAD_REQUEST)
        order = get_object_or_404(Order, tracking_token=token)
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def cancel(self, request):
        token = request.data.get('token')
        if not token:
            return Response({"error": "Tracking token is required."}, status=status.HTTP_400_BAD_REQUEST)
        order = get_object_or_404(Order, tracking_token=token)
        
        # Check if entire order or any round can be cancelled
        pending_items = order.items.filter(status='pending')
        if not pending_items.exists() and order.status != 'pending':
            return Response(
                {"error": "Only pending orders or items can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if order.items.exclude(status='pending').exists():
            # Only cancel pending items
            pending_items.update(status='cancelled')
            order.recalculate_total()
            order.sync_overall_status()
        else:
            # Cancel entire order
            order.items.update(status='cancelled')
            order.status = 'cancelled'
            order.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsAuthenticated, HasTenantAccess, HasActiveSubscription])
    def update_round_status(self, request, pk=None):
        """Update the preparation status for all items within a specific round (e.g. Round 1 -> served)."""
        order = self.get_object()
        round_number = request.data.get('round')
        new_status = request.data.get('status')

        valid_statuses = ['pending', 'preparing', 'served', 'cancelled']
        if not round_number or new_status not in valid_statuses:
            return Response(
                {"error": f"round (int) and valid status ({', '.join(valid_statuses)}) are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            round_number = int(round_number)
        except ValueError:
            return Response({"error": "round must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        items_in_round = order.items.filter(round=round_number)
        if not items_in_round.exists():
            return Response({"error": f"No items found for round {round_number}."}, status=status.HTTP_404_NOT_FOUND)

        items_in_round.update(status=new_status)
        if new_status == 'cancelled':
            order.recalculate_total()

        # If a round is marked served, check if next round exists and automatically advance it to preparing
        if new_status == 'served':
            next_pending_items = order.items.filter(round__gt=round_number, status='pending')
            if next_pending_items.exists():
                next_round_num = next_pending_items.first().round
                order.items.filter(round=next_round_num, status='pending').update(status='preparing')

        order.sync_overall_status()
        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsAuthenticated, HasTenantAccess, HasActiveSubscription])
    def update_item_status(self, request, pk=None):
        """Update the status of an individual item within an order."""
        order = self.get_object()
        item_id = request.data.get('item_id')
        new_status = request.data.get('status')

        valid_statuses = ['pending', 'preparing', 'served', 'cancelled']
        if not item_id or new_status not in valid_statuses:
            return Response(
                {"error": f"item_id and valid status ({', '.join(valid_statuses)}) are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_item = get_object_or_404(order.items, id=item_id)
        order_item.status = new_status
        order_item.save(update_fields=['status'])

        if new_status == 'cancelled':
            order.recalculate_total()

        order.sync_overall_status()
        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)



class OwnerDashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasTenantAccess]

    def get(self, request):
        from django.utils import timezone
        from django.db.models import Sum

        tenant_id = getattr(request, 'tenant_id', None)
        if not tenant_id:
            restaurant = None
        else:
            restaurant = Restaurant.objects.filter(id=tenant_id).first()
            
        if not restaurant:
            return Response({
                "has_restaurant": False,
                "stats": {
                    "categories_count": 0,
                    "items_count": 0,
                    "tables_count": 0,
                    "today_orders_count": 0,
                    "today_pending_orders_count": 0,
                    "today_revenue": 0.0,
                },
                "recent_orders": []
            }, status=status.HTTP_200_OK)

        # Get counts
        categories_count = Category.objects.filter(restaurant=restaurant).count()
        items_count = MenuItem.objects.filter(category__restaurant=restaurant).count()
        tables_count = Table.objects.filter(restaurant=restaurant).count()

        # Date range for today (local day or UTC timezone aware)
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Today's orders
        today_orders = Order.objects.filter(restaurant=restaurant, created_at__gte=today_start)
        today_orders_count = today_orders.count()
        today_pending_orders_count = today_orders.filter(status='pending').count()
        
        # Today's revenue (sum total_price for completed or served orders)
        revenue_data = today_orders.filter(status__in=['served', 'completed']).aggregate(Sum('total_price'))
        today_revenue = float(revenue_data['total_price__sum'] or 0.0)

        # Get recent 5 orders
        recent_orders_qs = Order.objects.filter(restaurant=restaurant).order_by('-created_at')[:5]
        recent_orders_serializer = OrderSerializer(recent_orders_qs, many=True)

        return Response({
            "has_restaurant": True,
            "restaurant_name": restaurant.name,
            "stats": {
                "categories_count": categories_count,
                "items_count": items_count,
                "tables_count": tables_count,
                "today_orders_count": today_orders_count,
                "today_pending_orders_count": today_pending_orders_count,
                "today_revenue": today_revenue,
            },
            "recent_orders": recent_orders_serializer.data
        }, status=status.HTTP_200_OK)



