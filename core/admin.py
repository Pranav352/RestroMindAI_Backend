from django.contrib import admin
from .models import Restaurant, Category, MenuItem, Table, Order, OrderItem

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'phone', 'created_at')
    search_fields = ('name', 'owner__email', 'phone')
    list_filter = ('created_at',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant')
    search_fields = ('name', 'restaurant__name')
    list_filter = ('restaurant',)

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available')
    search_fields = ('name', 'category__name', 'category__restaurant__name')
    list_filter = ('is_available', 'category__restaurant', 'category')

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('table_number', 'restaurant', 'qr_code')
    search_fields = ('table_number', 'restaurant__name')
    list_filter = ('restaurant',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ('menu_item',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'restaurant', 'table_number', 'customer_name', 'status', 'total_price', 'created_at')
    search_fields = ('id', 'customer_name', 'restaurant__name')
    list_filter = ('status', 'restaurant', 'created_at')
    inlines = [OrderItemInline]


