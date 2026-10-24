import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from authentication.decorators import librarian_required, visitor_required
from book.models import Book

from .models import Order

MAX_ORDER_DAYS = 60
STATUSES = (
    ('', 'All'),
    ('open', 'Open'),
    ('overdue', 'Overdue'),
    ('closed', 'Closed'),
)


def _filter_by_status(orders, status):
    if status == 'open':
        return orders.filter(end_at__isnull=True)
    if status == 'overdue':
        return orders.filter(end_at__isnull=True, plated_end_at__lt=timezone.now())
    if status == 'closed':
        return orders.filter(end_at__isnull=False)
    return orders


@librarian_required
def order_list(request):
    """Show all orders (librarian only)."""
    status = request.GET.get('status', '')
    query = request.GET.get('q', '').strip()
    orders = Order.objects.select_related('book', 'user')
    orders = _filter_by_status(orders, status)
    if query:
        from django.db.models import Q
        orders = orders.filter(Q(book__name__icontains=query) | Q(user__email__icontains=query)
                               | Q(user__last_name__icontains=query) | Q(user__first_name__icontains=query))
    return render(request, 'order/order_list.html',
                  {'orders': orders, 'status': status, 'statuses': STATUSES, 'query': query})


@login_required
def my_orders(request):
    """Show all orders of the current user."""
    status = request.GET.get('status', '')
    orders = _filter_by_status(Order.objects.filter(user=request.user).select_related('book'), status)
    return render(request, 'order/my_orders.html',
                  {'orders': orders, 'status': status, 'statuses': STATUSES})


@visitor_required
@require_POST
def order_create(request):
    """Create an order for a book (ordinary user only)."""
    book = get_object_or_404(Book, pk=request.POST.get('book_id') or 0)

    try:
        return_date = datetime.date.fromisoformat(request.POST.get('plated_end_at', ''))
    except ValueError:
        messages.error(request, 'Choose a valid return date.')
        return redirect('book_detail', book_id=book.id)

    today = timezone.localdate()
    if not today < return_date <= today + datetime.timedelta(days=MAX_ORDER_DAYS):
        messages.error(request, f'Return date must be between tomorrow and {MAX_ORDER_DAYS} days from today.')
        return redirect('book_detail', book_id=book.id)

    if Order.objects.filter(user=request.user, book=book, end_at__isnull=True).exists():
        messages.warning(request, 'You already have this book.')
        return redirect('book_detail', book_id=book.id)

    plated_end_at = timezone.make_aware(datetime.datetime.combine(return_date, datetime.time(18, 0)))
    order = Order.create(request.user, book, plated_end_at)
    if order is None:
        messages.error(request, 'Sorry, there are no free copies of this book right now.')
        return redirect('book_detail', book_id=book.id)

    messages.success(request, f'"{book.name}" is yours until {return_date:%d.%m.%Y}. Enjoy reading!')
    return redirect('my_orders')


@librarian_required
@require_POST
def order_close(request, order_id):
    """Close an order - the book has been returned (librarian only)."""
    order = get_object_or_404(Order.objects.select_related('book'), pk=order_id)
    if order.end_at is not None:
        messages.info(request, f'Order #{order.id} is already closed.')
    else:
        order.update(end_at=timezone.now())
        messages.success(request, f'Order #{order.id} is closed. "{order.book.name}" is back in the library.')

    next_url = request.POST.get('next', '')
    if next_url.startswith('/') and not next_url.startswith('//'):
        return redirect(next_url)
    return redirect('order_list')
