import os
import time
import json
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import viewsets, permissions, status, generics, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action

try:
    import qrcode
    import qrcode.image.svg
except ImportError:
    qrcode = None

from .models import Restaurant, Category, MenuItem, Table, Order, OrderItem
from .permissions import IsRestaurantOwner, IsSystemAdmin, HasTenantAccess
from .utils import get_local_timeframe_bounds, get_restaurant_tz
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


from rest_framework.pagination import PageNumberPagination


class TablePagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'page_size'
    max_page_size = 100


class TableViewSet(viewsets.ModelViewSet):
    serializer_class = TableSerializer
    permission_classes = [permissions.IsAuthenticated, HasTenantAccess, HasActiveSubscription]
    pagination_class = TablePagination

    def get_queryset(self):
        if hasattr(self.request, 'tenant_id'):
            qs = Table.objects.filter(restaurant_id=self.request.tenant_id)
            sec = self.request.query_params.get('section')
            if sec and sec != 'All':
                qs = qs.filter(section=sec)
            return qs.order_by('table_number')
        return Table.objects.none()


def get_frontend_base_url(request):
    """Dynamically determine frontend base URL from settings, request headers, or fallback."""
    frontend_base = getattr(settings, 'FRONTEND_BASE_URL', None)
    if frontend_base and frontend_base != 'http://localhost:3000':
        return frontend_base.rstrip('/')
    
    origin = request.headers.get('origin')
    if origin:
        return origin.rstrip('/')
    
    referer = request.headers.get('referer')
    if referer:
        from urllib.parse import urlparse
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
            
    return getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:3000').rstrip('/')


