from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0005_client_app_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='role_limit',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='ClientRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('slug', models.SlugField(max_length=120)),
                ('base_role', models.CharField(choices=[('employee', 'Employee'), ('hr', 'HR'), ('manager', 'Manager')], default='employee', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='roles', to='clients.client')),
            ],
            options={
                'ordering': ('sort_order', 'name'),
                'unique_together': {('client', 'slug')},
            },
        ),
    ]
