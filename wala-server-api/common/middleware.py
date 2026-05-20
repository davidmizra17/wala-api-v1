from contextvars import ContextVar

_current_tenant: ContextVar = ContextVar("current_tenant", default=None)


def get_current_tenant():
    return _current_tenant.get()


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_tenant.set(None)
        try:
            if request.user.is_authenticated and hasattr(request.user, "tenant"):
                _current_tenant.set(request.user.tenant)
            return self.get_response(request)
        finally:
            _current_tenant.reset(token)
