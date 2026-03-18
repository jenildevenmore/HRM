from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0006_client_role_limit_clientrole'),
        ('employees', '0004_alter_employee_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='client_role',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='clients.clientrole'),
        ),
    ]
