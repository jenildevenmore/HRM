from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0004_client_enabled_addons'),
        ('accounts', '0002_userprofile_module_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientPermissionGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('module_permissions', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='permission_groups', to='clients.client')),
            ],
            options={
                'verbose_name': 'Client Permission Group',
                'verbose_name_plural': 'Client Permission Groups',
                'unique_together': {('client', 'name')},
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='permission_group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users', to='accounts.clientpermissiongroup'),
        ),
    ]
