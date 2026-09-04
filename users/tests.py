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
            "password": "RestroMind@2026",
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
        invalid_data['role'] = 'superuser'
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('role', response.data)

    def test_password_complexity_missing_symbol(self):
        invalid_data = self.user_data.copy()
        invalid_data['password'] = 'RestroMind2026'  # No symbol
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_password_complexity_missing_uppercase(self):
        invalid_data = self.user_data.copy()
        invalid_data['password'] = 'restromind@2026'  # No uppercase
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_password_complexity_exceeding_max_length(self):
        invalid_data = self.user_data.copy()
        invalid_data['password'] = 'RestroMind@2026' + 'a' * 25  # > 32 chars
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_user_login_success(self):
        self.client.post(self.register_url, self.user_data, format='json')
        login_data = {
            "email": self.user_data['email'],
            "password": self.user_data['password']
        }
        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_user_login_invalid_credentials(self):
        self.client.post(self.register_url, self.user_data, format='json')
        login_data = {
            "email": self.user_data['email'],
            "password": "WrongPassword123!"
        }
        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_endpoint_without_token(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_endpoint_with_token(self):
        self.client.post(self.register_url, self.user_data, format='json')
        login_data = {
            "email": self.user_data['email'],
            "password": self.user_data['password']
        }
        login_res = self.client.post(self.login_url, login_data, format='json')
        access_token = login_res.data['access']
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user_data['email'])

    def test_user_logout(self):
        self.client.post(self.register_url, self.user_data, format='json')
        login_data = {
            "email": self.user_data['email'],
            "password": self.user_data['password']
        }
        login_res = self.client.post(self.login_url, login_data, format='json')
        access_token = login_res.data['access']
        refresh_token = login_res.data['refresh']
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_res = self.client.post(self.logout_url, {"refresh": refresh_token}, format='json')
        self.assertEqual(logout_res.status_code, status.HTTP_205_RESET_CONTENT)
        self.assertTrue(logout_res.data['success'])

        logout_res_retry = self.client.post(self.logout_url, {"refresh": refresh_token}, format='json')
        self.assertEqual(logout_res_retry.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_registration_with_first_name_and_pin(self):
        data = {
            "email": "john.owner@restromind.com",
            "password": "RestroMind@2026",
            "role": "owner",
            "first_name": "John Doe",
            "recovery_pin": "4829"
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['first_name'], "John Doe")
        
        user = User.objects.get(email="john.owner@restromind.com")
        self.assertEqual(user.first_name, "John Doe")
        self.assertTrue(user.check_recovery_pin("4829"))
        self.assertFalse(user.subscription.is_active())
        self.assertEqual(user.subscription.status, 'pending')


    def test_reset_password_with_pin_success(self):
        data = {
            "email": "reset.owner@restromind.com",
            "password": "OldPassword123!",
            "role": "owner",
            "recovery_pin": "1234"
        }
        self.client.post(self.register_url, data, format='json')
        
        reset_url = reverse('auth_reset_password_with_pin')
        reset_data = {
            "email": "reset.owner@restromind.com",
            "pin": "1234",
            "new_password": "NewSecurePassword123!"
        }
        response = self.client.post(reset_url, reset_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

        login_data = {
            "email": "reset.owner@restromind.com",
            "password": "NewSecurePassword123!"
        }
        login_res = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

    def test_reset_password_account_without_pin(self):
        data = {
            "email": "nopin.owner@restromind.com",
            "password": "OldPassword123!",
            "role": "owner"
        }
        self.client.post(self.register_url, data, format='json')
        
        reset_url = reverse('auth_reset_password_with_pin')
        reset_data = {
            "email": "nopin.owner@restromind.com",
            "pin": "1234",
            "new_password": "NewSecurePassword123!"
        }
        response = self.client.post(reset_url, reset_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No recovery PIN set', response.data['pin'][0])

    def test_update_pin_via_me_view(self):
        data = {
            "email": "updatepin.owner@restromind.com",
            "password": "OldPassword123!",
            "role": "owner"
        }
        self.client.post(self.register_url, data, format='json')
        login_res = self.client.post(self.login_url, {"email": data['email'], "password": data['password']}, format='json')
        access_token = login_res.data['access']
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        me_res = self.client.get(self.me_url)
        self.assertFalse(me_res.data['has_recovery_pin'])

        patch_res = self.client.patch(self.me_url, {"recovery_pin": "5678", "first_name": "Updated Name"}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertTrue(patch_res.data['user']['has_recovery_pin'])
        self.assertEqual(patch_res.data['user']['first_name'], "Updated Name")


class SubscriptionTests(APITestCase):

    def setUp(self):
        self.owner_email = "newowner@test.com"
        self.owner_password = "RestroMindPassword123!"

    def test_subscription_states(self):
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
        self.assertFalse(user.subscription.is_active())
        self.assertEqual(user.subscription.status, 'pending')

        
        user.subscription.status = 'pending'
        user.subscription.save()
        self.assertFalse(user.subscription.is_active())

        user.subscription.status = 'stopped'
        user.subscription.save()
        self.assertFalse(user.subscription.is_active())

        user.subscription.status = 'active'
        from django.utils import timezone
        from datetime import timedelta
        user.subscription.start_date = timezone.now()
        user.subscription.end_date = timezone.now() + timedelta(days=30)
        user.subscription.save()
        
        self.assertTrue(user.subscription.is_active())
        self.assertEqual(user.subscription.days_remaining(), 30)
