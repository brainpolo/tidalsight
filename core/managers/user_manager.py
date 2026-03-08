import logging

from django.contrib.auth import authenticate, get_user_model, login, logout

User = get_user_model()

logger = logging.getLogger(__name__)


def create_user(
    first_name: str,
    last_name: str,
    username: str,
    email: str,
    password: str,
) -> User:
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    logger.info("Created user: %s (%s)", user.username, user.email)
    return user


def sign_in_user(request, username: str, password: str) -> User | None:
    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        logger.info("Signed in user: %s", user.username)
    return user


def update_profile(
    user, first_name: str, last_name: str, currency: str, timezone: str
) -> User:
    user.first_name = first_name
    user.last_name = last_name
    user.currency = currency
    user.timezone = timezone
    user.save(update_fields=["first_name", "last_name", "currency", "timezone"])
    logger.info("Updated profile for: %s", user.username)
    return user


def sign_out_user(request) -> None:
    logger.info("Signed out user: %s", request.user.username)
    logout(request)
