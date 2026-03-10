"""
URL configuration for hrm_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView

from accounts.views import UserProfileViewSet, ClientPermissionGroupViewSet
from accounts.serializers import CustomTokenObtainPairSerializer
from employees.views import EmployeeViewSet
from custom_fields.views import CustomFieldViewSet, CustomFieldValueViewSet
from clients.views import ClientViewSet, ClientRoleViewSet
from dynamic_models.views import DynamicModelViewSet, DynamicFieldViewSet, DynamicRecordViewSet, AutoClockoutRunView
from leaves.views import LeaveRequestViewSet, LeaveTypeViewSet, LeaveBalanceView
from holidays.views import HolidayViewSet
from payroll.views import PayrollPolicyViewSet, EmployeeCompensationViewSet, PayrollReportView
from policies.views import CompanyPolicyViewSet
from activity_logs.views import ActivityLogViewSet
from shifts.views import ShiftViewSet
from banks.views import BankAccountViewSet

router = DefaultRouter()

router.register("accounts", UserProfileViewSet, basename="accounts")
router.register("account-groups", ClientPermissionGroupViewSet, basename="account-groups")
router.register("clients", ClientViewSet, basename="clients")
router.register("client-roles", ClientRoleViewSet, basename="client-roles")
router.register("employees", EmployeeViewSet, basename="employees")
router.register("custom-fields", CustomFieldViewSet, basename="custom-fields")
router.register("custom-field-values", CustomFieldValueViewSet, basename="custom-field-values")
router.register("dynamic-models", DynamicModelViewSet, basename="dynamic-models")
router.register("dynamic-fields", DynamicFieldViewSet, basename="dynamic-fields")
router.register("dynamic-records", DynamicRecordViewSet, basename="dynamic-records")
router.register("leaves", LeaveRequestViewSet, basename="leaves")
router.register("leave-types", LeaveTypeViewSet, basename="leave-types")
router.register("holidays", HolidayViewSet, basename="holidays")
router.register("shifts", ShiftViewSet, basename="shifts")
router.register("bank-accounts", BankAccountViewSet, basename="bank-accounts")
router.register("payroll-policy", PayrollPolicyViewSet, basename="payroll-policy")
router.register("employee-compensation", EmployeeCompensationViewSet, basename="employee-compensation")
router.register("company-policies", CompanyPolicyViewSet, basename="company-policies")
router.register("activity-logs", ActivityLogViewSet, basename="activity-logs")

# Custom token view with profile info
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

urlpatterns = [

    path('admin/', admin.site.urls),

    path('api/leave-balance/', LeaveBalanceView.as_view()),
    path('api/payroll-report/', PayrollReportView.as_view()),
    path('api/attendance/auto-clockout/run/', AutoClockoutRunView.as_view()),
    path('api/', include(router.urls)),

    path('api/token/', CustomTokenObtainPairView.as_view()),
    path('api/token/refresh/', TokenRefreshView.as_view()),
    path('', include('core.urls')),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
