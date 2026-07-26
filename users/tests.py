from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

class AuthTests(APITestCase):
    def setUp(self):
        self.register_url = reverse('auth_register')
        self.login_url = reverse('auth_login')
        self.logout_url = reverse('auth_logout')
        self.me_url = reverse('auth_me')
        
        self.user_data = {
            "email": "owner@restromind.com",
            "password": "securepassword123",
            "role": "owner"
        }

    def test_user_registration_success(self):
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['user']['email'], self.user_data['email'])
        self.assertEqual(response.data['user']['role'], self.user_data['role'])

    def test_user_registration_duplicate_email(self):
        # Register once
        self.client.post(self.register_url, self.user_data, format='json')
        # Register again
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_user_registration_invalid_role(self):
        invalid_data = self.user_data.copy()
        invalid_data['role'] = 'superuser'  # Not in customer, owner, admin
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('role', response.data)

    def test_user_registration_short_password(self):
        invalid_data = self.user_data.copy()
        invalid_data['password'] = 'short'
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_user_login_success(self):
        # Register first
        self.client.post(self.register_url, self.user_data, format='json')
        
        # Log in
        login_data = {
            "email": self.user_data['email'],
            "password": self.user_data['password']
        }
        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_user_login_invalid_credentials(self):
        # Register first
        self.client.post(self.register_url, self.user_data, format='json')
        
        # Log in with wrong password
        login_data = {
            "email": self.user_data['email'],
            "password": "wrongpassword"
        }
        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_endpoint_without_token(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_endpoint_with_token(self):
        # Register and log in
        self.client.post(self.register_url, self.user_data, format='json')
        login_data = {
            "email": self.user_data['email'],
            "password": self.user_data['password']
        }
        login_res = self.client.post(self.login_url, login_data, format='json')
        access_token = login_res.data['access']
        
        # Access with token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user_data['email'])

    def test_user_logout(self):
        # Register and log in
        self.client.post(self.register_url, self.user_data, format='json')
        login_data = {
            "email": self.user_data['email'],
            "password": self.user_data['password']
        }
        login_res = self.client.post(self.login_url, login_data, format='json')
        access_token = login_res.data['access']
        refresh_token = login_res.data['refresh']
        
        # Log out
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_res = self.client.post(self.logout_url, {"refresh": refresh_token}, format='json')
        self.assertEqual(logout_res.status_code, status.HTTP_205_RESET_CONTENT)
        self.assertTrue(logout_res.data['success'])

        # Try to use blacklisted refresh token again
        logout_res_retry = self.client.post(self.logout_url, {"refresh": refresh_token}, format='json')
        self.assertEqual(logout_res_retry.status_code, status.HTTP_400_BAD_REQUEST)


class SubscriptionTests(APITestCase):
    def setUp(self):
        self.owner_email = "newowner@test.com"
        self.owner_password = "securepassword123"

    def test_subscription_states(self):
        # Register a new owner
        register_url = reverse('auth_register')
        data = {
            "email": self.owner_email,
            "password": self.owner_password,
            "role": "owner",
            "plan": "free_trial"
        }
        
        response = self.client.post(register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        user = User.objects.get(email=self.owner_email)
        self.assertTrue(hasattr(user, 'subscription'))
        
        # Test pending state
        user.subscription.status = 'pending'
        user.subscription.save()
        self.assertFalse(user.subscription.is_active())

        # Test stopped state
        user.subscription.status = 'stopped'
        user.subscription.save()
        self.assertFalse(user.subscription.is_active())

        # Test active state with remaining days
        user.subscription.status = 'active'
        from django.utils import timezone
        from datetime import timedelta
        user.subscription.start_date = timezone.now()
        user.subscription.end_date = timezone.now() + timedelta(days=30)
        user.subscription.save()
        
        self.assertTrue(user.subscription.is_active())
        self.assertEqual(user.subscription.days_remaining(), 30)


