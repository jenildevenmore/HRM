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
        if user.is_superuser:
            return Employee.objects.all()
        try:
            profile = user.profile
            # Super admin sees all, others see only their client's employees
            if profile.role == 'superadmin':
                return Employee.objects.all()
            else:
                return Employee.objects.filter(client=profile.client)
        except:
            return Employee.objects.none()
