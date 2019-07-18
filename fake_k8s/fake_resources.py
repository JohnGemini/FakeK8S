import json
import os
import re
import copy


CWD = os.path.dirname(__file__)
swagger_path = os.path.join(CWD, 'swagger.json')


def gen_api_groups():
    url_pattern = ('^\/(?P<base>[^\/]+)\/(?P<version>v1|'
                   '(?!v1\/)[^\/]+\/[^\/]+)\/(?P<name>[^\/]+)(?:\/)?$')
    with open(swagger_path) as f:
        swagger = json.load(f)
    resource_list = {
        'api': {},
        'apis': {}
    }
    for path in swagger['paths']:
        match = re.match(url_pattern, path)
        if match:
            result = match.groupdict()
            key = 'apis' if '/' in result['version'] else 'api'
            definition = swagger['paths'][path].get('get') or \
                swagger['paths'][path].get('post')
            group_version_kind = definition['x-kubernetes-group-version-kind']
            resource_definition = {
                "categories": [
                    "all"
                ],
                "kind": group_version_kind['kind'],
                "name": result['name'],
                "namespaced": True,
                "singularName": "",
                "verbs": [
                    "get",
                    "list",
                    "create",
                    "delete",
                    "deletecollection",
                    "patch",
                    "update",
                    "watch"
                ]
            }
            if group_version_kind['group']:
                resource_list[key].setdefault(group_version_kind['group'], {})
                resource_list[key][group_version_kind['group']].setdefault(
                        group_version_kind['version'], [])
                resource_list[key][group_version_kind['group']][
                    group_version_kind['version']].append(resource_definition)
            else:
                resource_list[key].setdefault(group_version_kind['version'],
                                              [])
                resource_list[key][group_version_kind['version']].append(
                    resource_definition)
    with open('resource_list.json', 'w') as f:
        json.dump(resource_list, f, indent=2)


class FakeResources(object):

    def __init__(self):
        with open(os.path.join(CWD, 'resource_list.json')) as f:
            self.resource_list = json.load(f)

    def _get_paths(self, data, paths, parent='/'):
        if isinstance(data, dict):
            for path, value in data.iteritems():
                joined_path = os.path.join(parent, path)
                paths.append(joined_path)
                self._get_paths(value, paths, joined_path)
        return paths

    def _traverse_from_keys(self, keys, data):
        key = keys.pop(0)
        value = data[key]
        if not keys:
            return value
        else:
            return self._traverse_from_keys(keys, value)

    def _get_api_versions(self):
        return {
            "kind": "APIVersions",
            "serverAddressByClientCIDRs": [
                {
                    "clientCIDR": "0.0.0.0/0",
                    "serverAddress": "127.0.0.1:6443"
                }
            ],
            "versions": self.resource_list['api'].keys()
        }

    def _get_api_group(self, group, group_versions):
        versions = map(lambda version: {
            'groupVersion': "%s/%s" % (group, version), "version": version},
            group_versions)
        return {
            "name": group,
            "preferredVersion": versions[0],
            "serverAddressByClientCIDRs": None,
            "versions": versions
        }

    def _get_api_groups(self, path):
        keys = filter(None, path.split('/'))
        result = self._traverse_from_keys(copy.deepcopy(keys),
                                          self.resource_list)
        last_key = keys.pop()
        if last_key == 'apps':
            groups = []
            for group, group_versions in result.iteritems():
                groups.append(self._get_api_group(group,
                                                  group_versions.keys()))
            return {
                "apiVersion": "v1",
                "kind": "APIGroupList",
                "groups": groups
            }
        else:
            api_group = self._get_api_group(last_key, result.keys())
            api_group.update({
                "apiVersion": "v1",
                "kind": "APIGroup"
            })
            return api_group

    def _get_api_resource_list(self, path):
        keys = filter(None, path.split('/'))
        result = self._traverse_from_keys(copy.deepcopy(keys),
                                          self.resource_list)
        base = keys.pop(0)
        api_resource_list = {
            "groupVersion": '/'.join(keys),
            "kind": "APIResourceList",
            "resources": result
        }
        if base != 'api':
            api_resource_list['apiVersion'] = 'v1'
        return api_resource_list

    def get(self, path, api_targets):
        if not api_targets['base']:
            paths = self._get_paths(self.resource_list, [])
            return {'code': 200, 'response': {'paths': paths}}
        elif not api_targets['version']:
            if api_targets['base'] == 'api':
                return {'code': 200, 'response': self._get_api_versions()}
            else:
                return {'code': 200, 'response': self._get_api_groups(path)}
        else:
            return {'code': 200, 'response': self._get_api_resource_list(path)}


if not os.path.exists(os.path.join(CWD, 'resource_list.json')):
    gen_api_groups()
