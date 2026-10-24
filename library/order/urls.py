from django.urls import path

from . import views

urlpatterns = [
    path('', views.order_list, name='order_list'),
    path('my/', views.my_orders, name='my_orders'),
    path('create/', views.order_create, name='order_create'),
    path('<int:order_id>/close/', views.order_close, name='order_close'),
]
