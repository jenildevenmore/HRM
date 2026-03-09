from rest_framework import viewsets
from .models import Employee
from .serializers import EmployeeSerializer
from rest_framework.permissions import IsAuthenticated


class EmployeeViewSet(viewsets.ModelViewSet):

    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter employees by user's client"""
        user = self.request.user
        role_filter = (self.request.query_params.get('role') or '').strip().lower()

        if user.is_superuser:
            qs = Employee.objects.all()
            return qs.filter(role=role_filter) if role_filter in ('employee', 'hr', 'manager') else qs
        try:
            profile = user.profile
            # Super admin sees all, others see only their client's employees
            if profile.role == 'superadmin':
                qs = Employee.objects.all()
            else:
                qs = Employee.objects.filter(client=profile.client)
            if role_filter in ('employee', 'hr', 'manager'):
                qs = qs.filter(role=role_filter)
            return qs
        except:
            return Employee.objects.none()
