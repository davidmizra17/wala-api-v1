from threading import local

_thread_locals = local()


def get_current_tenant():
    return getattr(_thread_locals, "tenant", None)


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.tenant = None

        if request.user.is_authenticated and hasattr(request.user, "tenant"):
            _thread_locals.tenant = request.user.tenant

        response = self.get_response(request)
        return response
