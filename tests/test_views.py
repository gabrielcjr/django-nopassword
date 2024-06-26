# -*- coding: utf8 -*-
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from nopassword.models import LoginCode


class TestViews(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create(username='user', email='foo@bar.com')

    def test_request_login_code(self):
        response = self.client.post('/accounts/login/', {
            'username': self.user.username,
            'next': '/private/',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/accounts/login/code/')

        login_code = LoginCode.objects.filter(user=self.user).first()

        self.assertIsNotNone(login_code)
        self.assertEqual(login_code.next, '/private/')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            'http://testserver/accounts/login/code/?user={}&code={}'.format(
                login_code.user.pk,
                login_code.code
            ),
            mail.outbox[0].body,
        )

    def test_request_login_code_missing_username(self):
        response = self.client.post('/accounts/login/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].errors, {
            'username': ['This field is required.'],
        })

    def test_request_login_code_unknown_user(self):
        response = self.client.post('/accounts/login/', {
            'username': 'unknown',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].errors, {
            'username': ['Please enter a correct userid. Note that it is case-sensitive.'],
        })

    def test_request_login_code_inactive_user(self):
        self.user.is_active = False
        self.user.save()

        response = self.client.post('/accounts/login/', {
            'username': self.user.username,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].errors, {
            'username': ['This account is inactive.'],
        })

    def test_login_post(self):
        login_code = LoginCode.objects.create(user=self.user, next='/private/')

        response = self.client.post('/accounts/login/code/', {
            'user': login_code.user.pk,
            'code': login_code.code,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/private/')
        self.assertEqual(response.wsgi_request.user, self.user)
        self.assertTrue(LoginCode.objects.filter(pk=login_code.pk).exists())

    def test_login_get(self):
        login_code = LoginCode.objects.create(user=self.user)

        response = self.client.get('/accounts/login/code/', {
            'user': login_code.user.pk,
            'code': login_code.code,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].cleaned_data['code'], login_code.code)
        self.assertTrue(response.wsgi_request.user.is_anonymous)
        self.assertTrue(LoginCode.objects.filter(pk=login_code.pk).exists())
    
    @patch("nopassword.models.timezone.now")
    def test_login_get_with_expired_at(self, mock_now):
        mock_now.return_value = timezone.datetime(2100, 1, 1, 0, 0, 1)
        login_code = LoginCode.objects.create(user=self.user)
        created_code= (login_code.create_code_for_user(self.user))

        self.assertIsNone(created_code)

        with self.assertRaises(TypeError) as assert_error:
            response = self.client.get('/accounts/login/code/', {
                'user': login_code.user.pk,
                'code': created_code,
            })
            self.assertEqual(response.status_code, 302)

        self.assertEqual(
            assert_error.exception.args[0],
            "Cannot encode None in a query string. Did you mean to pass an empty string or omit the value?"
            )


    @override_settings(NOPASSWORD_LOGIN_ON_GET=True)
    def test_login_get_non_idempotent(self):
        login_code = LoginCode.objects.create(user=self.user, next='/private/')

        response = self.client.get('/accounts/login/code/', {
            'user': login_code.user.pk,
            'code': login_code.code,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/private/')
        self.assertEqual(response.wsgi_request.user, self.user)
        self.assertTrue(LoginCode.objects.filter(pk=login_code.pk).exists())

    def test_login_missing_code_post(self):
        response = self.client.post('/accounts/login/code/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].errors, {
            'user': ['This field is required.'],
            'code': ['This field is required.'],
            '__all__': ['Unable to log in with provided login code.']
        })

    def test_login_missing_code_get(self):
        response = self.client.get('/accounts/login/code/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_bound)

    def test_login_unknown_code(self):
        response = self.client.post('/accounts/login/code/', {
            'user': 1,
            'code': 'unknown',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].errors, {
            '__all__': ['Unable to log in with provided login code.'],
        })

    def test_login_inactive_user(self):
        self.user.is_active = False
        self.user.save()

        login_code = LoginCode.objects.create(user=self.user)

        response = self.client.post('/accounts/login/code/', {
            'user': login_code.user.pk,
            'code': login_code.code,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].errors, {
            '__all__': ['Unable to log in with provided login code.']
        })

    def test_logout_post(self):
        login_code = LoginCode.objects.create(user=self.user)

        self.client.login(username=self.user.username, code=login_code.code)

        response = self.client.post('/accounts/logout/?next=/accounts/login/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/accounts/login/')
        self.assertTrue(response.wsgi_request.user.is_anonymous)

    def test_logout_get(self):
        login_code = LoginCode.objects.create(user=self.user)

        self.client.login(username=self.user.username, code=login_code.code)

        response = self.client.post('/accounts/logout/?next=/accounts/login/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/accounts/login/')
        self.assertTrue(response.wsgi_request.user.is_anonymous)
