from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from author.models import Author
from book.models import Book
from order.models import Order

from .decorators import librarian_required
from .models import ROLE_CHOICES, CustomUser

NAME_MAX_LENGTH = 20
PASSWORD_MIN_LENGTH = 6


def home(request):
    """Landing page with a short overview of the library."""
    context = {
        'books_count': Book.objects.count(),
        'authors_count': Author.objects.count(),
        'open_orders_count': Order.objects.filter(end_at__isnull=True).count(),
        'latest_books': Book.objects.order_by('-id')[:4],
    }
    return render(request, 'home.html', context)


def register(request):
    """Register a new user as a librarian or as an ordinary user (visitor)."""
    if request.user.is_authenticated:
        return redirect('book_list')

    data = {}
    errors = {}
    if request.method == 'POST':
        data = {key: request.POST.get(key, '').strip()
                for key in ('first_name', 'middle_name', 'last_name', 'email', 'role')}
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        for field, label in (('first_name', 'First name'), ('last_name', 'Last name')):
            if not data[field]:
                errors[field] = f'{label} is required.'
        for field in ('first_name', 'middle_name', 'last_name'):
            if len(data[field]) > NAME_MAX_LENGTH:
                errors[field] = f'Maximum {NAME_MAX_LENGTH} characters.'

        try:
            validate_email(data['email'])
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'
        else:
            if len(data['email']) > 100:
                errors['email'] = 'Maximum 100 characters.'
            elif CustomUser.objects.filter(email__iexact=data['email']).exists():
                errors['email'] = 'A user with this email already exists.'

        if len(password) < PASSWORD_MIN_LENGTH:
            errors['password'] = f'Password must contain at least {PASSWORD_MIN_LENGTH} characters.'
        elif password != password2:
            errors['password2'] = 'Passwords do not match.'

        if data['role'] not in ('0', '1'):
            errors['role'] = 'Choose a role.'

        if not errors:
            user = CustomUser.objects.create_user(
                email=data['email'],
                password=password,
                first_name=data['first_name'],
                middle_name=data['middle_name'],
                last_name=data['last_name'],
                role=int(data['role']),
                is_active=True,
            )
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome, {user.first_name}! Your account has been created.')
            return redirect('book_list')

    return render(request, 'authentication/register.html',
                  {'data': data, 'errors': errors, 'roles': ROLE_CHOICES})


def login_view(request):
    """Log in with email and password."""
    if request.user.is_authenticated:
        return redirect('book_list')

    email = ''
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'Hello, {user.first_name or user.email}!')
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect('book_list')
        messages.error(request, 'Wrong email or password.')

    return render(request, 'authentication/login.html',
                  {'email': email, 'next': request.GET.get('next', '')})


@require_POST
def logout_view(request):
    """Log out the current user."""
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@librarian_required
def user_list(request):
    """Show all users with search and role filter (librarian only)."""
    query = request.GET.get('q', '').strip()
    role = request.GET.get('role', '')

    users = CustomUser.objects.annotate(
        open_orders=Count('order', filter=Q(order__end_at__isnull=True)),
        total_orders=Count('order'),
    )
    if query:
        users = users.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query)
                             | Q(middle_name__icontains=query) | Q(email__icontains=query))
    if role in ('0', '1'):
        users = users.filter(role=int(role))

    return render(request, 'authentication/user_list.html',
                  {'users': users, 'query': query, 'role': role, 'roles': ROLE_CHOICES})


@librarian_required
def user_detail(request, user_id):
    """Show a specific user (librarian only)."""
    user = get_object_or_404(CustomUser, pk=user_id)
    orders = Order.objects.filter(user=user).select_related('book')
    context = {
        'profile': user,
        'open_orders': orders.filter(end_at__isnull=True),
        'closed_count': orders.filter(end_at__isnull=False).count(),
    }
    return render(request, 'authentication/user_detail.html', context)