def generate_table_qr_code(restaurant, table_number, request, section="Main Area", label=""):
    section = section or "Main Area"
    table, created = Table.objects.get_or_create(
        restaurant=restaurant,
        section=section,
        table_number=table_number,
        defaults={'label': label}
    )
    if not created and label:
        table.label = label
        table.save(update_fields=['label'])

    frontend_base = get_frontend_base_url(request)
    target_url = f"{frontend_base}/menu/{restaurant.id}?table={table.table_number}"

    if qrcode is not None:
        try:
            # Generate PNG raster image
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(target_url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            qr_dir = os.path.join(settings.MEDIA_ROOT, 'qrcodes')
            os.makedirs(qr_dir, exist_ok=True)
            
            sec_slug = section.lower().replace(' ', '_')
            file_name_png = f"restaurant_{restaurant.id}_{sec_slug}_table_{table_number}.png"
            file_path_png = os.path.join(qr_dir, file_name_png)
            img.save(file_path_png)
            table.qr_code = f"qrcodes/{file_name_png}"

            # Generate SVG Vector image
            try:
                factory = qrcode.image.svg.SvgImage
                svg_img = qrcode.make(target_url, image_factory=factory)
                file_name_svg = f"restaurant_{restaurant.id}_{sec_slug}_table_{table_number}.svg"
                file_path_svg = os.path.join(qr_dir, file_name_svg)
                svg_img.save(file_path_svg)
                table.qr_code_svg = f"qrcodes/{file_name_svg}"
            except Exception as err:
                print(f"SVG QR Generation Warning: {err}")

            table.save()
        except Exception as img_err:
            print(f"PNG QR Generation Warning: {img_err}")
            sec_slug = section.lower().replace(' ', '_')
            table.qr_code = f"qrcodes/restaurant_{restaurant.id}_{sec_slug}_table_{table_number}.png"
            table.save()

    return table


def check_table_quota_limit(restaurant, new_tables_count=1):
    """Verify if owner on Free Trial can generate requested new tables."""
    subscription = getattr(restaurant.owner, 'subscription', None)
    if subscription and subscription.plan == 'free_trial':
        from users.models import SystemSetting
        sys_settings = SystemSetting.get_settings()
        max_tables = sys_settings.free_tier_max_tables
        
        current_tables = Table.objects.filter(restaurant=restaurant).count()
        if current_tables + new_tables_count > max_tables:
            return False, f"Free Trial table limit reached ({current_tables}/{max_tables} QR codes used). Upgrade your subscription to generate more tables."
            
    return True, None


class QRGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveSubscription]

    def post(self, request):
        restaurant_id = request.data.get("restaurant_id")
        table_number = request.data.get("table_number", 1)
        section = request.data.get("section", "Main Area")
        label = request.data.get("label", "")

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

        # Check Free Trial quota if creating a new table
        table_exists = Table.objects.filter(restaurant=restaurant, section=section, table_number=table_number).exists()
        if not table_exists:
            quota_ok, error_msg = check_table_quota_limit(restaurant, 1)
            if not quota_ok:
                return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)

        table = generate_table_qr_code(restaurant, table_number, request, section=section, label=label)

        serializer = TableSerializer(table, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class BulkQRGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveSubscription]

    def post(self, request):
        restaurant_id = request.data.get("restaurant_id")
        start_table = request.data.get("start_table", 1)
        count = request.data.get("count", 5)
        section = request.data.get("section", "Main Area")

        if not restaurant_id:
            return Response(
                {"restaurant_id": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        restaurant = get_object_or_404(Restaurant, id=restaurant_id)

        if restaurant.owner != request.user:
            return Response(
                {"error": "You do not own this restaurant."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            start_table = int(start_table)
            count = int(count)
            if start_table <= 0 or count <= 0 or count > 50:
                raise ValueError()
        except ValueError:
            return Response(
                {"error": "start_table must be >= 1 and count must be between 1 and 50."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if qrcode is None:
            return Response(
                {"error": "qrcode library is not installed on the system."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Check Free Trial quota for new tables in bulk request
        existing_nums = set(Table.objects.filter(restaurant=restaurant, section=section).values_list('table_number', flat=True))
        new_count = sum(1 for num in range(start_table, start_table + count) if num not in existing_nums)

        if new_count > 0:
            quota_ok, error_msg = check_table_quota_limit(restaurant, new_count)
            if not quota_ok:
                return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)

        generated_tables = []
        for num in range(start_table, start_table + count):
            lbl = f"{section} #{num}" if section != "Main Area" else ""
            table = generate_table_qr_code(restaurant, num, request, section=section, label=lbl)
            generated_tables.append(table)

        serializer = TableSerializer(generated_tables, many=True, context={"request": request})
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
        from datetime import timedelta, timezone as dt_timezone
        import zoneinfo

        now_utc = timezone.now()
        local_tz = zoneinfo.ZoneInfo('Asia/Kolkata')
        now_local = now_utc.astimezone(local_tz)
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_local.astimezone(dt_timezone.utc)
        seven_days_ago = now_utc - timedelta(days=7)

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
        if self.action in ['create', 'status', 'cancel', 'check_table', 'stream']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), HasTenantAccess(), HasActiveSubscription()]

    def get_queryset(self):
        if hasattr(self.request, 'tenant_id'):
            restaurant = Restaurant.objects.filter(id=self.request.tenant_id).first()
            queryset = Order.objects.filter(restaurant_id=self.request.tenant_id).prefetch_related('items__menu_item')
            date_param = self.request.query_params.get('date') or self.request.query_params.get('timeframe')
            if date_param and restaurant:
                date_str = str(date_param).strip().lower()
                if date_str not in ['all', 'all_time']:
                    bounds = get_local_timeframe_bounds(restaurant, date_str)
                    queryset = queryset.filter(created_at__gte=bounds['start_date'], created_at__lte=bounds['end_date'])
            return queryset.order_by('-created_at')
        return Order.objects.none()

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def stream(self, request):
        """
        Server-Sent Events (SSE) stream for instant sub-second live order arrival.
        Streams new order arrivals and status events directly to the restaurant dashboard.
        """
        token = request.query_params.get('token')
        tenant_id = request.query_params.get('tenant_id')
        user = None

        if token:
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                validated_token = AccessToken(token)
                user_id = validated_token['user_id']
                user = User.objects.filter(id=user_id).first()
            except Exception as e:
                print('Stream token validation notice:', e)

        if not user and request.user and request.user.is_authenticated:
            user = request.user

        if not user:
            return Response({"error": "Authentication token required for order stream."}, status=status.HTTP_401_UNAUTHORIZED)

        restaurant_id = tenant_id or getattr(request, 'tenant_id', None)
        if not restaurant_id:
            if hasattr(user, 'restaurant') and user.restaurant:
                restaurant_id = user.restaurant.id
            elif user.role == 'owner':
                rest = Restaurant.objects.filter(owner=user).first()
                if rest:
                    restaurant_id = rest.id

        if not restaurant_id:
            return Response({"error": "No associated restaurant tenant found."}, status=status.HTTP_400_BAD_REQUEST)

        def event_generator():
            last_order_id = Order.objects.filter(restaurant_id=restaurant_id).order_by('-id').values_list('id', flat=True).first() or 0
            last_check_time = timezone.now()
            yield f"event: connected\ndata: {json.dumps({'status': 'stream_active', 'restaurant_id': restaurant_id})}\n\n"
            
            ticks = 0
            while True:
                ticks += 1
                try:
                    now = timezone.now()
                    new_orders = Order.objects.filter(restaurant_id=restaurant_id, id__gt=last_order_id).order_by('id')
                    updated_orders = Order.objects.filter(
                        restaurant_id=restaurant_id,
                        id__lte=last_order_id,
                        updated_at__gt=last_check_time
                    ).order_by('updated_at')

                    has_events = False
                    if new_orders.exists():
                        for order in new_orders:
                            last_order_id = max(last_order_id, order.id)
                            serializer = OrderSerializer(order)
                            yield f"event: new_order\ndata: {json.dumps(serializer.data)}\n\n"
                        has_events = True

                    if updated_orders.exists():
                        for order in updated_orders:
                            serializer = OrderSerializer(order)
                            yield f"event: order_updated\ndata: {json.dumps(serializer.data)}\n\n"
                        has_events = True

                    if has_events:
                        last_check_time = now
                    elif ticks % 5 == 0:
                        yield ": keepalive\n\n"
                except Exception as e:
                    yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                
                time.sleep(2)

        response = StreamingHttpResponse(event_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    def perform_create(self, serializer):
        order = serializer.save()
        try:
            from core.services.push_service import send_order_push_notification
            send_order_push_notification(
                restaurant_id=order.restaurant_id,
                title=f"🚨 New Order #{order.id} (Table {order.table_number})",
                message=f"New order placed by {order.customer_name or 'Customer'} on Table {order.table_number}.",
                url="/orders"
            )
        except Exception as e:
            print("Failed to dispatch push notification on create:", e)

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
                order.is_paid = True
                order.save(update_fields=['is_paid'])

            try:
                from core.services.push_service import send_order_push_notification
                send_order_push_notification(
                    restaurant_id=order.restaurant_id,
                    title=f"Order #{order.id} Status: {new_status.title()}",
                    message=f"Order for Table {order.table_number} is now {new_status}.",
                    url="/orders"
                )
            except Exception as e:
                print("Failed to dispatch push notification on update:", e)

    @action(detail=True, methods=['patch'])
    def recover_payment(self, request, pk=None):
        """Mark a voided/walkout order as recovered when customer pays later via UPI link or cash."""
        order = self.get_object()
        payment_method = request.data.get('payment_method', 'upi')
        payment_txn_id = request.data.get('payment_txn_id', '')

        order.is_recovered = True
        order.is_paid = True
        order.payment_method = payment_method
        if payment_txn_id:
            order.payment_txn_id = payment_txn_id
        order.save(update_fields=['is_recovered', 'is_paid', 'payment_method', 'payment_txn_id', 'updated_at'])

        return Response({
            "message": "Payment marked as recovered successfully.",
            "order": OrderSerializer(order).data
        })

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def check_table(self, request):
        """Check if a table currently has an active open order and verify table host status."""
        restaurant_id = request.query_params.get('restaurant_id')
        table_number = request.query_params.get('table_number')
        token = request.query_params.get('token')

        if not restaurant_id or not table_number:
            return Response(
                {"error": "restaurant_id and table_number query params are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            table_number = int(table_number)
            restaurant_id = int(restaurant_id)
        except ValueError:
            return Response(
                {"error": "restaurant_id and table_number must be integers."},
                status=status.HTTP_400_BAD_REQUEST
            )

        active_order = Order.objects.filter(
            restaurant_id=restaurant_id,
            table_number=table_number,
            status__in=['pending', 'preparing', 'served']
        ).first()

        if active_order:
            is_table_host = bool(token and str(active_order.tracking_token) == str(token))
            return Response({
                "is_occupied": True,
                "is_table_host": is_table_host,
                "table_number": table_number,
                "order_id": active_order.id,
                "order_status": active_order.status,
                "tracking_token": str(active_order.tracking_token) if is_table_host else None
            }, status=status.HTTP_200_OK)

        return Response({
            "is_occupied": False,
            "is_table_host": False,
            "table_number": table_number,
            "order_id": None,
            "order_status": None
        }, status=status.HTTP_200_OK)

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
        from django.db.models import Sum, F, Q
        from datetime import timedelta, timezone as dt_timezone

        tenant_id = getattr(request, 'tenant_id', None)
        restaurant = None
        if tenant_id:
            restaurant = Restaurant.objects.filter(id=tenant_id).first()
        if not restaurant and request.user and request.user.is_authenticated:
            restaurant = Restaurant.objects.filter(owner=request.user).first()
            
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
                    "revenue_delta": 0.0,
                    "orders_delta": 0.0,
                    "aov": 0.0,
                    "occupancy_rate": 0.0,
                    "cancellation_rate": 0.0,
                    "timeframe": "today",
                    "timeframe_label": "Today"
                },
                "top_selling_items": [],
                "hourly_sales": [],
                "recent_orders": []
            }, status=status.HTTP_200_OK)

        timeframe = request.query_params.get('timeframe', 'today').lower()
        bounds = get_local_timeframe_bounds(restaurant, timeframe)

        start_date = bounds['start_date']
        end_date = bounds['end_date']
        prev_start_date = bounds['prev_start_date']
        prev_end_date = bounds['prev_end_date']
        timeframe_label = bounds['timeframe_label']
        now_local = bounds['now_local']

        # General counts
        categories_count = Category.objects.filter(restaurant=restaurant).count()
        items_count = MenuItem.objects.filter(category__restaurant=restaurant).count()
        tables_count = Table.objects.filter(restaurant=restaurant).count()

        # Orders querysets for timeframe & comparison
        period_orders = Order.objects.filter(restaurant=restaurant, created_at__gte=start_date, created_at__lte=end_date)
        prev_orders = Order.objects.filter(restaurant=restaurant, created_at__gte=prev_start_date, created_at__lte=prev_end_date)

        orders_count = period_orders.count()
        prev_orders_count = prev_orders.count()
        pending_orders_count = period_orders.filter(status='pending').count()

        # Revenue calculation (incorporates completed sales + recovered walkouts!)
        revenue_filter = Q(status__in=['served', 'completed']) | Q(status='cancelled', is_recovered=True)
        
        revenue_aggregate = period_orders.filter(revenue_filter).aggregate(Sum('total_price'))
        period_revenue = float(revenue_aggregate['total_price__sum'] or 0.0)

        prev_revenue_aggregate = prev_orders.filter(revenue_filter).aggregate(Sum('total_price'))
        prev_revenue = float(prev_revenue_aggregate['total_price__sum'] or 0.0)

        # Trend Deltas calculation
        if prev_revenue > 0:
            revenue_delta = round(((period_revenue - prev_revenue) / prev_revenue * 100), 1)
        else:
            revenue_delta = 100.0 if period_revenue > 0 else 0.0

        if prev_orders_count > 0:
            orders_delta = round(((orders_count - prev_orders_count) / prev_orders_count * 100), 1)
        else:
            orders_delta = 100.0 if orders_count > 0 else 0.0

        # KPI 1: Average Order Value (AOV)
        completed_count = period_orders.filter(revenue_filter).count()
        aov = round((period_revenue / completed_count), 2) if completed_count > 0 else 0.0

        # KPI 2: Active Table Occupancy Rate %
        active_tables_set = set(
            Order.objects.filter(
                restaurant=restaurant,
                status__in=['pending', 'preparing', 'served']
            ).values_list('table_number', flat=True)
        )
        occupied_count = len([t for t in active_tables_set if t])
        occupancy_rate = round((occupied_count / tables_count * 100), 1) if tables_count > 0 else 0.0

        # KPI 3: Order Cancellation Rate %
        cancelled_unrecovered_count = period_orders.filter(status='cancelled', is_recovered=False).count()
        cancellation_rate = round((cancelled_unrecovered_count / orders_count * 100), 1) if orders_count > 0 else 0.0

        # Top 5 Best-Selling Dishes
        top_items_qs = OrderItem.objects.filter(
            order__restaurant=restaurant,
            order__created_at__gte=start_date,
            order__created_at__lte=end_date
        ).exclude(status='cancelled').values('menu_item__name').annotate(
            total_qty=Sum('quantity'),
            total_sales=Sum(F('price') * F('quantity'))
        ).order_by('-total_qty')[:5]

        top_selling_items = [
            {
                "name": item['menu_item__name'] or 'Unknown Item',
                "total_qty": item['total_qty'],
                "total_sales": float(item['total_sales'] or 0.0)
            }
            for item in top_items_qs
        ]

        # Hourly / Daily Sales Breakdown in Restaurant Local Operating Time
        hourly_sales = []
        is_single_day = timeframe in ['today', 'yesterday'] or bounds.get('is_custom', False)

        if is_single_day:
            start_local_day = start_date.astimezone(bounds['restaurant_tz']).replace(hour=0, minute=0, second=0, microsecond=0)
            for h in range(0, 24, 2):
                h_start_local = start_local_day.replace(hour=h, minute=0, second=0, microsecond=0)
                h_end_local = start_local_day.replace(hour=min(h+1, 23), minute=59, second=59, microsecond=999999)
                h_start_utc = h_start_local.astimezone(dt_timezone.utc)
                h_end_utc = h_end_local.astimezone(dt_timezone.utc)

                h_orders = period_orders.filter(created_at__gte=h_start_utc, created_at__lte=h_end_utc)
                h_revenue = float(h_orders.filter(revenue_filter).aggregate(Sum('total_price'))['total_price__sum'] or 0.0)

                if h == 0:
                    hour_label = "12 AM"
                elif h < 12:
                    hour_label = f"{h} AM"
                elif h == 12:
                    hour_label = "12 PM"
                else:
                    hour_label = f"{h - 12} PM"

                hourly_sales.append({
                    "label": hour_label,
                    "revenue": h_revenue,
                    "orders": h_orders.count()
                })
        else:
            num_days = 7 if timeframe == '7d' else 30
            for d in range(num_days - 1, -1, -1):
                day_start_local = (now_local - timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
                day_end_local = day_start_local.replace(hour=23, minute=59, second=59, microsecond=999999)
                day_start_utc = day_start_local.astimezone(dt_timezone.utc)
                day_end_utc = day_end_local.astimezone(dt_timezone.utc)

                d_orders = period_orders.filter(created_at__gte=day_start_utc, created_at__lte=day_end_utc)
                d_revenue = float(d_orders.filter(revenue_filter).aggregate(Sum('total_price'))['total_price__sum'] or 0.0)

                hourly_sales.append({
                    "label": day_start_local.strftime("%a, %b %d"),
                    "revenue": d_revenue,
                    "orders": d_orders.count()
                })

        # Peak Hour Calculation
        peak_hour = None
        if hourly_sales:
            max_slot = max(hourly_sales, key=lambda x: (x['revenue'], x['orders']))
            if max_slot and (max_slot['revenue'] > 0 or max_slot['orders'] > 0):
                peak_hour = {
                    "label": max_slot['label'],
                    "revenue": max_slot['revenue'],
                    "orders": max_slot['orders']
                }

        # Category Sales Breakdown
        cat_qs = OrderItem.objects.filter(
            order__restaurant=restaurant,
            order__created_at__gte=start_date,
            order__created_at__lte=end_date
        ).exclude(status='cancelled').values('menu_item__category__name').annotate(
            total_sales=Sum(F('price') * F('quantity')),
            total_qty=Sum('quantity')
        ).order_by('-total_sales')

        total_cat_sales_sum = sum(float(c['total_sales'] or 0.0) for c in cat_qs)
        category_sales = []
        for c in cat_qs[:5]:
            c_sales = float(c['total_sales'] or 0.0)
            c_percent = round((c_sales / total_cat_sales_sum * 100), 1) if total_cat_sales_sum > 0 else 0.0
            category_sales.append({
                "name": c['menu_item__category__name'] or 'General',
                "total_sales": c_sales,
                "total_qty": c['total_qty'],
                "percentage": c_percent
            })

        # Recent 5 orders feed
        recent_orders_qs = Order.objects.filter(restaurant=restaurant).order_by('-created_at')[:5]
        recent_orders_serializer = OrderSerializer(recent_orders_qs, many=True)

        return Response({
            "has_restaurant": True,
            "restaurant_id": restaurant.id,
            "restaurant_name": restaurant.name,
            "currency": restaurant.currency,
            "is_accepting_orders": restaurant.is_accepting_orders,
            "stats": {
                "categories_count": categories_count,
                "items_count": items_count,
                "tables_count": tables_count,
                "today_orders_count": orders_count,
                "today_pending_orders_count": pending_orders_count,
                "today_revenue": period_revenue,
                "revenue_delta": revenue_delta,
                "orders_delta": orders_delta,
                "aov": aov,
                "occupancy_rate": occupancy_rate,
                "cancellation_rate": cancellation_rate,
                "timeframe": timeframe,
                "timeframe_label": timeframe_label
            },
            "top_selling_items": top_selling_items,
            "category_sales": category_sales,
            "peak_hour": peak_hour,
            "hourly_sales": hourly_sales,
            "recent_orders": recent_orders_serializer.data
        }, status=status.HTTP_200_OK)



