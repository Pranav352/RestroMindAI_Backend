from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.utils import timezone
from .serializers import RegisterSerializer, UserSerializer, ResetPasswordWithPinSerializer, UserProfileUpdateSerializer, ChangePasswordSerializer, SystemSettingSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer
    throttle_scope = 'auth'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "success": True,
                "message": "User registered successfully.",
                "user": UserSerializer(user).data
            },
            status=status.HTTP_201_CREATED
        )


class ResetPasswordWithPinView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_scope = 'auth'

    def post(self, request):
        serializer = ResetPasswordWithPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "success": True,
                "message": "Password has been reset successfully. You can now log in with your new password."
            },
            status=status.HTTP_200_OK
        )



class LoginView(TokenObtainPairView):
    throttle_scope = 'auth'


class LogoutView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"success": True, "message": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT
            )
        except Exception as e:
            return Response(
                {"error": "Invalid token or already blacklisted."},
                status=status.HTTP_400_BAD_REQUEST
            )


from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

class MeView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "success": True,
                "message": "Profile updated successfully.",
                "user": UserSerializer(user).data
            },
            status=status.HTTP_200_OK
        )


class MockUpgradeView(APIView):

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        user = request.user
        if user.role == 'owner':
            user.trial_started_at = timezone.now()
            user.save()
            return Response(
                {
                    "success": True, 
                    "message": "Free trial reset successfully. 7 additional days granted!",
                    "user": UserSerializer(user).data
                },
                status=status.HTTP_200_OK
            )
        return Response(
            {"error": "Only owner accounts can reset trial status."},
            status=status.HTTP_400_BAD_REQUEST
        )


class ChangePasswordView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "success": True,
                "message": "Password changed successfully."
            },
            status=status.HTTP_200_OK
        )


class SystemSettingView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get(self, request):
        from .models import SystemSetting
        settings_obj = SystemSetting.get_settings()
        serializer = SystemSettingSerializer(settings_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        if request.user.role != 'admin':
            return Response({"error": "Only admin users can update global system settings."}, status=status.HTTP_403_FORBIDDEN)
        from .models import SystemSetting
        settings_obj = SystemSetting.get_settings()
        serializer = SystemSettingSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class SystemDiagnosticsView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        if request.user.role != 'admin':
            return Response({"error": "Only super admin users can view system diagnostics."}, status=status.HTTP_403_FORBIDDEN)

        import time
        import platform
        import django
        from django.db import connection
        from django.utils import timezone
        from .models import User, Subscription, SystemSetting

        # 1. Test Database Latency
        start_time = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        db_latency_ms = round((time.time() - start_time) * 1000, 2)

        # 2. Database Stats & Metrics
        total_users = User.objects.count()
        total_owners = User.objects.filter(role='owner').count()
        total_staff = User.objects.filter(role='staff').count()
        active_subscriptions = Subscription.objects.filter(status='active').count()
        pending_subscriptions = Subscription.objects.filter(status='pending').count()
        
        # 3. System & Runtime Environment Information
        db_vendor = connection.vendor.upper()
        python_ver = platform.python_version()
        django_ver = django.get_version()
        os_info = f"{platform.system()} {platform.release()}"
        sys_settings = SystemSetting.get_settings()

        return Response({
            "status": "operational",
            "db_status": "connected",
            "db_vendor": db_vendor,
            "db_latency_ms": db_latency_ms,
            "python_version": python_ver,
            "django_version": django_ver,
            "os_info": os_info,
            "metrics": {
                "total_users": total_users,
                "total_owners": total_owners,
                "total_staff": total_staff,
                "active_subscriptions": active_subscriptions,
                "pending_subscriptions": pending_subscriptions,
            },
            "maintenance": {
                "mode": sys_settings.maintenance_mode,
                "status": sys_settings.maintenance_status,
                "locked": sys_settings.lock_platform,
            },
            "timestamp": timezone.now().isoformat()
        }, status=status.HTTP_200_OK)



