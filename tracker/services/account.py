"""Account clean-up and profile bookkeeping shared by the JSON API and the admin tools."""
from ..models import Document, KnowledgeSource, SiteConfig


def delete_stored_files(user) -> None:
    """Delete the files a person stored (documents and knowledge uploads), not just their rows. Call before `user.delete()`."""
    for doc in Document.objects.filter(application__owner=user):
        if doc.file:
            doc.file.delete(save=False)
    for source in KnowledgeSource.objects.filter(owner=user):
        if source.file:
            source.file.delete(save=False)


def save_cv_history(user, obj, form) -> None:
    """After a profile or welcome form saved: refresh the knowledge base from the CV and keep every CV change in the history."""
    from . import knowledge
    from .cvversions import CVError, record_master

    knowledge.sync_cv(SiteConfig.for_user(user), user)
    if "profile_cv" in form.changed_data and obj.profile_cv.strip():
        try:
            record_master(user, obj.profile_cv)
        except CVError:
            pass
