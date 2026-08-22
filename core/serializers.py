from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Restaurant, Category, MenuItem, Table, Order, OrderItem

User = get_user_model()


from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r'^\+?[\d\s\-()]{7,20}$',
    message="Phone number must be a valid format (e.g. +1234567890 or 123-456-7890). Between 7 and 20 characters."
)

def validate_image_file(file):
    if not file:
        return file
    max_size = 5 * 1024 * 1024
    if file.size > max_size:
        raise serializers.ValidationError("Image file size must be less than 5MB.")
    allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
    content_type = getattr(file, 'content_type', None)
    if content_type and content_type not in allowed_types:
        raise serializers.ValidationError("Only JPEG, PNG, WEBP, and GIF images are allowed.")
    return file

class RestaurantSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    phone = serializers.CharField(
        validators=[phone_validator],
        required=False,
        allow_blank=True
    )
    logo = serializers.ImageField(
        validators=[validate_image_file],
        required=False,
        allow_null=True
    )

    class Meta:
        model = Restaurant
        fields = ('id', 'owner', 'name', 'logo', 'phone', 'address', 'currency', 'created_at')


    def validate(self, data):
        request = self.context.get('request')
        if request and request.method == 'POST':
            # Limit to one restaurant per owner
            if Restaurant.objects.filter(owner=request.user).exists():
                raise serializers.ValidationError("An owner can only create one restaurant in the MVP scope.")
        return data


class CategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ('id', 'restaurant', 'name', 'parent', 'subcategories')

    def get_subcategories(self, obj):
        # We can recursively serialize subcategories here if needed, 
        # but let's just return minimal info to avoid deep nesting issues if they are deep.
        return CategorySerializer(obj.subcategories.all(), many=True, context=self.context).data

    def validate_restaurant(self, value):
        request = self.context.get('request')
        if request and hasattr(request, 'tenant_id'):
            if value.id != request.tenant_id:
                raise serializers.ValidationError("You can only create categories for your active restaurant.")
        return value


class MenuItemSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(
        validators=[validate_image_file],
        required=False,
        allow_null=True
    )

    class Meta:
        model = MenuItem
        fields = ('id', 'category', 'name', 'description', 'price', 'image', 'is_available')

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be a positive number.")
        return value

    def validate_category(self, value):
        request = self.context.get('request')
        if request and hasattr(request, 'tenant_id'):
            if value.restaurant.id != request.tenant_id:
                raise serializers.ValidationError("This category belongs to a different restaurant.")
        return value


class TableSerializer(serializers.ModelSerializer):
    qr_code_url = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = ('id', 'restaurant', 'table_number', 'qr_code', 'qr_code_url')
        read_only_fields = ('qr_code', 'qr_code_url')

    def get_qr_code_url(self, obj):
        if obj.qr_code:
            request = self.context.get('request')
            path = obj.qr_code
            if not path.startswith('/media/') and not path.startswith('http://') and not path.startswith('https://'):
                path = f"/media/{path}"
            if request:
                return request.build_absolute_uri(path)
            return path
        return None

    def validate_restaurant(self, value):
        request = self.context.get('request')
        if request and hasattr(request, 'tenant_id'):
            if value.id != request.tenant_id:
                raise serializers.ValidationError("You can only create tables for your active restaurant.")
        return value

    def validate_table_number(self, value):
        if value <= 0:
            raise serializers.ValidationError("Table number must be a positive integer.")
        return value


# Serializers for Public Menu (Customer view - Lean & Fast)
class PublicMenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ('id', 'name', 'description', 'price', 'image', 'is_available')


class PublicCategorySerializer(serializers.ModelSerializer):
    menu_items = serializers.SerializerMethodField()
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ('id', 'name', 'menu_items', 'subcategories')

    def get_menu_items(self, obj):
        # Only return items that are available
        available_items = obj.menu_items.filter(is_available=True)
        return PublicMenuItemSerializer(available_items, many=True, context=self.context).data

    def get_subcategories(self, obj):
        return PublicCategorySerializer(obj.subcategories.all(), many=True, context=self.context).data


class PublicRestaurantSerializer(serializers.ModelSerializer):
    categories = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = ('id', 'name', 'logo', 'phone', 'address', 'currency', 'categories')

    def get_categories(self, obj):
        # Only return top-level categories here. 
        # Subcategories are nested inside their parent categories via PublicCategorySerializer.
        top_categories = obj.categories.filter(parent__isnull=True)
        return PublicCategorySerializer(top_categories, many=True, context=self.context).data


from users.models import Subscription

class AdminSubscriptionSerializer(serializers.ModelSerializer):
    days_remaining = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = ('plan', 'status', 'start_date', 'end_date', 'days_remaining', 'is_active')


