from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Subscription

User = get_user_model()

class SubscriptionSerializer(serializers.ModelSerializer):
    days_remaining = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = ('plan', 'status', 'start_date', 'end_date', 'days_remaining', 'is_active')


class UserSerializer(serializers.ModelSerializer):
    subscription = SubscriptionSerializer(read_only=True)
    has_recovery_pin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'role', 'subscription', 'has_recovery_pin')

    def get_has_recovery_pin(self, obj):
        return bool(obj.recovery_pin)


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    recovery_pin = serializers.CharField(required=False, allow_blank=True, write_only=True, min_length=4, max_length=6)

    class Meta:
        model = User
        fields = ('first_name', 'recovery_pin')

    def update(self, instance, validated_data):
        recovery_pin = validated_data.pop('recovery_pin', None)
        if recovery_pin:
            instance.set_recovery_pin(recovery_pin)
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




