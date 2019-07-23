# coding=UTF-8
from jinja2 import Environment
import string
import random
import re


CUSTOM_FILTERS = {}


class NamespaceSelector(object):
    def __init__(self, namespace):
        self.namespace = namespace

    def __call__(self, obj):
        return obj['metadata']['namespace'] == self.namespace


class Selector(object):
    pattern = ''

    def __init__(self, selector):
        self.selector = selector

    @property
    def requirements(self):
        if not hasattr(self, '_requirements'):
            match = re.match(self.pattern, self.selector)
            if not match:
                return
            self._requirements = match.groupdict()
        return self._requirements

    @property
    def is_available(self):
        return bool(self.requirements)


class EqualityBasedSelector(Selector):
    pattern = '^(?P<key>[^!\s]+)\s*(?P<operator>=|!=)\s*(?P<value>\S+)$'

    def __call__(self, obj):
        label_value = obj['metadata'].get('labels', {}).get(
            self.requirements['key'])
        return (self.requirements['operator'] == '!=') == \
            (label_value != self.requirements['value'])


class fieldSelector(EqualityBasedSelector):

    def __match(self, obj, fields):
        field = next(fields, None)
        if not field:
            return (self.requirements['operator'] == '!=') == \
                (obj != self.requirements['value'])
        else:
            if field in obj:
                return self.__match(obj[field], fields)
            else:
                return self.requirements['operator'] == '!='

    def __call__(self, obj):
        fields = iter(re.findall('\w+', self.requirements['key']))
        return self.__match(obj, fields)


class SetBasedSelector(Selector):
    pattern = '^(?P<key>\S+)\s+(?P<operator>in|notin)\s+(?P<values>\(.*\))$'

    def __call__(self, obj):
        label_value = obj['metadata'].get('labels', {}).get(
            self.requirements['key'])
        values = re.findall('\\b(\S+)\\b', self.requirements['values'])
        return (self.requirements['operator'] == 'notin') == \
            (label_value not in values)


class EmptyBasedSelector(Selector):
    pattern = '^(?P<empty>!?)(?P<key>\S+)$'

    def __call__(self, obj):
        labels = obj['metadata'].get('labels', {})
        return bool(self.requirements['empty']) == \
            (self.requirements['key'] not in labels)


labelSelectors = [EqualityBasedSelector, SetBasedSelector, EmptyBasedSelector]


def as_selectors(values):
    selectors = []
    if isinstance(values, dict):
        for key, value in values.iteritems():
            selectors.append(EqualityBasedSelector('%s = %s' % (key, value)))
    elif isinstance(values, list):
        for expression in values:
            if expression['operator'] in ['In', 'NotIn']:
                selectors.append(SetBasedSelector(
                    '%s %s (%s)' % (expression['key'],
                                    expression['operator'].lower(),
                                    ','.join(expression['values']))))
            elif expression['operator'] in ['Exists', 'DoesNotExist']:
                selectors.append(EmptyBasedSelector(
                    '%s%s' %
                    ('' if expression['operator'] == 'Exists' else '!',
                     expression['key'])
                ))
            else:
                raise Exception('Invalid operator: %s' %
                                expression['operator'])
    else:
        raise Exception('Unable to convert %s to instances of Selector' %
                        values)
    return selectors


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
