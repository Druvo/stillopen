from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone

from .models import (
    Application,
    Bucket,
    Document,
    DocumentKind,
    Event,
    ExpiredPhrase,
    Insight,
    LivenessRun,
    ScoreBand,
    SiteConfig,
    Source,
    Status,
)
from .services import liveness
from .services.paperless import PaperlessClient, PaperlessError, push_document


class SiteConfigForm(forms.ModelForm):
    paperless_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the saved token. The PAPERLESS_TOKEN environment variable takes precedence.",
    )

    class Meta:
        model = SiteConfig
        fields = "__all__"

    def clean_paperless_token(self):
        token = self.cleaned_data.get("paperless_token", "")
        return token or (self.instance.paperless_token if self.instance else "")


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    form = SiteConfigForm
    fieldsets = (
        ("Dashboard", {"fields": ("site_title", "score_scale", "urgent_days", "auto_close_expired")}),
        ("career-ops import", {"fields": ("careerops_path", "node_command")}),
        ("Open / closed check", {"fields": ("liveness_mode", "liveness_timeout")}),
        (
            "Paperless-ngx",
            {"fields": ("paperless_enabled", "paperless_url", "paperless_token", "paperless_verify_tls", "paperless_auto_upload")},
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


@admin.register(Bucket)
class BucketAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "order", "is_closed")
    list_editable = ("order", "is_closed")
    prepopulated_fields = {"key": ("label",)}


@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ("name", "bucket", "order", "color", "counts_as_applied", "is_terminal")
    list_editable = ("bucket", "order", "color", "counts_as_applied", "is_terminal")


@admin.register(ScoreBand)
class ScoreBandAdmin(admin.ModelAdmin):
    list_display = ("label", "min_percent", "color")
    list_editable = ("min_percent", "color")


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "host_contains")


@admin.register(ExpiredPhrase)
class ExpiredPhraseAdmin(admin.ModelAdmin):
    list_display = ("phrase", "note")
    search_fields = ("phrase",)


@admin.register(DocumentKind)
class DocumentKindAdmin(admin.ModelAdmin):
    list_display = ("name", "keywords", "paperless_tag", "paperless_document_type", "order")
    list_editable = ("keywords", "paperless_tag", "paperless_document_type", "order")


class InsightInline(admin.TabularInline):
    model = Insight
    extra = 1


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    fields = ("kind", "title", "file", "source_path", "paperless_id", "paperless_error")
    readonly_fields = ("paperless_id", "paperless_error")


class EventInline(admin.TabularInline):
    model = Event
    extra = 0


def _paperless_client(request, config):
    try:
        return PaperlessClient.from_config(config)
    except PaperlessError as exc:
        messages.error(request, str(exc))
        return None


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("careerops_num", "company", "role", "status", "match", "decision", "live_state", "deadline", "applied_date")
    list_display_links = ("company", "role")
    list_editable = ("status",)
    list_filter = ("status", "status__bucket", "live_state", "risk", "source")
    search_fields = ("company", "role", "notes", "summary")
    date_hierarchy = "found_date"
    inlines = [InsightInline, DocumentInline, EventInline]
    readonly_fields = ("live_state", "live_detail", "live_checked_at", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("company", "role", "url", "source", "status", "careerops_num")}),
        ("Evaluation", {"fields": ("score", "decision", "legitimacy", "risk", "summary", "next_action", "advertised_pay", "report_path")}),
        ("Dates", {"fields": ("found_date", "applied_date", "deadline")}),
        ("Notes", {"fields": ("notes",)}),
        ("Open / closed check", {"fields": ("live_state", "live_detail", "live_checked_at")}),
    )
    actions = ["mark_applied", "mark_discarded", "check_open_status", "push_documents_to_paperless"]

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
class DocumentAdmin(admin.ModelAdmin):
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
class LivenessRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "finished_at", "running", "done", "total", "error")
    readonly_fields = [f.name for f in LivenessRun._meta.fields]

    def has_add_permission(self, request):
        return False
