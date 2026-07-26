from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import RegisterSerializer, UserSerializer

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


class MeView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


from django.utils import timezone

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
