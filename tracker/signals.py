from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=get_user_model())
def on_user_created(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    from .services import claim

    UserProfile.for_user(instance)
    # The first account on an install that predates accounts inherits the existing data.
    if get_user_model().objects.count() == 1 and claim.has_orphans():
        claim.claim_orphans(instance)
