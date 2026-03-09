from django.urls import path
from core import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('reset-password/', views.reset_password_view, name='reset_password'),

    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Clients
    path('clients/', views.client_list, name='client_list'),
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/delete/', views.client_delete, name='client_delete'),
    path('permissions/', views.permission_list, name='permission_list'),

    # Employees
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/create/', views.employee_create, name='employee_create'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/<int:pk>/edit/', views.employee_edit, name='employee_edit'),
    path('employees/<int:pk>/delete/', views.employee_delete, name='employee_delete'),

    # Leaves
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/types/', views.leave_type_list, name='leave_type_list'),
    path('leaves/types/<int:pk>/delete/', views.leave_type_delete, name='leave_type_delete'),
    path('leaves/balance/', views.leave_balance, name='leave_balance'),
    path('leaves/create/', views.leave_create, name='leave_create'),
    path('leaves/<int:pk>/review/', views.leave_review, name='leave_review'),
    path('leaves/<int:pk>/cancel/', views.leave_cancel, name='leave_cancel'),
    path('leaves/<int:pk>/delete/', views.leave_delete, name='leave_delete'),

    # Custom Fields
    path('custom-fields/', views.custom_field_list, name='custom_field_list'),
    path('custom-fields/create/', views.custom_field_create, name='custom_field_create'),
    path('custom-fields/<int:pk>/edit/', views.custom_field_edit, name='custom_field_edit'),
    path('custom-fields/<int:pk>/delete/', views.custom_field_delete, name='custom_field_delete'),

    # Dynamic Models
    path('dynamic-models/', views.dynamic_model_list, name='dynamic_model_list'),
    path('dynamic-models/create/', views.dynamic_model_create, name='dynamic_model_create'),
    path('dynamic-models/create-attendance/', views.dynamic_model_create_attendance, name='dynamic_model_create_attendance'),
    path('dynamic-models/<int:pk>/edit/', views.dynamic_model_edit, name='dynamic_model_edit'),
    path('dynamic-models/<int:pk>/delete/', views.dynamic_model_delete, name='dynamic_model_delete'),

    # Dynamic Fields
    path('dynamic-models/<int:model_id>/fields/', views.dynamic_field_list, name='dynamic_field_list'),
    path('dynamic-models/<int:model_id>/fields/create/', views.dynamic_field_create, name='dynamic_field_create'),
    path('dynamic-models/<int:model_id>/fields/<int:pk>/edit/', views.dynamic_field_edit, name='dynamic_field_edit'),
    path('dynamic-models/<int:model_id>/fields/<int:pk>/delete/', views.dynamic_field_delete, name='dynamic_field_delete'),

    # Dynamic Records
    path('dynamic-models/<int:model_id>/records/', views.dynamic_record_list, name='dynamic_record_list'),
    path('dynamic-models/<int:model_id>/records/create/', views.dynamic_record_create, name='dynamic_record_create'),
    path('dynamic-models/<int:model_id>/records/<int:pk>/edit/', views.dynamic_record_edit, name='dynamic_record_edit'),
    path('dynamic-models/<int:model_id>/records/<int:pk>/delete/', views.dynamic_record_delete, name='dynamic_record_delete'),

    # Dynamic Entity Screens (form-based, appears in Main nav)
    path('dynamic-entities/<int:model_id>/', views.dynamic_entity_list, name='dynamic_entity_list'),
    path('dynamic-entities/<int:model_id>/create/', views.dynamic_entity_create, name='dynamic_entity_create'),
    path('dynamic-entities/<int:model_id>/punch/', views.dynamic_entity_punch, name='dynamic_entity_punch'),
    path('dynamic-entities/<int:model_id>/<int:pk>/edit/', views.dynamic_entity_edit, name='dynamic_entity_edit'),
    path('dynamic-entities/<int:model_id>/<int:pk>/delete/', views.dynamic_entity_delete, name='dynamic_entity_delete'),
]
