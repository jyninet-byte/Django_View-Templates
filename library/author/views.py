from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from authentication.decorators import librarian_required

from .models import Author

NAME_MAX_LENGTH = 20


@librarian_required
def author_list(request):
    """Show all authors and a form to add a new one (librarian only)."""
    authors = Author.objects.annotate(books_count=Count('books')).prefetch_related('books')
    return render(request, 'author/author_list.html',
                  {'authors': authors, 'data': {}, 'errors': {}})


@librarian_required
@require_POST
def author_create(request):
    """Create a new author (librarian only)."""
    data = {key: request.POST.get(key, '').strip() for key in ('name', 'surname', 'patronymic')}
    errors = {}
    for field, label in (('name', 'Name'), ('surname', 'Surname')):
        if not data[field]:
            errors[field] = f'{label} is required.'
    for field in data:
        if len(data[field]) > NAME_MAX_LENGTH:
            errors[field] = f'Maximum {NAME_MAX_LENGTH} characters.'

    if errors:
        authors = Author.objects.annotate(books_count=Count('books')).prefetch_related('books')
        messages.error(request, 'Please correct the errors below.')
        return render(request, 'author/author_list.html',
                      {'authors': authors, 'data': data, 'errors': errors}, status=400)

    author = Author(**data)
    author.save()
    messages.success(request, f'Author {author.full_name} has been added.')
    return redirect('author_list')


@librarian_required
@require_POST
def author_delete(request, author_id):
    """Remove an author if he is not attached to any book (librarian only)."""
    author = get_object_or_404(Author, pk=author_id)
    books_count = author.books.count()
    if books_count:
        messages.error(request, f'{author.full_name} cannot be removed: '
                                f'the author is attached to {books_count} book(s).')
    else:
        name = author.full_name
        author.delete()
        messages.success(request, f'Author {name} has been removed.')
    return redirect('author_list')
