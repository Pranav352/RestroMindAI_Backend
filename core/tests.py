from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch, MagicMock
import os
from django.conf import settings

from .models import Restaurant, Category, MenuItem, Table

User = get_user_model()

class CoreModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@restromind.com",
            password="securepassword123",
            role="owner"
        )
        
        self.restaurant = Restaurant.objects.create(
            owner=self.user,
            name="Pizza Paradiso",
            phone="1234567890",
            address="123 Main St"
        )

    def test_restaurant_creation(self):
        self.assertEqual(self.restaurant.name, "Pizza Paradiso")
        self.assertEqual(self.restaurant.owner, self.user)
        self.assertEqual(str(self.restaurant), "Pizza Paradiso")

    def test_category_creation_and_cascade(self):
        category = Category.objects.create(
            restaurant=self.restaurant,
            name="Starters"
        )
        self.assertEqual(category.name, "Starters")
        self.assertEqual(str(category), "Starters - Pizza Paradiso")

        # Test related name
        self.assertIn(category, self.restaurant.categories.all())

        # Test cascade delete
        self.restaurant.delete()
        self.assertFalse(Category.objects.filter(id=category.id).exists())

    def test_menu_item_creation_and_cascade(self):
        category = Category.objects.create(
            restaurant=self.restaurant,
            name="Mains"
        )
        menu_item = MenuItem.objects.create(
            category=category,
            name="Margherita Pizza",
            description="Classic pizza with tomatoes and mozzarella",
            price=12.99,
            is_available=True
        )
        self.assertEqual(menu_item.name, "Margherita Pizza")
        self.assertEqual(str(menu_item), "Margherita Pizza")
        self.assertIn(menu_item, category.menu_items.all())

        # Test cascade delete on category delete
        category.delete()
        self.assertFalse(MenuItem.objects.filter(id=menu_item.id).exists())

    def test_table_creation_and_unique_constraint(self):
        table = Table.objects.create(
            restaurant=self.restaurant,
            table_number=5,
            qr_code="http://example.com/qr/5"
        )
        self.assertEqual(table.table_number, 5)
        self.assertEqual(str(table), "Table 5 (Pizza Paradiso)")
        self.assertIn(table, self.restaurant.tables.all())

        # Test unique constraint on table number for the same restaurant
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Table.objects.create(
                restaurant=self.restaurant,
                table_number=5
            )


