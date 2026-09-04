from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from datetime import timedelta


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = [
        ('customer', 'Customer'),
        ('owner', 'Owner'),
        ('admin', 'Admin'),
    ]

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')

    recovery_pin = models.CharField(max_length=128, blank=True, null=True)
    avatar = models.ImageField(upload_to='user_avatars/', max_length=500, null=True, blank=True)
    settings = models.JSONField(default=dict, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def set_recovery_pin(self, raw_pin):
        from django.contrib.auth.hashers import make_password
        if raw_pin:
            self.recovery_pin = make_password(str(raw_pin))

    def check_recovery_pin(self, raw_pin):
        from django.contrib.auth.hashers import check_password
        if not self.recovery_pin or not raw_pin:
            return False
        return check_password(str(raw_pin), self.recovery_pin)

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"


class Subscription(models.Model):
    PLAN_CHOICES = [
        ('free_trial', 'Free Trial'),
        ('premium', 'Premium (Coming Soon)'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('stopped', 'Stopped by Admin'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free_trial')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_active(self):
        if self.status != 'active':
            return False
        if self.end_date and timezone.now() > self.end_date:
            return False
        return True

    def days_remaining(self):
        if not self.end_date or self.status != 'active':
            return 0
        remaining = self.end_date - timezone.now()
        # Using ceil to give a full day if there are hours left
        days = (self.end_date - timezone.now()).days
        # If remaining is positive and there is fraction of a day, add 1 day
        if remaining.total_seconds() > 0 and remaining.seconds > 0:
            days += 1
        return max(0, days)

    def __str__(self):
        return f"{self.user.email} - {self.get_plan_display()} ({self.get_status_display()})"


class SystemSetting(models.Model):
    MAINTENANCE_STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    maintenance_mode = models.BooleanField(default=False)
    maintenance_status = models.CharField(max_length=20, choices=MAINTENANCE_STATUS_CHOICES, default='in_progress')
    lock_platform = models.BooleanField(default=False)
    estimated_completion = models.CharField(max_length=100, blank=True, default='Today at 3:00 AM UTC')
    banner_severity = models.CharField(max_length=20, default='warning')
    banner_text = models.TextField(default='Scheduled system maintenance in progress.')
    default_trial_days = models.IntegerField(default=7)
    auto_approve_owners = models.BooleanField(default=True)
    default_currency = models.CharField(max_length=10, default='USD')
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.50)
    gateway_mode = models.CharField(max_length=20, default='sandbox')
    
    feature_ai_menu = models.BooleanField(default=True)
    feature_qr_ordering = models.BooleanField(default=True)
    feature_whatsapp_alerts = models.BooleanField(default=False)
    feature_analytics_export = models.BooleanField(default=True)

    # Free Tier User Settings Governance Flags
    free_tier_allow_receipt_settings = models.BooleanField(default=False)
    free_tier_allow_kitchen_settings = models.BooleanField(default=True)
    free_tier_allow_security_pin = models.BooleanField(default=True)
    show_pro_badges_on_user_settings = models.BooleanField(default=True)
    hide_locked_settings_tabs = models.BooleanField(default=True)

    # Free Tier Quota Limits & Security Governance
    free_tier_max_orders_per_month = models.IntegerField(default=50)
    free_tier_max_menu_items = models.IntegerField(default=20)
    failed_login_lockout_threshold = models.IntegerField(default=5)
    audit_log_retention_days = models.IntegerField(default=90)
    
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self):
        return f"Global System Settings (Maintenance: {self.maintenance_mode})"






