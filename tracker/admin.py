from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import (
    PrepPlan,
    AIUsageEvent,
    Application,
    Bucket,
    Document,
    DocumentKind,
    Event,
    ExpiredPhrase,
    Insight,
    JobSource,
    KnowledgeSource,
    LivenessRun,
    Posting,
    ScanLogEntry,
    ScanRun,
    ScoreBand,
    SiteConfig,
    Source,
    Status,
    UserProfile,
)
from .forms import SecretKeysMixin
from .services import ai, knowledge, liveness, scan
from .services.paperless import PaperlessClient, PaperlessError, push_document


class SiteConfigForm(forms.ModelForm):
    paperless_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the saved token. The PAPERLESS_TOKEN environment variable takes precedence.",
    )

    jooble_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Free key from jooble.org/api/about. Leave blank to keep the saved key. The JOOBLE_API_KEY environment variable takes precedence.",
    )

    usajobs_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Free key from developer.usajobs.gov/apirequest. Leave blank to keep the saved key. The USAJOBS_API_KEY environment variable takes precedence.",
    )

    # write-only secrets: blank keeps what is saved
    email_password = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False),
        help_text="The SMTP password or key (for Brevo, the SMTP key). Stored encrypted and never shown again. Leave blank to keep the saved one.",
    )
    google_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), help_text="Client secret. Stored encrypted. Leave blank to keep the saved one.")
    github_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), help_text="Client secret. Stored encrypted. Leave blank to keep the saved one.")
    facebook_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), help_text="App secret. Stored encrypted. Leave blank to keep the saved one.")

    class Meta:
        model = SiteConfig
        fields = "__all__"

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("email_password"):
            obj.set_email_password(self.cleaned_data["email_password"])
        for provider in ("google", "github", "facebook"):
            if self.cleaned_data.get(f"{provider}_secret"):
                obj.set_social_secret(provider, self.cleaned_data[f"{provider}_secret"])
        if commit:
            obj.save()
        return obj

    def clean_jooble_api_key(self):
        key = self.cleaned_data.get("jooble_api_key", "")
        return key or (self.instance.jooble_api_key if self.instance else "")

    def clean_usajobs_api_key(self):
        key = self.cleaned_data.get("usajobs_api_key", "")
        return key or (self.instance.usajobs_api_key if self.instance else "")

    def clean_paperless_token(self):
        token = self.cleaned_data.get("paperless_token", "")
        return token or (self.instance.paperless_token if self.instance else "")


