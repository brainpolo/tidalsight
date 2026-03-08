from asgiref.sync import iscoroutinefunction
from django.utils.decorators import sync_and_async_middleware


@sync_and_async_middleware
def eager_user_middleware(get_response):
    """Eagerly resolve request.user for async views.

    Django's AuthenticationMiddleware sets request.user to a SimpleLazyObject
    that triggers a synchronous DB hit when first accessed. In async views
    this raises SynchronousOnlyOperation.

    ASGI path: resolves the user via request.auser() (async-safe).
    WSGI path: forces evaluation of the lazy object while still in sync
    context, so that async views (which Django wraps with async_to_sync)
    find an already-resolved user with no DB hit needed.
    """
    if iscoroutinefunction(get_response):

        async def middleware(request):
            request.user = await request.auser()
            return await get_response(request)

    else:

        def middleware(request):
            # Force the lazy SimpleLazyObject to evaluate now (sync context).
            # After this, request.user._wrapped is set and subsequent access
            # from async views proxies without triggering another DB query.
            request.user.is_authenticated
            return get_response(request)

    return middleware