class AdminUserSerializer(serializers.ModelSerializer):
    restaurant_count = serializers.SerializerMethodField()
    subscription = AdminSubscriptionSerializer(required=False, allow_null=True)

    class Meta:
        model = User
        fields = (
            'id', 
            'email', 
            'role', 
            'is_active', 
            'date_joined', 
            'restaurant_count',
            'subscription'
        )
        read_only_fields = (
            'id', 
            'email', 
            'date_joined', 
            'restaurant_count'
        )

    def get_restaurant_count(self, obj):
        return obj.restaurants.count()

    def update(self, instance, validated_data):
        subscription_data = validated_data.pop('subscription', None)
        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update nested subscription fields
        if subscription_data:
            subscription = getattr(instance, 'subscription', None)
            if subscription:
                status = subscription_data.get('status', subscription.status)
                
                from django.utils import timezone
                from datetime import timedelta
                
                # If transitioning to active, automatically assign the 30-day trial
                if status == 'active' and subscription.status != 'active':
                    subscription.start_date = timezone.now()
                    subscription.end_date = timezone.now() + timedelta(days=30)
                
                subscription.status = status
                subscription.plan = subscription_data.get('plan', subscription.plan)
                
                if 'start_date' in subscription_data:
                    subscription.start_date = subscription_data['start_date']
                if 'end_date' in subscription_data:
                    subscription.end_date = subscription_data['end_date']
                    
                subscription.save()
            elif instance.role == 'owner':
                from django.utils import timezone
                from datetime import timedelta
                
                status = subscription_data.get('status', 'pending')
                plan = subscription_data.get('plan', 'free_trial')
                
                start_date = subscription_data.get('start_date', None)
                end_date = subscription_data.get('end_date', None)
                
                if status == 'active' and not start_date:
                    start_date = timezone.now()
                    end_date = timezone.now() + timedelta(days=30)
                    
                Subscription.objects.create(
                    user=instance,
                    plan=plan,
                    status=status,
                    start_date=start_date,
                    end_date=end_date
                )
                
        return instance



class AdminRestaurantSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source='owner.email', read_only=True)

    class Meta:
        model = Restaurant
        fields = ('id', 'owner', 'owner_email', 'name', 'logo', 'phone', 'address', 'currency', 'created_at')


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)
    menu_item_price = serializers.DecimalField(source='menu_item.price', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ('id', 'menu_item', 'menu_item_name', 'menu_item_price', 'quantity', 'price', 'status', 'round', 'created_at')
        read_only_fields = ('price', 'created_at')


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    tracking_token = serializers.UUIDField(required=False, allow_null=True)
    rounds_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id', 
            'restaurant', 
            'table_number', 
            'customer_name', 
            'status', 
            'total_price', 
            'items', 
            'tracking_token', 
            'rounds_count',
            'created_at', 
            'updated_at'
        )
        read_only_fields = ('total_price', 'created_at', 'updated_at')

    def get_rounds_count(self, obj):
        return obj.items.values('round').distinct().count() or 1

    def create(self, validated_data):
        from django.db.models import Max
        items_data = validated_data.pop('items')
        restaurant = validated_data['restaurant']
        tracking_token = validated_data.get('tracking_token')

        # Check if customer is adding items to an existing active order (same session)
        existing_order = None
        if tracking_token:
            existing_order = Order.objects.filter(
                tracking_token=tracking_token,
                restaurant=restaurant
            ).exclude(status__in=['completed', 'cancelled']).first()

        if existing_order:
            # Append new items to existing order as a new round
            current_max_round = existing_order.items.aggregate(Max('round'))['round__max'] or 1
            new_round = current_max_round + 1

            for item_data in items_data:
                menu_item = item_data['menu_item']
                if menu_item.category.restaurant != restaurant:
                    raise serializers.ValidationError({"items": f"Menu item {menu_item.name} does not belong to this restaurant."})
                
                OrderItem.objects.create(
                    order=existing_order,
                    menu_item=menu_item,
                    quantity=item_data['quantity'],
                    price=menu_item.price,
                    status='pending',
                    round=new_round
                )

            # Update customer name if provided
            customer_name = validated_data.get('customer_name')
            if customer_name and not existing_order.customer_name:
                existing_order.customer_name = customer_name

            existing_order.recalculate_total()
            # If the order was served or pending, set it to preparing to alert the kitchen
            if existing_order.status in ('served', 'pending'):
                existing_order.status = 'preparing'
                existing_order.save(update_fields=['status', 'customer_name', 'updated_at'])
            else:
                existing_order.save(update_fields=['customer_name', 'updated_at'])

            return existing_order

        # Standard new order creation (Round 1)
        customer_name = validated_data.get('customer_name', '').strip()
        if not customer_name:
            raise serializers.ValidationError({"customer_name": "Please enter your name."})
        validated_data['customer_name'] = customer_name

        table_number = validated_data.get('table_number')
        if table_number:
            # Check if table is currently occupied with an active dining session
            occupied_order = Order.objects.filter(
                restaurant=restaurant,
                table_number=table_number,
                status__in=['pending', 'preparing', 'served']
            ).first()
            if occupied_order:
                raise serializers.ValidationError({
                    "table_number": f"Table {table_number} currently has an active dining session. Extra items can be ordered from the table's primary device."
                })

            Table.objects.get_or_create(restaurant=restaurant, table_number=table_number)

        order = Order.objects.create(**validated_data)
        total_price = 0
        for item_data in items_data:
            menu_item = item_data['menu_item']
            if menu_item.category.restaurant != restaurant:
                order.delete()
                raise serializers.ValidationError({"items": f"Menu item {menu_item.name} does not belong to this restaurant."})
            
            price = menu_item.price
            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                quantity=item_data['quantity'],
                price=price,
                status='pending',
                round=1
            )
            total_price += price * item_data['quantity']
        
        order.total_price = total_price
        order.save(update_fields=['total_price', 'updated_at'])
        return order



