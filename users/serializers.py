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

    class Meta:
        model = User
        fields = ('id', 'email', 'role', 'subscription')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, required=True)
    plan = serializers.ChoiceField(choices=Subscription.PLAN_CHOICES, required=False, default='free_trial')

    class Meta:
        model = User
        fields = ('email', 'password', 'role', 'plan')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        plan = validated_data.pop('plan', 'free_trial')
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data['role']
        )
        if user.role == 'owner':
            subscription, created = Subscription.objects.get_or_create(
                user=user,
                defaults={'plan': plan, 'status': 'pending'}
            )
            if not created:
                subscription.plan = plan
                subscription.save()
        return user

