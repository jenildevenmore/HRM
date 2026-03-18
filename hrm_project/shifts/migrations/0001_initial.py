from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('clients', '0007_clientrole_enabled_addons_clientrole_module_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='Shift',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('code', models.CharField(blank=True, default='', max_length=30)),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('grace_minutes', models.PositiveIntegerField(default=0)),
                ('is_night_shift', models.BooleanField(default=False)),
                ('weekly_off', models.CharField(blank=True, default='', max_length=60)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shifts', to='clients.client')),
            ],
            options={
                'ordering': ('name',),
                'unique_together': {('client', 'name')},
            },
        ),
    ]
