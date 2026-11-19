from django.contrib import admin
from django.urls import reverse

from .models import UserProfile, candidate, elections


admin.site.site_header = "Blockchain Admin"
admin.site.site_title = "Blockchain Control Panel"
admin.site.index_title = "Manage Elections, Candidates, and Votes"


@admin.register(elections)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "scope", "ends_at", "is_open", "candidates_count")
    list_filter = ("scope",)
    search_fields = ("name",)
    ordering = ("-ends_at",)
    readonly_fields = ("is_open", "candidates_count")

    fieldsets = (
        ("Election Info", {
            "fields": ("name", "scope", "description", "ends_at")
        }),
        ("Status", {
            "fields": ("is_open", "candidates_count")
        }),
    )


@admin.register(candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("id", "candidatename", "elections", "vote")
    list_filter = ("elections",)
    search_fields = ("candidatename", "elections__name")
    ordering = ("elections", "candidatename")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "date_of_birth", "created_at")
    search_fields = ("user__username", "user__email")
    change_list_template = "admin/vote/userprofile/change_list.html"

    def changelist_view(self, request, extra_context=None):
        context = extra_context or {}
        try:
            context["signup_url"] = reverse("signup")
        except Exception:  # pragma: no cover - URL resolution errors
            context["signup_url"] = None
        return super().changelist_view(request, extra_context=context)