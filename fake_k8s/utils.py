# coding=UTF-8
from jinja2 import Environment
import string
import random


CUSTOM_FILTERS = {}


class JinjaEnvironment(Environment):
    def __init__(self, *args, **kwargs):
        super(JinjaEnvironment, self).__init__(*args, **kwargs)
        self.filters.update(CUSTOM_FILTERS)


def custom_filter(func):
    CUSTOM_FILTERS[func.__name__] = func
    return func


@custom_filter
def default_if_none(value, default_value):
    return value if value else default_value


@custom_filter
def datetime(value, dateformat='%Y-%m-%dT%H:%M:%SZ'):
    return value.strftime(dateformat)


@custom_filter
def random_string(value):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for i in xrange(value))


@custom_filter
def random_number(value):
    chars = string.digits
    return ''.join(random.choice(chars) for i in xrange(value))
