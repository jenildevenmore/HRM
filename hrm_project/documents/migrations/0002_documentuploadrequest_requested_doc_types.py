from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentuploadrequest',
            name='requested_doc_types',
            field=models.JSONField(blank=True, default=list),
        ),
    ]

