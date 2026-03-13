from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_documentuploadrequest_requested_doc_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='file_base64',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='document',
            name='file_mime_type',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='document',
            name='file_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
