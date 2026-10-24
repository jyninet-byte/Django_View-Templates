"""Tests for views and templates of the library app."""
import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from author.models import Author
from book.models import Book
from order.models import Order

from .models import CustomUser


class LibraryViewsTest(TestCase):
    def setUp(self):
        self.librarian = CustomUser.objects.create_user(
            email='lib@test.com', password='secret123', first_name='Olena', middle_name='',
            last_name='Koval', role=1, is_active=True)
        self.reader = CustomUser.objects.create_user(
            email='reader@test.com', password='secret123', first_name='Andrii', middle_name='',
            last_name='Melnyk', role=0, is_active=True)
        self.orwell = Author.objects.create(name='George', surname='Orwell', patronymic='')
        self.free_author = Author.objects.create(name='Free', surname='Author', patronymic='')
        self.book = Book.objects.create(name='1984', description='Dystopia', count=1)
        self.book.authors.add(self.orwell)
        self.other = Book.objects.create(name='Kobzar', description='Poetry', count=3)

    def login(self, user):
        self.client.force_login(user)

    # ---------- auth
    def test_register_reader_and_librarian(self):
        for role, email in (('0', 'new@test.com'), ('1', 'newlib@test.com')):
            self.client.logout()
            response = self.client.post(reverse('register'), {
                'first_name': 'Ivan', 'middle_name': '', 'last_name': 'Petrenko',
                'email': email, 'password': 'secret123', 'password2': 'secret123', 'role': role})
            self.assertRedirects(response, reverse('book_list'))
            user = CustomUser.objects.get(email=email)
            self.assertEqual(user.role, int(role))
            self.assertTrue(user.check_password('secret123'))
            self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_register_errors(self):
        response = self.client.post(reverse('register'), {
            'first_name': '', 'last_name': 'X', 'email': 'reader@test.com',
            'password': '1', 'password2': '2', 'role': '0'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')
        self.assertContains(response, 'First name is required')

    def test_login_logout(self):
        response = self.client.post(reverse('login'), {'email': 'reader@test.com', 'password': 'secret123'})
        self.assertRedirects(response, reverse('book_list'))
        response = self.client.post(reverse('login'), {'email': 'reader@test.com', 'password': 'bad'})
        self.client.logout()
        response = self.client.post(reverse('login'), {'email': 'reader@test.com', 'password': 'bad'})
        self.assertContains(response, 'Wrong email or password')
        self.login(self.reader)
        self.client.post(reverse('logout'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('book_list'))
        self.assertRedirects(response, reverse('login') + '?next=' + reverse('book_list'))

    # ---------- books
    def test_book_list_and_filters(self):
        self.login(self.reader)
        response = self.client.get(reverse('book_list'))
        self.assertContains(response, '1984')
        self.assertContains(response, 'Kobzar')
        response = self.client.get(reverse('book_list'), {'q': 'kob'})
        self.assertNotContains(response, '>1984<')
        self.assertContains(response, 'Kobzar')
        response = self.client.get(reverse('book_list'), {'author': self.orwell.id})
        self.assertEqual(list(response.context['books']), [self.book])
        response = self.client.get(reverse('book_list'), {'description': 'poet'})
        self.assertEqual(list(response.context['books']), [self.other])

    def test_book_detail(self):
        self.login(self.reader)
        response = self.client.get(reverse('book_detail', args=[self.book.id]))
        self.assertContains(response, 'Order the book')
        self.assertEqual(self.client.get(reverse('book_detail', args=[999])).status_code, 404)

    def test_user_books_only_for_librarian(self):
        Order.objects.create(user=self.reader, book=self.book, plated_end_at=timezone.now())
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse('user_books', args=[self.reader.id])).status_code, 403)
        self.login(self.librarian)
        response = self.client.get(reverse('user_books', args=[self.reader.id]))
        self.assertContains(response, '1984')

    def test_book_create(self):
        self.login(self.librarian)
        response = self.client.post(reverse('book_create'), {
            'name': 'Animal Farm', 'description': 'Satire', 'count': '2', 'authors': [self.orwell.id]})
        book = Book.objects.get(name='Animal Farm')
        self.assertRedirects(response, reverse('book_detail', args=[book.id]))
        self.assertEqual(list(book.authors.all()), [self.orwell])

    # ---------- users
    def test_users_only_for_librarian(self):
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse('user_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('user_detail', args=[self.reader.id])).status_code, 403)
        self.login(self.librarian)
        self.assertContains(self.client.get(reverse('user_list')), 'reader@test.com')
        self.assertContains(self.client.get(reverse('user_detail', args=[self.reader.id])), 'Melnyk')

    # ---------- orders
    def test_create_and_close_order(self):
        self.login(self.reader)
        date = (timezone.localdate() + datetime.timedelta(days=14)).isoformat()
        response = self.client.post(reverse('order_create'), {'book_id': self.book.id, 'plated_end_at': date})
        self.assertRedirects(response, reverse('my_orders'))
        order = Order.objects.get(user=self.reader, book=self.book)
        self.assertContains(self.client.get(reverse('my_orders')), '1984')

        # the only copy is taken now
        other_reader = CustomUser.objects.create_user(
            email='r2@test.com', password='secret123', first_name='A', middle_name='', last_name='B',
            is_active=True)
        self.login(other_reader)
        self.client.post(reverse('order_create'), {'book_id': self.book.id, 'plated_end_at': date})
        self.assertEqual(Order.objects.filter(book=self.book).count(), 1)

        # reader cannot close an order, librarian can
        self.assertEqual(self.client.post(reverse('order_close', args=[order.id])).status_code, 403)
        self.login(self.librarian)
        self.assertContains(self.client.get(reverse('order_list')), '1984')
        self.client.post(reverse('order_close', args=[order.id]))
        order.refresh_from_db()
        self.assertIsNotNone(order.end_at)

    def test_order_wrong_date(self):
        self.login(self.reader)
        self.client.post(reverse('order_create'), {'book_id': self.book.id, 'plated_end_at': '2000-01-01'})
        self.assertFalse(Order.objects.exists())

    def test_librarian_cannot_create_order_and_reader_cannot_see_all(self):
        self.login(self.librarian)
        response = self.client.post(reverse('order_create'), {'book_id': self.book.id, 'plated_end_at': '2099-01-01'})
        self.assertEqual(response.status_code, 403)
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse('order_list')).status_code, 403)

    # ---------- authors
    def test_authors(self):
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse('author_list')).status_code, 403)
        self.login(self.librarian)
        self.assertContains(self.client.get(reverse('author_list')), 'Orwell')

        self.client.post(reverse('author_create'), {'name': 'Ray', 'surname': 'Bradbury', 'patronymic': ''})
        self.assertTrue(Author.objects.filter(surname='Bradbury').exists())
        response = self.client.post(reverse('author_create'), {'name': '', 'surname': 'X' * 30})
        self.assertEqual(response.status_code, 400)

        self.client.post(reverse('author_delete', args=[self.orwell.id]))
        self.assertTrue(Author.objects.filter(pk=self.orwell.id).exists())
        self.client.post(reverse('author_delete', args=[self.free_author.id]))
        self.assertFalse(Author.objects.filter(pk=self.free_author.id).exists())

    def test_home_page(self):
        self.assertContains(self.client.get(reverse('home')), 'Every book in one place')