class CoreAPITests(APITestCase):
    def setUp(self):
        # Create users
        self.owner = User.objects.create_user(
            email="owner@restromind.com",
            password="securepassword123",
            role="owner"
        )
        self.other_owner = User.objects.create_user(
            email="other@restromind.com",
            password="securepassword123",
            role="owner"
        )

        # URLs
        self.restaurant_list_url = reverse('restaurant-list')
        self.category_list_url = reverse('category-list')
        self.menu_item_list_url = reverse('menu-item-list')
        self.qr_generate_url = reverse('qr-generate')

        # Authenticate owner by default
        self.client.force_authenticate(user=self.owner)

    def test_restaurant_crud_success(self):
        # Create
        data = {
            "name": "Pizza Planet",
            "phone": "9998887777",
            "address": "1 Infinite Loop"
        }
        response = self.client.post(self.restaurant_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], "Pizza Planet")
        
        # List (Only MY restaurants)
        response = self.client.get(self.restaurant_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # Enforce max 1 restaurant constraint
        response = self.client.post(self.restaurant_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_restaurant_ownership_check(self):
        # Create a restaurant owned by other_owner
        other_restaurant = Restaurant.objects.create(
            owner=self.other_owner,
            name="Other Cafe"
        )
        
        detail_url = reverse('restaurant-detail', args=[other_restaurant.id])
        
        # Try to modify (should fail with 403 or not found since get_queryset filters out other restaurants)
        # In DRF, standard get_queryset will return 404 since it filters by owner=request.user
        response = self.client.put(detail_url, {"name": "Hacked Cafe"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_category_crud_owner_scoped(self):
        restaurant = Restaurant.objects.create(owner=self.owner, name="Pizza Planet")
        other_restaurant = Restaurant.objects.create(owner=self.other_owner, name="Other Restaurant")

        # Create category for own restaurant
        data = {
            "restaurant": restaurant.id,
            "name": "Mains"
        }
        response = self.client.post(self.category_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Try to create category for someone else's restaurant
        data_other = {
            "restaurant": other_restaurant.id,
            "name": "Intruding Category"
        }
        response = self.client.post(self.category_list_url, data_other, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_menu_item_crud_with_price_validation(self):
        restaurant = Restaurant.objects.create(owner=self.owner, name="Pizza Planet")
        category = Category.objects.create(restaurant=restaurant, name="Drinks")

        # Positive price check
        data = {
            "category": category.id,
            "name": "Cola",
            "price": -1.50
        }
        response = self.client.post(self.menu_item_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Valid payload
        data["price"] = 2.50
        response = self.client.post(self.menu_item_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(response.data['price']), 2.50)

    @patch('core.views.qrcode')
    def test_qr_generate_success(self, mock_qrcode):
        # Mock qrcode generation to avoid file system writing issues and check method calls
        mock_qr_instance = MagicMock()
        mock_qrcode.QRCode.return_value = mock_qr_instance
        
        restaurant = Restaurant.objects.create(owner=self.owner, name="Pizza Planet")
        data = {
            "restaurant_id": restaurant.id,
            "table_number": 3
        }
        response = self.client.post(self.qr_generate_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['table_number'], 3)
        self.assertIsNotNone(response.data['qr_code'])
        
        # Verify Table was created
        self.assertTrue(Table.objects.filter(restaurant=restaurant, table_number=3).exists())

    def test_public_menu_endpoint_unauthenticated(self):
        restaurant = Restaurant.objects.create(owner=self.owner, name="Pizza Planet")
        category = Category.objects.create(restaurant=restaurant, name="Dessert")
        
        # Available item
        MenuItem.objects.create(
            category=category,
            name="Ice Cream",
            price=4.00,
            is_available=True
        )
        # Unavailable item (should not be in public payload)
        MenuItem.objects.create(
            category=category,
            name="Expired Cake",
            price=3.50,
            is_available=False
        )

        # Make request WITHOUT authentication
        self.client.force_authenticate(user=None)
        
        public_url = reverse('public-menu', args=[restaurant.id])
        response = self.client.get(public_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], "Pizza Planet")
        
        # Verify Ice Cream is returned, but Expired Cake is omitted
        categories = response.data['categories']
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0]['name'], "Dessert")
        
        items = categories[0]['menu_items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['name'], "Ice Cream")


class AdminAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@restromind.com",
            password="adminpassword123"
        )
        self.owner = User.objects.create_user(
            email="owner@restromind.com",
            password="ownerpassword123",
            role="owner"
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner,
            name="Owner Pizza Shop"
        )

        self.stats_url = reverse('admin-stats')
        self.users_list_url = reverse('admin-user-list')
        self.restaurants_list_url = reverse('admin-restaurant-list')

    def test_non_admin_forbidden(self):
        # Authenticate standard owner
        self.client.force_authenticate(user=self.owner)
        
        response = self.client.get(self.stats_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        response = self.client.get(self.users_list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(self.restaurants_list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_stats(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.stats_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_users'], 2)
        self.assertEqual(response.data['total_restaurants'], 1)

    def test_admin_manage_users(self):
        self.client.force_authenticate(user=self.admin)
        
        # List users
        response = self.client.get(self.users_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        
        # Toggle user is_active (suspend)
        user_detail_url = reverse('admin-user-detail', args=[self.owner.id])
        response = self.client.patch(user_detail_url, {"is_active": False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)

        # Delete user
        response = self.client.delete(user_detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=self.owner.id).exists())

    def test_admin_manage_restaurants(self):
        self.client.force_authenticate(user=self.admin)

        # List restaurants
        response = self.client.get(self.restaurants_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

        # Delete restaurant
        restaurant_detail_url = reverse('admin-restaurant-detail', args=[self.restaurant.id])
        response = self.client.delete(restaurant_detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Restaurant.objects.filter(id=self.restaurant.id).exists())



