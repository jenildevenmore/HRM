from jinja2 import Environment
from django.templatetags.static import static
from django.urls import reverse
from django.middleware.csrf import get_token
from django.utils.html import format_html


def environment(**options):
    env = Environment(**options)
    env.globals.update({
        'static': static,
        'url': reverse,
        'csrf_input': _csrf_input,
        'csrf_token': _csrf_token,
    })
    return env


def _csrf_input(request):
    return format_html(
        '<input type="hidden" name="csrfmiddlewaretoken" value="{}">',
        get_token(request)
    )


def _csrf_token(request):
    return get_token(request)