def _public_base() -> str:
    """The site's public address for the redirect URLs shown in the admin, from the allowed hosts (never a guess at a local one)."""
    from django.conf import settings

    hosts = [h for h in settings.ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1", "*", "[::1]") and not h.startswith(".")]
    return f"https://{hosts[0]}" if hosts else "https://your-site"


@admin.register(SiteConfig)
class SiteConfigAdmin(ModelAdmin):
    form = SiteConfigForm
    fieldsets = (
        (
            "Dashboard",
            {
                "classes": ("tab",),
                "fields": ("site_title", "score_scale", "urgent_days", "apply_followup_days", "auto_close_expired", "followup_emails_enabled", "scan_emails_enabled", "auto_scan_hours", "mcp_remote_enabled"),
                "description": "Follow-up emails need email set up (the Email tab) and `manage.py send_followup_emails` on a schedule (e.g. daily cron) -- enabling this alone does not send anything by itself.",
            },
        ),
        (
            "Registration",
            {
                "classes": ("tab",),
                "fields": ("signup_mode",),
                "description": (
                    "<strong>Open</strong> lets anyone register. New users must confirm their email, so set up the Email tab "
                    "first. Everyone only ever sees their own data."
                ),
            },
        ),
        ("Landing page", {"classes": ("tab",), "fields": ("landing_enabled", "landing_headline", "landing_subheadline", "landing_github_url")}),
        (
            "Job board",
            {
                "classes": ("tab",),
                "fields": ("public_board_enabled", "public_details_indexable", "contact_email"),
                "description": "The public job board (/openings/) shows openings from sources marked 'Show publicly' under Job sources, each with a short excerpt "
                "and a credit link to the original. Remotive's terms forbid this, so it is off for Remotive.",
            },
        ),
        ("Legal", {"classes": ("tab",), "fields": ("privacy_text", "terms_text"), "description": "Shown at /privacy/ and /terms/. Replace the defaults."}),
        ("career-ops", {"classes": ("tab",), "fields": ("careerops_path", "node_command")}),
        ("Open check", {"classes": ("tab",), "fields": ("liveness_mode", "liveness_timeout")}),
        (
            "Email",
            {
                "classes": ("tab",),
                "fields": ("email_host", "email_port", "email_username", "email_password", "email_use_tls", "email_from"),
                "description": (
                    "Needed for sign-up confirmation links, interview reminders, follow-up digests and job alerts. "
                    "<strong>Brevo (free, 300 a day):</strong> host <code>smtp-relay.brevo.com</code>, port <code>587</code>, TLS on, "
                    "username = your Brevo SMTP login, password = an SMTP key from Brevo, sender = an address you verified in Brevo. "
                    "Save, then <a href=\"/tools/email-test/\">send yourself a test email</a>. "
                    "The EMAIL_HOST environment variable, if set, takes precedence over this section."
                ),
            },
        ),
        (
            "Prep plans",
            {
                "classes": ("tab",),
                "fields": ("prep_enabled", "prep_default_weeks", "prep_default_hours", "prep_daily_questions", "prep_max_weeks", "prep_max_active_plans",
                           "prep_questions_per_lesson", "prep_runs_per_day", "prep_check_sources"),
                "description": "A person can turn a job's skill gaps into a short study plan with quiz questions. It is written by their own AI account "
                "(it costs you nothing) and nothing starts until they have read it. Every lesson and question must cite an official link.",
            },
        ),
        (
            "Social sign-in",
            {
                "classes": ("tab",),
                "fields": (
                    "google_login_enabled", "google_client_id", "google_secret",
                    "github_login_enabled", "github_client_id", "github_secret",
                    "facebook_login_enabled", "facebook_client_id", "facebook_secret",
                    "google_allowed_emails",
                ),
                "description": (
                    "All three are free. For each one you want, create an OAuth app with the provider, give it the redirect address "
                    "below, paste its client ID and secret here, and tick the box. Changes apply at once. "
                    "Redirect addresses: <code>{base}/accounts/google/login/callback/</code>, "
                    "<code>{base}/accounts/github/login/callback/</code>, <code>{base}/accounts/facebook/login/callback/</code>. "
                    "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (and the GITHUB_ and FACEBOOK_ ones) in the environment take precedence."
                ).format(base=_public_base()),
            },
        ),
        (
            "Job search keys & writing check",
            {
                "classes": ("tab",),
                "fields": ("jooble_api_key", "usajobs_api_key", "usajobs_email", "languagetool_url"),
                "description": "Optional. Jooble covers Bangladesh, Malaysia and the Gulf, where few job sites publish an open feed. "
                "USAJobs is the official US federal job board's own documented API -- unlike Jooble it also needs the email "
                "address the key was requested with (USAJobs requires it on every request). Without a key those sources are "
                "simply skipped. LanguageTool is unrelated to job search -- it switches on a 'Check writing' button on CVs "
                "and cover letters, self-hosted or pointed at the public instance, off (nothing sent anywhere) while blank.",
            },
        ),
        (
            "Paperless",
            {
                "classes": ("tab",),"fields": ("paperless_enabled", "paperless_url", "paperless_token", "paperless_verify_tls", "paperless_auto_upload")},
        ),
    )
    actions = None

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        SiteConfig.load()
        return HttpResponseRedirect(reverse("admin:tracker_siteconfig_change", args=[1]))

    def response_post_save_change(self, request, obj):
        return HttpResponseRedirect(reverse("admin:tracker_siteconfig_change", args=[1]))


class UserProfileAdminForm(SecretKeysMixin, forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = "__all__"

    def save(self, commit=True):
        instance = super().save(commit=False)
        self.apply_secrets(instance)
        if commit:
            instance.save()
        return instance


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    form = UserProfileAdminForm
    list_display = ("user", "ai_provider", "rag_mode", "complete", "updated_at")
    search_fields = ("user__username", "user__email")
    fieldsets = (
        (None, {"fields": ("user",)}),
        ("What they want", {"fields": ("target_roles", "home_country", "employment_types", "seniority_levels", "industries", "languages", "notice_period", "salary_floor", "deal_breakers", "about", "scan_digest_enabled")}),
        ("CV", {"fields": ("profile_cv",)}),
        (
            "AI evaluation",
            {
                "fields": (
                    "ai_provider", "ai_model", "ai_base_url", "ai_custom_headers", "ai_custom_body", "ai_custom_response_path",
                    "ai_claude_command", "ai_api_key", "clear_ai_key", "ai_timeout", "ai_max_input_chars",
                ),
            },
        ),
        (
            "Retrieval (RAG)",
            {
                "fields": (
                    "rag_enabled", "rag_mode", "rag_top_k", "rag_chunk_chars", "rag_always_chars",
                    "rag_embedding_base_url", "rag_embedding_model", "rag_embedding_key", "clear_rag_key",
                ),
            },
        ),
    )

    @admin.display(description="Complete", boolean=True)
    def complete(self, obj):
        return obj.is_complete


@admin.register(Bucket)
class BucketAdmin(ModelAdmin):
    list_display = ("label", "key", "order", "is_closed")
    list_editable = ("order", "is_closed")
    prepopulated_fields = {"key": ("label",)}


@admin.register(Status)
class StatusAdmin(ModelAdmin):
    list_display = ("name", "bucket", "order", "color", "counts_as_applied", "is_terminal")
    list_editable = ("bucket", "order", "color", "counts_as_applied", "is_terminal")


@admin.register(ScoreBand)
class ScoreBandAdmin(ModelAdmin):
    list_display = ("label", "min_percent", "color")
    list_editable = ("min_percent", "color")


@admin.register(Source)
class SourceAdmin(ModelAdmin):
    list_display = ("name", "host_contains")


@admin.register(ExpiredPhrase)
class ExpiredPhraseAdmin(ModelAdmin):
    list_display = ("phrase", "note")
    search_fields = ("phrase",)


@admin.register(DocumentKind)
class DocumentKindAdmin(ModelAdmin):
    list_display = ("name", "keywords", "paperless_tag", "paperless_document_type", "order")
    list_editable = ("keywords", "paperless_tag", "paperless_document_type", "order")


@admin.register(KnowledgeSource)
class KnowledgeSourceAdmin(ModelAdmin):
    list_display = ("title", "owner", "kind", "enabled", "characters", "passages", "embedded", "updated_at")
    list_filter = ("kind", "enabled")
    search_fields = ("title", "text", "owner__username")
    fields = ("owner", "title", "kind", "enabled", "text", "file")
    actions = ["reindex", "compute_embeddings"]
    change_list_template = "admin/tracker/knowledgesource/change_list.html"

    @admin.display(description="Characters")
    def characters(self, obj):
        return len(obj.text)

    @admin.display(description="Passages")
    def passages(self, obj):
        return obj.chunks.count()

    @admin.display(description="Embedded", boolean=True)
    def embedded(self, obj):
        total = obj.chunks.count()
        return bool(total) and obj.chunks.exclude(embedding=None).count() == total

    def get_urls(self):
        from django.urls import path

        return [
            path("import-careerops/", self.admin_site.admin_view(self.import_careerops_view), name="tracker_knowledgesource_import")
        ] + super().get_urls()

    def import_careerops_view(self, request):
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:tracker_knowledgesource_changelist"))
        done = knowledge.import_careerops(SiteConfig.for_user(request.user), request.user)
        if done:
            self.message_user(request, "Imported from career-ops: " + ", ".join(done) + ".")
        else:
            self.message_user(request, "Nothing found. Check the career-ops folder in Site configuration.", messages.WARNING)
        return HttpResponseRedirect(reverse("admin:tracker_knowledgesource_changelist"))

    def save_model(self, request, obj, form, change):
        try:
            if obj.file and "file" in form.changed_data and not obj.text.strip():
                obj.text = knowledge.extract_text(obj.file.file)
        except knowledge.KnowledgeError as exc:
            self.message_user(request, f"File not read: {exc}", messages.ERROR)
        if not obj.owner_id:
            obj.owner = request.user
        super().save_model(request, obj, form, change)
        count = knowledge.reindex_source(obj)
        self.message_user(request, f"Split into {count} passage(s).")

    @admin.action(description="Rebuild passages")
    def reindex(self, request, queryset):
        total = sum(knowledge.reindex_source(s) for s in queryset)
        self.message_user(request, f"Rebuilt {total} passage(s).")

    @admin.action(description="Compute embeddings now (Embeddings mode)")
    def compute_embeddings(self, request, queryset):
        done = 0
        try:
            for owner in {s.owner for s in queryset.select_related("owner")}:
                done += knowledge.embed_pending(SiteConfig.for_user(owner) if owner else SiteConfig.load(), owner)
        except knowledge.KnowledgeError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return
        self.message_user(request, f"Embedded {done} passage(s).")


class InsightInline(TabularInline):
    model = Insight
    extra = 1


class DocumentInline(TabularInline):
    model = Document
    extra = 0
    fields = ("kind", "title", "file", "source_path", "paperless_id", "paperless_error")
    readonly_fields = ("paperless_id", "paperless_error")


class EventInline(TabularInline):
    model = Event
    extra = 0


def _paperless_client(request, config):
    try:
        return PaperlessClient.from_config(config)
    except PaperlessError as exc:
        messages.error(request, str(exc))
        return None


@admin.register(Application)
class ApplicationAdmin(ModelAdmin):
    list_display = ("careerops_num", "owner", "company", "role", "status", "match", "decision", "live_state", "deadline", "applied_date")
    list_display_links = ("company", "role")
    list_editable = ("status",)
    list_filter = ("owner", "status", "status__bucket", "live_state", "risk", "source")
    search_fields = ("company", "role", "notes", "summary", "owner__username")
    date_hierarchy = "found_date"
    inlines = [InsightInline, DocumentInline, EventInline]
    readonly_fields = ("live_state", "live_detail", "live_checked_at", "ai_evaluated_at", "ai_method", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("owner", "company", "role", "url", "source", "status", "careerops_num")}),
        ("Job description", {"fields": ("description", "ai_evaluated_at", "ai_method")}),
        ("Evaluation", {"fields": ("score", "decision", "legitimacy", "risk", "summary", "next_action", "advertised_pay", "report_path")}),
        ("Dates", {"fields": ("found_date", "applied_date", "deadline", "follow_up_date")}),
        ("Application sent", {"fields": ("applied_cv", "applied_channel", "applied_note", "jd_at_apply")}),
        ("Notes", {"fields": ("notes",)}),
        ("Open / closed check", {"fields": ("live_state", "live_detail", "live_checked_at")}),
    )
    def save_model(self, request, obj, form, change):
        if not obj.owner_id:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

    actions = ["evaluate_match", "mark_applied", "mark_discarded", "check_open_status", "push_documents_to_paperless"]

    @admin.action(description="Evaluate match (AI provider, or keyword match if AI is off)")
    def evaluate_match(self, request, queryset):
        ok, failed = 0, []
        for app in queryset.select_related("owner"):
            try:
                ai.evaluate_application(app)  # uses the application owner's own AI settings and profile
                ok += 1
            except ai.AIError as exc:
                failed.append(f"{app.company}: {exc}")
        if ok:
            self.message_user(request, f"Evaluated {ok} application(s).")
        for line in failed[:5]:
            self.message_user(request, line, messages.ERROR)

    @admin.display(description="Match")
    def match(self, obj):
        pct = obj.match_percent(SiteConfig.load().score_scale)
        return "N/A" if pct is None else f"{pct}%"

    def _set_status(self, request, queryset, name):
        status = Status.objects.filter(name__iexact=name).first()
        if not status:
            self.message_user(request, f'No status named "{name}". Create it under Statuses.', messages.ERROR)
            return
        for app in queryset:
            app.status = status
            if status.counts_as_applied and not app.applied_date:
                app.applied_date = timezone.localdate()
            app.save()
            Event.objects.create(application=app, kind="applied" if status.counts_as_applied else "status", text=f"Status set to {status.name}")
        self.message_user(request, f"{queryset.count()} application(s) set to {status.name}.")

    @admin.action(description="Mark as Applied (stamps today as the applied date)")
    def mark_applied(self, request, queryset):
        self._set_status(request, queryset, "Applied")

    @admin.action(description="Mark as Discarded")
    def mark_discarded(self, request, queryset):
        self._set_status(request, queryset, "Discarded")

    @admin.action(description="Check whether the postings are still open")
    def check_open_status(self, request, queryset):
        config = SiteConfig.load()
        done = 0
        for app in queryset.exclude(url=""):
            state, detail = liveness.check_url(app.url, config)
            Application.objects.filter(pk=app.pk).update(live_state=state, live_detail=detail[:300], live_checked_at=timezone.now())
            done += 1
        self.message_user(request, f"Checked {done} posting(s).")

    @admin.action(description="Push documents to Paperless-ngx")
    def push_documents_to_paperless(self, request, queryset):
        config = SiteConfig.load()
        client = _paperless_client(request, config)
        if not client:
            return
        ok = bad = 0
        for doc in Document.objects.filter(application__in=queryset, paperless_id__isnull=True):
            if push_document(doc, client, config):
                ok += 1
            else:
                bad += 1
        self.message_user(request, f"Pushed {ok} document(s); {bad} not confirmed (see each document's error).")


