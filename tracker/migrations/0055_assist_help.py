import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0054_ui_preferences"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="application",
            name="ai_summary",
            field=models.JSONField(blank=True, default=dict, editable=False, help_text='The latest "what this role really needs" reading of the posting, with red flags (services/assist.py). Separate from the person\'s own summary.'),
        ),
        migrations.AlterField(
            model_name="aiusageevent",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("evaluate", "Evaluate match"), ("tailor", "Tailor CV"), ("prep", "Prep plan"), ("interview_prep", "Interview questions"),
                    ("answer_feedback", "Answer feedback"), ("app_answer", "Application answer"), ("summarise", "Posting summary"),
                    ("suggest_roles", "Role suggestions"), ("message_draft", "Message draft"),
                ],
                max_length=24,
            ),
        ),
        migrations.CreateModel(
            name="InterviewPrep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("application", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="interview_prep", to="tracker.application")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="interview_preps", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
