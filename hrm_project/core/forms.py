from django import forms


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Username', 'autofocus': True}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'}),
    )


class ClientForm(forms.Form):
    ADDON_CHOICES = [
        ('custom_fields', 'Custom Fields'),
        ('dynamic_models', 'Dynamic Models'),
        ('attendance', 'Attendance'),
        ('attendance_location', 'Attendance + Location'),
        ('attendance_selfie_location', 'Attendance + Selfie + Location'),
        ('leave_management', 'Leave Management'),
        ('holidays', 'Holidays'),
        ('payroll', 'Payroll'),
        ('activity_logs', 'Activity Logs'),
        ('settings', 'Settings'),
        ('policy', 'Policy'),
        ('role_management', 'Role Management'),
    ]

    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Client Name'}),
    )
    domain = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. example.com'}),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={'placeholder': 'Client password'},
            render_value=True,
        ),
    )
    schema_name = forms.SlugField(
        required=False,
        max_length=63,
        widget=forms.TextInput(attrs={'placeholder': 'tenant_demo'}),
    )
    admin_username = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Client admin username'}),
    )
    admin_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'placeholder': 'Client admin email'}),
    )
    admin_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={'placeholder': 'Client admin password'},
            render_value=True,
        ),
    )
    enabled_addons = forms.MultipleChoiceField(
        required=False,
        choices=ADDON_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        initial=[k for k, _ in ADDON_CHOICES],
    )
    role_limit = forms.IntegerField(
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'placeholder': 'e.g. 3'}),
    )


class EmployeeForm(forms.Form):
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'First Name'}),
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Last Name'}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'Email Address'}),
    )
    role = forms.ChoiceField(
        choices=[],
    )
    hr = forms.ChoiceField(
        required=False,
        choices=[],
    )
    manager = forms.ChoiceField(
        required=False,
        choices=[],
    )
    joining_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
    )


class CustomFieldForm(forms.Form):
    FIELD_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
    ]

    MODEL_CHOICES = [
        ('Employee', 'Employee'),
        ('Client', 'Client'),
    ]

    model_name = forms.ChoiceField(
        choices=MODEL_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    field_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Field Name'}),
    )
    field_type = forms.ChoiceField(choices=FIELD_TYPE_CHOICES)


class CustomFieldValueForm(forms.Form):
    employee = forms.IntegerField(
        label='Employee ID',
        widget=forms.NumberInput(attrs={'placeholder': 'Employee ID'}),
    )
    field = forms.IntegerField(
        label='Custom Field ID',
        widget=forms.NumberInput(attrs={'placeholder': 'Custom Field ID'}),
    )
    value = forms.CharField(
        widget=forms.Textarea(attrs={'placeholder': 'Value', 'rows': 3}),
    )


class DynamicModelForm(forms.Form):
    client = forms.IntegerField(required=False)
    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'Model name'}),
    )
    slug = forms.SlugField(
        max_length=140,
        widget=forms.TextInput(attrs={'placeholder': 'model-slug'}),
    )
    show_in_employee_form = forms.BooleanField(required=False)


class DynamicFieldForm(forms.Form):
    FIELD_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('boolean', 'Boolean'),
        ('email', 'Email'),
        ('file', 'File'),
        ('image', 'Image'),
    ]

    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'Field name'}),
    )
    key = forms.SlugField(
        max_length=140,
        widget=forms.TextInput(attrs={'placeholder': 'field_key'}),
    )
    field_type = forms.ChoiceField(choices=FIELD_TYPE_CHOICES)
    use_dropdown = forms.BooleanField(required=False)
    required = forms.BooleanField(required=False)
    visible_to_users = forms.BooleanField(required=False, initial=True)
    choices_json = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'placeholder': '["A", "B"]', 'rows': 3}),
    )
    sort_order = forms.IntegerField(required=False, initial=0)


class DynamicRecordForm(forms.Form):
    data_json = forms.CharField(
        widget=forms.Textarea(attrs={'placeholder': '{"key":"value"}', 'rows': 8}),
    )
