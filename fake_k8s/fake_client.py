# coding=UTF-8
import re
import json
import os
import fake_objects
from fake_resources import FakeResources
from functools import wraps
from flask import current_app as app
from flask_cache import Cache


CACHE = Cache(app, config={'CACHE_TYPE': 'filesystem',
                           'CACHE_DIR': '/tmp/cache'})


def failure_content(status_code, reason, message):
    content = {
        'apiVersion': 'v1',
        'kind': 'Status',
        'code': status_code,
        'reason': reason,
        'message': message,
        'status': 'Failure'
    }
    return content


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


class ObjectOperator(object):
    def __init__(self, target_name, target_namespace,
                 targets, key, content={}):
        kind = 'None'
        fake_resources = FakeResources()
        resource_list = fake_resources.get(os.path.join(targets['base'],
                                           targets['version']), targets)
        for resource in resource_list['response']['resources']:
            if resource['name'] == key:
                kind = resource['kind']
        obj_class = getattr(fake_objects, kind,
                            fake_objects.FakeObject)
        name = target_name or content.get('metadata', {}).get('name')
        if target_namespace is None or not obj_class.namespaced:
            namespace = None
        else:
            namespace = (target_namespace or
                         content.get('metadata', {}).get('namespace') or
                         'default')
        self.obj = obj_class(kind, name,
                             namespace, key, content)
        self.key = key
        self.targets = targets

    def label_filter(self, label_selectors):
        label_pattern = \
            '((?:\\b\S+ (?:in|notin) \([^\)]*\))|(?:!?\\b[^,]+\\b))'
        labels_list = re.findall(label_pattern, label_selectors)
        selectors = []
        for label in labels_list:
            for selector in labelSelectors:
                selector_inst = selector(label)
                if selector_inst.is_available:
                    selectors.append(selector_inst)
                    break
            else:
                raise Exception("Unable to parse selector '%s'" % label)
        return selectors

    def field_filter(self, field_selectors):
        field_pattern = '(\\b[^,]+\\b)'
        fields_list = re.findall(field_pattern, field_selectors)
        selectors = []
        for field in fields_list:
            selector_inst = fieldSelector(field)
            if selector_inst.is_available:
                selectors.append(selector_inst)
            else:
                raise Exception("Unable to parse selector '%s'" % field)
        return selectors

    def ns_filter(self, namespace):
        if namespace and self.obj.namespaced:
            return [NamespaceSelector(namespace)]
        else:
            return []

    def request_handler(func):
        @wraps(func)
        def wrap(self, *args, **kwargs):
            if self.obj.namespaced and self.obj.namespace is not None:
                namespaces = CACHE.get('namespaces') or []
                for ns in namespaces:
                    if ns['metadata']['name'] == self.obj.namespace:
                        break
                else:
                    return failure_content(
                        404, 'NotFound',
                        'namespaces "%s" not found' % self.obj.namespace)
            try:
                if self.targets['operation']:
                    op_method = getattr(self.obj, self.targets['operation'],
                                        None)
                    if not op_method:
                        return failure_content(
                            404, 'NotFound',
                            'the server could not find the requested resource')
                    else:
                        ret = op_method(**kwargs)
                else:
                    ret = func(self, *args, **kwargs)
                if not ret:
                    return failure_content(
                        404, 'NotFound',
                        '%s "%s" not found' % (self.key, self.obj.name))
                return ret
            except Exception as e:
                return failure_content(
                    500, 'InternalServerError', str(e))
        return wrap

    @request_handler
    def create(self, **kwargs):
        objects = CACHE.get(self.key) or []
        for obj in objects:
            if (obj['kind'] == self.obj.kind and
                    obj['metadata']['name'] == self.obj.name and
                    obj['metadata'].get('namespace') == self.obj.namespace):
                return failure_content(
                    409, 'AlreadyExists',
                    '%s "%s" already exists' % (self.key, self.obj.name))
        return self.obj.create()

    @request_handler
    def get(self, **kwargs):
        objects = CACHE.get(self.key) or []
        if self.obj.name:
            for obj in objects:
                if obj['metadata'].get('namespace') == self.obj.namespace \
                        and obj['metadata']['name'] == self.obj.name:
                    return obj
            else:
                return failure_content(
                    404, 'NotFound',
                    '%s "%s" not found' % (self.key, self.obj.name))
        filters = self.ns_filter(self.obj.namespace)
        filters.extend(self.label_filter(kwargs.get('labelSelector', '')))
        filters.extend(self.field_filter(kwargs.get('fieldSelector', '')))
        return {'items': filter(lambda obj: all(f(obj) for f in filters),
                objects), 'kind': '%sList' % self.obj.kind, "apiVersion": "v1"}

    @request_handler
    def update(self, **kwargs):
        return self.obj.update()

    @request_handler
    def replace(self, **kwargs):
        return self.obj.replace()

    @request_handler
    def delete(self, **kwargs):
        return self.obj.delete()


class FakeRequest(object):

    def get_api_targets(func):
        @wraps(func)
        def wrap(self, *args, **kwargs):
            api_targets = kwargs.pop('api_targets')
            endpoint = api_targets['kind'] or api_targets['global_kind']
            if api_targets['kind']:
                target_name = api_targets['name']
                target_namespace = api_targets['global_name']
            else:
                target_name = api_targets['global_name']
                target_namespace = None
            return func(self, target_name, target_namespace,
                        endpoint, api_targets, **kwargs)
        return wrap

    def resource_list(self, version):
        return {
            "code": 200,
            "response": {
                "apiVersion": "v1",
                "groupVersion": version,
                "kind": "APIResourceList",
                "resources": []
            }
        }

    @get_api_targets
    def post(self, target_name, target_namespace, key, api_targets, **kwargs):
        content = json.loads(kwargs['data'])
        obj_op = ObjectOperator(target_name, target_namespace,
                                api_targets, key, content)
        output = obj_op.create(**kwargs)
        return {'code': output.get('code', 201), 'response': output}

    @get_api_targets
    def put(self, target_name, target_namespace, key, api_targets, **kwargs):
        content = json.loads(kwargs['data'])
        obj_op = ObjectOperator(target_name, target_namespace,
                                api_targets, key, content)
        output = obj_op.replace(**kwargs)
        return {'code': output.get('code', 201), 'response': output}

    @get_api_targets
    def patch(self, target_name, target_namespace, key, api_targets, **kwargs):
        content = json.loads(kwargs['data'])
        obj_op = ObjectOperator(target_name, target_namespace,
                                api_targets, key, content)
        output = obj_op.update(**kwargs)
        return {'code': output.get('code', 200), 'response': output}

    @get_api_targets
    def get(self, target_name, target_namespace, key, api_targets, **kwargs):
        obj_op = ObjectOperator(target_name, target_namespace,
                                api_targets, key)
        output = obj_op.get(**kwargs)
        return {'code': output.get('code', 200), 'response': output}

    @get_api_targets
    def delete(self, target_name, target_namespace,
               key, api_targets, **kwargs):
        obj_op = ObjectOperator(target_name, target_namespace,
                                api_targets, key)
        output = obj_op.delete(**kwargs)
        return {'code': output.get('code', 200), 'response': output}
