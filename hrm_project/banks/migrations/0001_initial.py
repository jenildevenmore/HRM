from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('clients', '0007_clientrole_enabled_addons_clientrole_module_permissions'),
        ('employees', '0005_employee_client_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='BankAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bank_name', models.CharField(max_length=120)),
                ('account_holder_name', models.CharField(max_length=120)),
                ('account_number', models.CharField(max_length=50)),
                ('ifsc_code', models.CharField(blank=True, default='', max_length=30)),
                ('branch_name', models.CharField(blank=True, default='', max_length=120)),
                ('upi_id', models.CharField(blank=True, default='', max_length=120)),
                ('is_primary', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_accounts', to='clients.client')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_accounts', to='employees.employee')),
            ],
            options={
                'ordering': ('employee_id', 'bank_name'),
                'unique_together': {('client', 'employee', 'account_number')},
            },
        ),
    ]
