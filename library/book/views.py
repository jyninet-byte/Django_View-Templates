import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from authentication.decorators import librarian_required
from authentication.models import CustomUser
from author.models import Author
from order.models import Order

from .models import Book

SORT_OPTIONS = {
    'name': ('Title A-Z', 'name'),
    '-name': ('Title Z-A', '-name'),
    '-count': ('Most copies', '-count'),
    '-id': ('Newest first', '-id'),
}


@login_required
def book_list(request):
    """Show all books with filters by title, author, description and availability."""
    filters = {
        'q': request.GET.get('q', '').strip(),
        'author': request.GET.get('author', ''),
        'description': request.GET.get('description', '').strip(),
        'available': request.GET.get('available', ''),
        'sort': request.GET.get('sort', 'name'),
    }

    books = Book.objects.prefetch_related('authors').annotate(
        taken=Count('order', filter=Q(order__end_at__isnull=True), distinct=True),
    ).annotate(available=F('count') - F('taken'))

    if filters['q']:
        books = books.filter(name__icontains=filters['q'])
    if filters['author'].isdigit():
        books = books.filter(authors__id=int(filters['author']))
    if filters['description']:
        books = books.filter(description__icontains=filters['description'])
    if filters['available']:
        books = books.filter(available__gt=0)
    if filters['sort'] not in SORT_OPTIONS:
        filters['sort'] = 'name'
    books = books.order_by(SORT_OPTIONS[filters['sort']][1], 'id').distinct()

    context = {
        'books': books,
        'authors': Author.objects.all(),
        'filters': filters,
        'sort_options': [(key, label) for key, (label, _) in SORT_OPTIONS.items()],
        'is_filtered': any(filters[key] for key in ('q', 'author', 'description', 'available')),
    }
    return render(request, 'book/book_list.html', context)


@login_required
def book_detail(request, book_id):
    """Show a specific book."""
    book = get_object_or_404(Book.objects.prefetch_related('authors'), pk=book_id)
    context = {
        'book': book,
        'default_return_date': (timezone.localdate() + datetime.timedelta(days=14)).isoformat(),
        'min_return_date': (timezone.localdate() + datetime.timedelta(days=1)).isoformat(),
        'max_return_date': (timezone.localdate() + datetime.timedelta(days=60)).isoformat(),
    }
    if request.user.is_librarian:
        context['open_orders'] = book.order_set.filter(end_at__isnull=True).select_related('user')
    else:
        context['my_open_order'] = book.order_set.filter(user=request.user, end_at__isnull=True).first()
    return render(request, 'book/book_detail.html', context)


@librarian_required
def book_create(request):
    """Add a new book (librarian only)."""
    data = {'count': '10'}
    errors = {}
    selected_authors = []
    if request.method == 'POST':
        data = {key: request.POST.get(key, '').strip() for key in ('name', 'description', 'count')}
        selected_authors = [int(pk) for pk in request.POST.getlist('authors') if pk.isdigit()]

        if not data['name']:
            errors['name'] = 'Title is required.'
        elif len(data['name']) > 128:
            errors['name'] = 'Maximum 128 characters.'
        if len(data['description']) > 256:
            errors['description'] = 'Maximum 256 characters.'
        if not data['count'].isdigit() or int(data['count']) < 1:
            errors['count'] = 'Enter a whole number greater than 0.'

        if not errors:
            authors = list(Author.objects.filter(pk__in=selected_authors))
            book = Book.create(data['name'], data['description'], int(data['count']), authors)
            messages.success(request, f'Book "{book.name}" has been added.')
            return redirect('book_detail', book_id=book.id)

    return render(request, 'book/book_form.html', {
        'data': data, 'errors': errors,
        'authors': Author.objects.all(), 'selected_authors': selected_authors,
    })


@librarian_required
def user_books(request, user_id):
    """Show all books provided to a specific user (librarian only)."""
    reader = get_object_or_404(CustomUser, pk=user_id)
    orders = Order.objects.filter(user=reader).select_related('book').prefetch_related('book__authors')
    context = {
        'reader': reader,
        'open_orders': orders.filter(end_at__isnull=True),
        'closed_orders': orders.filter(end_at__isnull=False),
    }
    return render(request, 'book/user_books.html', context)
