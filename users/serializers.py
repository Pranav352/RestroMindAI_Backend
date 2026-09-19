from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Subscription, SystemSetting

User = get_user_model()

class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    days_remaining = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = ('plan', 'status', 'start_date', 'end_date', 'days_remaining', 'is_active')


class UserSerializer(serializers.ModelSerializer):
    subscription = SubscriptionSerializer(read_only=True)
    has_recovery_pin = serializers.SerializerMethodField()
    quota_usage = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'role', 'subscription', 'has_recovery_pin', 'avatar', 'settings', 'quota_usage')

    def get_has_recovery_pin(self, obj):
        return bool(obj.recovery_pin)

    def get_quota_usage(self, obj):
        if obj.role != 'owner':
            return None

        try:
            from django.utils import timezone
            from core.models import Order, MenuItem, Table
            from .models import SystemSetting

            sys_settings = SystemSetting.get_settings()
            max_orders = sys_settings.free_tier_max_orders_per_month
            max_menu_items = sys_settings.free_tier_max_menu_items
            max_tables = sys_settings.free_tier_max_tables

            from datetime import timezone as dt_timezone
            import zoneinfo

            now_utc = timezone.now()
            local_tz = zoneinfo.ZoneInfo('Asia/Kolkata')
            now_local = now_utc.astimezone(local_tz)
            start_of_month_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_of_month = start_of_month_local.astimezone(dt_timezone.utc)

            orders_used = Order.objects.filter(
                restaurant__owner=obj,
                created_at__gte=start_of_month
            ).count()

            menu_items_count = MenuItem.objects.filter(
                category__restaurant__owner=obj
            ).count()

            tables_count = Table.objects.filter(
                restaurant__owner=obj
            ).count()

            orders_pct = round((orders_used / max_orders) * 100) if max_orders > 0 else 0
            menu_items_pct = round((menu_items_count / max_menu_items) * 100) if max_menu_items > 0 else 0
            tables_pct = round((tables_count / max_tables) * 100) if max_tables > 0 else 0

            return {
                'orders_used_this_month': orders_used,
                'max_orders_limit': max_orders,
                'orders_percentage': min(100, orders_pct),
                'menu_items_count': menu_items_count,
                'max_menu_items_limit': max_menu_items,
                'menu_items_percentage': min(100, menu_items_pct),
                'tables_count': tables_count,
                'max_tables_limit': max_tables,
                'tables_percentage': min(100, tables_pct),
                'tables_limit_reached': tables_count >= max_tables,
            }
        except Exception:
            return None


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    recovery_pin = serializers.CharField(required=False, allow_blank=True, write_only=True, min_length=4, max_length=6)
    avatar = serializers.ImageField(required=False, allow_null=True)
    settings = serializers.JSONField(required=False)

    class Meta:
        model = User
        fields = ('first_name', 'recovery_pin', 'avatar', 'settings')

    def update(self, instance, validated_data):
        recovery_pin = validated_data.pop('recovery_pin', None)
        if recovery_pin:
            instance.set_recovery_pin(recovery_pin)
        
        new_settings = validated_data.pop('settings', None)
        if new_settings is not None:
            current_settings = instance.settings or {}
            current_settings.update(new_settings)
            instance.settings = current_settings

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 32
PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 6


def validate_password_complexity(value):
    if len(value) < PASSWORD_MIN_LENGTH or len(value) > PASSWORD_MAX_LENGTH:
        raise serializers.ValidationError(f"Password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters long.")
    if not any(c.isupper() for c in value):
        raise serializers.ValidationError("Password must contain at least one uppercase letter (A-Z).")
    if not any(c.islower() for c in value):
        raise serializers.ValidationError("Password must contain at least one lowercase letter (a-z).")
    if not any(c.isdigit() for c in value):
        raise serializers.ValidationError("Password must contain at least one numeric digit (0-9).")
    if not any(not c.isalnum() for c in value):
        raise serializers.ValidationError("Password must contain at least one special character (!@#$%^&*...).")
    return value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    first_name = serializers.CharField(required=False, allow_blank=True, default='')
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, required=True)
    plan = serializers.ChoiceField(choices=Subscription.PLAN_CHOICES, required=False, default='free_trial')
    recovery_pin = serializers.CharField(required=False, allow_blank=True, write_only=True, min_length=PIN_MIN_LENGTH, max_length=PIN_MAX_LENGTH)


    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'role', 'plan', 'recovery_pin')

    def validate_password(self, value):
        return validate_password_complexity(value)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        first_name = validated_data.pop('first_name', '')
        recovery_pin = validated_data.pop('recovery_pin', '')
        plan = validated_data.pop('plan', 'free_trial')
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data['role'],
            first_name=first_name
        )
        if recovery_pin:
            user.set_recovery_pin(recovery_pin)
            user.save()
        if user.role == 'owner':
            subscription, created = Subscription.objects.get_or_create(
                user=user,
                defaults={'plan': plan, 'status': 'pending'}
            )
            if not created:
                subscription.plan = plan
                subscription.save()
        return user



class ResetPasswordWithPinSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    pin = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


    def validate_new_password(self, value):
        return validate_password_complexity(value)

    def validate(self, attrs):
        email = attrs.get('email')
        pin = attrs.get('pin')
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "No user found with this email address."})

        if not user.recovery_pin:
            raise serializers.ValidationError({"pin": "No recovery PIN set on this account. Please contact system admin for password reset assistance."})

        if not user.check_recovery_pin(pin):
            raise serializers.ValidationError({"pin": "Invalid recovery PIN."})

        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data['user']
        new_password = self.validated_data['new_password']
        user.set_password(new_password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):
        return validate_password_complexity(value)

    def validate(self, attrs):
        user = self.context['request'].user
        current_password = attrs.get('current_password')
        new_password = attrs.get('new_password')
        confirm_password = attrs.get('confirm_password')

        if not user.check_password(current_password):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})

        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "New password and confirmation password do not match."})

        if current_password == new_password:
            raise serializers.ValidationError({"new_password": "New password cannot be the same as your current password."})

        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user





