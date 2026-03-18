from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('clients', '0007_clientrole_enabled_addons_clientrole_module_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='CompanyPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=180)),
                ('category', models.CharField(blank=True, default='', max_length=80)),
                ('content', models.TextField(blank=True, default='')),
                ('image_url', models.CharField(blank=True, default='', max_length=500)),
                ('document_url', models.CharField(blank=True, default='', max_length=500)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='company_policies', to='clients.client')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_company_policies', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
                'unique_together': {('client', 'title')},
            },
        ),
    ]
