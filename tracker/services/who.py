"""Pick the user a command-line tool or the MCP server acts for."""
from django.contrib.auth import get_user_model


class WhoError(Exception):
    pass


def resolve_user(username: str | None = None):
    """The named user, else the only superuser, else the only user. Anything ambiguous is an error, never a guess."""
    User = get_user_model()
    if username:
        user = User.objects.filter(**{User.USERNAME_FIELD: username}).first()
        if not user:
            raise WhoError(f'No user named "{username}".')
        return user
    supers = list(User.objects.filter(is_superuser=True))
    if len(supers) == 1:
        return supers[0]
    users = list(User.objects.all())
    if len(users) == 1:
        return users[0]
    if not users:
        raise WhoError("There are no users yet. Run: python manage.py createsuperuser")
    raise WhoError("More than one possible user. Pass one explicitly (--user NAME, or STILLOPEN_USER for the MCP server).")
