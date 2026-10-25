"""Account clean-up shared by the classic page and the JSON API."""
from ..models import Document, KnowledgeSource


def delete_stored_files(user) -> None:
    """Delete the files a person stored (documents and knowledge uploads), not just their rows. Call before `user.delete()`."""
    for doc in Document.objects.filter(application__owner=user):
        if doc.file:
            doc.file.delete(save=False)
    for source in KnowledgeSource.objects.filter(owner=user):
        if source.file:
            source.file.delete(save=False)
