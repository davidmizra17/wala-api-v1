import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Channel",
            fields=[
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[("whatsapp", "WhatsApp"), ("instagram", "Instagram")],
                        default="whatsapp",
                        max_length=20,
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("wa_phone_id", models.CharField(blank=True, max_length=128)),
                ("wa_token", models.CharField(blank=True, max_length=512)),
                ("verify_token", models.CharField(blank=True, max_length=128)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channels_channel_set",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
