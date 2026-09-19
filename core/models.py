from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid

class Restaurant(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='restaurants'
    )
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='restaurant_logos/', max_length=500, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    CURRENCY_CHOICES = [
        ('₹', 'INR (₹)'),
        ('$', 'USD ($)'),
        ('€', 'EUR (€)'),
        ('£', 'GBP (£)'),
    ]
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='₹')
    is_accepting_orders = models.BooleanField(default=True)
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Category(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='categories'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories'
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        if self.parent:
            return f"{self.name} (Sub of {self.parent.name}) - {self.restaurant.name}"
        return f"{self.name} - {self.restaurant.name}"


class MenuItem(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='menu_items'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='menu_items/', max_length=500, null=True, blank=True)
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Table(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='tables'
    )
    table_number = models.PositiveIntegerField()
    section = models.CharField(max_length=50, default='Main Area', blank=True)
    label = models.CharField(max_length=50, blank=True)
    qr_code = models.CharField(max_length=255, null=True, blank=True)
    qr_code_svg = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['section', 'table_number']
        unique_together = ('restaurant', 'section', 'table_number')

    def __str__(self):
        display_name = self.label if self.label else f"Table {self.table_number}"
        return f"{display_name} ({self.section}) - {self.restaurant.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('served', 'Served'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('upi', 'UPI / QR'),
        ('card', 'Credit / Debit Card'),
        ('complimentary', 'Complimentary'),
    ]

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    table_number = models.PositiveIntegerField(null=True, blank=True)
    customer_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=100, blank=True, null=True)
    is_paid = models.BooleanField(default=False)
    payment_txn_id = models.CharField(max_length=100, blank=True, null=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tracking_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    cancellation_reason = models.CharField(max_length=50, blank=True, null=True)
    is_recovered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} - Table {self.table_number} ({self.status})"

    @property
    def rounds_count(self):
        return self.items.values('round').distinct().count() or 1

    def recalculate_total(self):
        """Recalculate total price based on non-cancelled line items."""
        active_items = self.items.exclude(status='cancelled')
        self.total_price = sum(item.price * item.quantity for item in active_items)
        self.save(update_fields=['total_price', 'updated_at'])

    def sync_overall_status(self):
        """Synchronize the order-level status based on individual item rounds."""
        if self.status == 'completed':
            return

        items = list(self.items.all())
        if not items:
            return

        active_items = [i for i in items if i.status != 'cancelled']
        if not active_items:
            self.status = 'cancelled'
        elif all(i.status == 'served' for i in active_items):
            self.status = 'served'
        elif any(i.status == 'preparing' for i in active_items):
            self.status = 'preparing'
        elif any(i.status == 'pending' for i in active_items):
            # If some are served/preparing and some pending, it is preparing
            if any(i.status in ('preparing', 'served') for i in active_items):
                self.status = 'preparing'
            else:
                self.status = 'pending'

        self.save(update_fields=['status', 'updated_at'])


class OrderItem(models.Model):
    ITEM_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('served', 'Served'),
        ('cancelled', 'Cancelled'),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Price at the time of order
    status = models.CharField(max_length=20, choices=ITEM_STATUS_CHOICES, default='pending')
    round = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['round', 'created_at', 'id']

    def __str__(self):
        return f"[R{self.round}] {self.quantity}x {self.menu_item.name} ({self.status}) in Order #{self.order.id}"