@admin.register(Document)
class DocumentAdmin(ModelAdmin):
    list_display = ("title", "application", "kind", "paperless_id", "created_at")
    list_filter = ("kind",)
    search_fields = ("title", "application__company")
    readonly_fields = ("paperless_id", "paperless_error")
    actions = ["push_to_paperless"]

    @admin.action(description="Push to Paperless-ngx")
    def push_to_paperless(self, request, queryset):
        config = SiteConfig.load()
        client = _paperless_client(request, config)
        if not client:
            return
        ok = sum(1 for d in queryset if push_document(d, client, config))
        self.message_user(request, f"{ok} of {queryset.count()} pushed.")


@admin.register(LivenessRun)
class LivenessRunAdmin(ModelAdmin):
    list_display = ("started_at", "finished_at", "running", "done", "total", "error")
    readonly_fields = [f.name for f in LivenessRun._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(JobSource)
class JobSourceAdmin(ModelAdmin):
    list_display = ("name", "connector", "board_token", "owner", "enabled", "show_publicly")
    list_editable = ("enabled", "show_publicly")
    list_filter = ("connector", "enabled", "show_publicly", "owner")
    search_fields = ("name", "board_token")


@admin.register(Posting)
class PostingAdmin(ModelAdmin):
    list_display = ("title", "company", "source", "location", "first_seen_at", "last_seen_at", "repost_flag")
    list_filter = ("source",)
    search_fields = ("title", "company", "title_key", "url")
    readonly_fields = [f.name for f in Posting._meta.fields]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Repost pattern", boolean=True)
    def repost_flag(self, obj):
        return bool(scan.repost_signal(obj))


class ScanLogEntryInline(TabularInline):
    model = ScanLogEntry
    extra = 0
    fields = ("source_name", "connector", "found", "matched", "added", "duplicates", "error")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ScanRun)
class ScanRunAdmin(ModelAdmin):
    list_display = ("owner", "started_at", "finished_at", "running", "done", "total", "found", "added", "error")
    readonly_fields = [f.name for f in ScanRun._meta.fields]
    inlines = [ScanLogEntryInline]

    def has_add_permission(self, request):
        return False


@admin.register(AIUsageEvent)
class AIUsageEventAdmin(ModelAdmin):
    list_display = ("owner", "provider", "purpose", "input_tokens", "output_tokens", "cost_usd", "cost_is_estimate", "created_at")
    list_filter = ("provider", "purpose", "cost_is_estimate")
    search_fields = ("owner__username",)
    readonly_fields = [f.name for f in AIUsageEvent._meta.fields]

    def has_add_permission(self, request):
        return False


# People and groups in the same look as everything else (Unfold's own forms and base classes).
User = get_user_model()
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(PrepPlan)
class PrepPlanAdmin(ModelAdmin):
    list_display = ("title", "owner", "application", "status", "weeks_count", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "owner__username", "owner__email")
    readonly_fields = ("owner", "application", "gap_skills", "generator", "progress", "error", "created_at", "approved_at")
    exclude = ()
