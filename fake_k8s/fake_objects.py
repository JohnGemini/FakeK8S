# coding=UTF-8
# flake8: noqa
import ast
import copy
import random
import string
from datetime import datetime
from flask import current_app as app
from flask_cache import Cache
from utils import JinjaEnvironment


CACHE = Cache(app, config=app.config['CACHE_CONFIG'])


def gen_child_name(name, size=5):
    chars = string.ascii_lowercase + string.digits
    return '%s-%s' % (name,
                      ''.join(random.choice(chars) for i in xrange(size)))


class FakeObject(object):
    namespaced = False
    template = ''

    def __init__(self, kind, name, namespace, key, content):
        self.kind = kind
        self.name = name
        self.namespace = namespace
        self.key = key
        self.content = content

    def render_template(self, **extra_prop):
        env = JinjaEnvironment()
        tmpl = env.from_string(self.template)
        return tmpl.render(extra_prop).strip()

    def create(self, **extra_prop):
        objects = CACHE.get(self.key) or []
        if self.template:
            extra_prop['obj'] = self.content
            rendered_template = self.render_template(**extra_prop)
            content = ast.literal_eval(rendered_template)
        else:
            content = self.content
        objects.append(content)
        CACHE.set(self.key, objects)
        return content

    def __partial_update(self, obj, value):
        for k, v in value.iteritems():
            if isinstance(obj.get(k), dict):
                self.__partial_update(obj[k], v)
            elif v is None:
                obj.pop(k, None)
            else:
                obj[k] = v

    def update(self, **extra_prop):
        content = {}
        objects = CACHE.get(self.key) or []
        for obj in objects:
            if obj['metadata']['name'] == self.name and \
                    obj['metadata'].get('namespace') == self.namespace:
                content = copy.deepcopy(obj)
                self.__partial_update(content, self.content)
                if self.template:
                    extra_prop['obj'] = content
                    rendered_template = self.render_template(**extra_prop)
                    content = ast.literal_eval(rendered_template)
                obj.update(content)
                break
        CACHE.set(self.key, objects)
        return content

    def replace(self, **extra_prop):
        content = {}
        objects = CACHE.get(self.key) or []
        for obj in objects:
            if obj['metadata']['name'] == self.name and \
                    obj['metadata'].get('namespace') == self.namespace:
                if self.template:
                    extra_prop['obj'] = self.content
                    rendered_template = self.render_template(**extra_prop)
                    content = ast.literal_eval(rendered_template)
                else:
                    content = self.content
                obj.update(content)
                break
        CACHE.set(self.key, objects)
        return content

    def delete(self):
        content = {}
        objects = CACHE.get(self.key) or []
        for index, obj in enumerate(objects):
            if obj['metadata']['name'] == self.name and \
                    obj['metadata'].get('namespace') == self.namespace:
                content = objects.pop(index)
                break
        CACHE.set(self.key, objects)
        return content

    def get_objects_by_references(self, key):
        objects = CACHE.get(key) or []
        ret = []
        for obj in objects:
            refs = obj['metadata'].get('ownerReferences', [])
            for ref in refs:
                if ref['kind'] == self.kind and ref['name'] == self.name:
                    ret.append(obj)
        return ret


class Node(FakeObject):
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Node",
        "metadata": {
          "name": "{{ obj.metadata.name }}",
          "labels": {
              "beta.kubernetes.io/arch": "amd64",
              "beta.kubernetes.io/os": "linux",
              {% if "labels" in obj.metadata %}
                {% for key, value in obj.metadata.labels.items() %}
                  {% if value is string %}
                    "{{ key }}": "{{ value }}",
                  {% else %}
                    "{{ key }}": {{ value }},
                  {% endif %}
                {% endfor %}
              {% endif %}
              "kubernetes.io/hostname": "{{ obj.metadata.name }}"
          },
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
          "externalID": "{{ obj.metadata.name }}",
          "podCIDR": "127.0.0.0/24",
          {% if obj.spec.unschedulable %}
            "unschedulable": True
          {% endif %}
        },
        "status": {
            "addresses": [
                {
                    "address": "127.0.0.1",
                    "type": "InternalIP"
                },
                {
                    "address": "{{ obj.metadata.name }}",
                    "type": "Hostname"
                }
            ],
            "allocatable": {
                "alpha.kubernetes.io/nvidia-gpu": "0",
                "cpu": "8",
                "ephemeral-storage": "107374182400",
                "hugepages-2Mi": "0",
                "memory": "16777216Ki",
                "pods": "110"
            },
            "capacity": {
                "alpha.kubernetes.io/nvidia-gpu": "0",
                "cpu": "8",
                "ephemeral-storage": "104857600Ki",
                "hugepages-2Mi": "0",
                "memory": "16777216Ki",
                "pods": "110"
            },
            "conditions": [
              {
                  "message": "kubelet is posting ready status",
                  "reason": "KubeletReady",
                  "status": "True",
                  "type": "Ready"
              }
            ],
            "images": [
            ],
            "nodeInfo": {
                "architecture": "amd64",
                "bootID": "f391568e-1adb-4b09-bcf1-bd4a4656e241",
                "containerRuntimeVersion": "docker://18.6.1",
                "kernelVersion": "4.4.0-101-generic",
                "kubeProxyVersion": "v1.10.4",
                "kubeletVersion": "v1.10.4",
                "machineID": "66f3f4cf26c749d29b2d23ca6d229664",
                "operatingSystem": "linux",
                "osImage": "Ubuntu 16.04.3 LTS",
                "systemUUID": "205FC311-D1E4-4C77-6FD4-9D041AC3070F"
            }
        }
      }
    '''

    def update(self):
        spec = self.content.get('spec', {})
        if spec.get('unschedulable') is not True:
            spec.pop('unschedulable', None)
        super(Node, self).update()


class Namespace(FakeObject):
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Namespace",
        "metadata": {
          "name": "{{ obj.metadata.name }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "status": {
          "phase": "Active"
        }
      }
    '''


class Pod(FakeObject):
    namespaced = True
    template = '''
      {% set parent = obj.metadata.ownerReferences[0].kind if obj.metadata.ownerReferences else "None" %}
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Pod",
        "metadata": {
            "name": "{{ obj.metadata.name }}",
            "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
            {% if "ownerReferences" in obj.metadata %}
              "ownerReferences": {{ obj.metadata.ownerReferences }},
            {% endif %}
            "labels": {{ obj.metadata.labels|default_if_none("{}") }},
            "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
        {% for key, value in obj.spec.items() %}
          {% if key == "containers" %}
            "containers": [
            {% for container in value %}
              {
                "image": "{{ container.image }}",
                "name": "{{ container.name }}",
                "ports": [
                {% for port in container.ports %}
                  {
                  {% if "name" in port %}
                    "name": "port.name",
                  {% endif %}
                    "containerPort": {{ port.containerPort }},
                    "protocol": "{{ port.protocol|default_if_none("TCP") }}"
                  },
                {% endfor %}
                ],
                "resources": {{ container.resources|default_if_none("{}") }},
                "volumeMounts": {{ container.volumeMounts|default_if_none("[]") }}
              },
            {% endfor %}
            ],
          {% elif value is string %}
            "{{ key }}": "{{ value }}",
          {% else %}
            "{{ key }}": {{ value }},
          {% endif %}
        {% endfor %}
            "nodeName": "slave"
        },
        "status": {
            "conditions": [
            {% for type in ["Initialized", "Ready", "PodScheduled"] %}
              {
                "lastProbeTime": None,
                "lastTransitionTime": "{{ current_time|datetime }}",
                "status": "True",
                "type": "{{ type }}"
              },
            {% endfor %}
            ],
            "containerStatuses": [
            {% for container in obj.spec.containers %}
              {
                  "containerID": "docker://{{ 12|random_string }}",
                  "image": "{{ container.image }}",
                  "name": "{{ container.name }}",
                  "restartCount": 0,
              {% if parent == "Job" %}
                "ready": False,
                "state": {
                    "terminated": {
                      "startedAt": "{{ current_time|datetime }}",
                      "finishedAt": "{{ current_time|datetime }}",
                      "reason": "Completed"
                    }
                }
              {% else %}
                "ready": True,
                "state": {
                    "running": {
                      "startedAt": "{{ current_time|datetime }}"
                    }
                }
              {% endif %}
              },
            {% endfor %}
            ],
            "hostIP": "slave",
            "phase": "{{ "Succeeded" if parent == "Job" else "Running" }}",
            "podIP": "127.0.0.1",
            "startTime": "{{ current_time|datetime }}"
        }
      }
    '''

    def create(self):
        return super(Pod, self).create(current_time=datetime.utcnow())

    def update(self):
        return super(Pod, self).update(current_time=datetime.utcnow())

    def log(self, **kwargs):
        return {'content': 'This is the log message from the fake client'}


class ReplicationController(FakeObject):
    namespaced = True
    template = '''
      {% set replicas = obj.spec.replicas if "replicas" in obj.spec else 1 %}
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "ReplicationController",
        "metadata": {
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
          "replicas": {{ replicas }},
          "selector": {{ obj.spec.template.metadata.labels }},
          "template": {
            "metadata": {
              "labels": {{ obj.spec.template.metadata.labels|default_if_none("{}") }},
              "annotations": {{ obj.spec.template.metadata.annotations|default_if_none("{}") }}
            },
            "spec": {{ obj.spec.template.spec }}
          }
        },
        "status": {
          "availableReplicas": {{ replicas }},
          "fullyLabeledReplicas": {{ replicas }},
          "observedGeneration": {{ replicas }},
          "readyReplicas": {{ replicas }},
          "replicas": {{ replicas }}
        }
      }
    '''

    def __create_child_pods(self, template, replicas):
        for replica in xrange(replicas):
            pod_template = copy.deepcopy(template['spec']['template'])
            pod_template.update({'apiVersion': 'v1', 'kind': 'Pod'})
            pod_template['metadata'].update({
                'name': gen_child_name(self.name),
                'namespace': self.namespace,
                'ownerReferences': [{
                    'apiVersion': template['apiVersion'],
                    'kind': self.kind,
                    'name': self.name
                }]
            })
            pod_obj = Pod('Pod', pod_template['metadata']['name'],
                          self.namespace, 'pods',
                          pod_template)
            pod_obj.create()

    def create(self):
        obj = super(ReplicationController, self).create()
        self.__create_child_pods(obj, obj['spec']['replicas'])
        return obj

    def update(self):
        obj = super(ReplicationController, self).update()
        if obj:
            replicas = obj['spec']['replicas']
            child_pods = self.get_objects_by_references('pods')
            childs_num = len(child_pods)
            if childs_num != replicas:
                if childs_num < replicas:
                    self.__create_child_pods(obj, replicas - childs_num)
                elif childs_num > replicas:
                    remove_num = childs_num - replicas
                    for index, pod in enumerate(reversed(child_pods)):
                        if index < remove_num:
                            pod_obj = Pod(
                                'Pod', pod['metadata']['name'],
                                 self.namespace,
                                'pods', pod)
                            pod_obj.delete()
        return obj


class Service(FakeObject):
    namespaced = True
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Service",
        "metadata": {
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
          {% if "externalIPs" in obj.spec %}
            "externalIPs": {{ obj.spec.externalIPs }},
          {% endif %}
          "ports": [
            {% for port in obj.spec.ports %}
              {
                {% if "name" in port %}
                "name": "{{ port.name }}",
                {% endif %}
                {% if obj.spec.type in ["LoadBalancer", "NodePort"] %}
                  {% if "nodePort" in port %}
                    "nodePort": {{ port.nodePort }},
                  {% else %}
                    "nodePort": 3{{ 4|random_number }},
                  {% endif %}
                {% endif %}
                "port": {{ port.port }},
                "protocol": "{{ port.protocol|default_if_none("TCP") }}",
                "targetPort": {{ port.targetPort|default_if_none(port.port) }}
              },
            {% endfor %}
          ],
          "selector": {{ obj.spec.selector }},
          "type": "{{ obj.spec.type|default_if_none("ClusterIP") }}",
          "clusterIP": "127.0.0.1",
          "externalTrafficPolicy": "Cluster",
          "sessionAffinity": "None"
        },
        "status": {
            "loadBalancer": {
            {% if obj.spec.type == "LoadBalancer" %}
              "ingress": [
                {
                    "ip": "127.0.0.1"
                }
              ]
            {% endif %}
            }
        }
      }
    '''


class NetworkPolicy(FakeObject):
    namespaced = True
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "NetworkPolicy",
        "metadata": {
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
        {% if "ingress" in obj.spec %}
          "ingress": {{ obj.spec.ingress }},
        {% endif %}
        {% if "egress" in obj.spec %}
          "egress": {{ obj.spec.egress }},
        {% endif %}
          "podSelector": {{ obj.spec.podSelector }},
          "policyTypes": [
            {% if obj.spec.ingress or "Ingress" in obj.spec.policyTypes or not obj.spec.policyTypes %}
              "Ingress",
            {% endif %}
            {% if obj.spec.egress or "Egress" in obj.spec.policyTypes %}
              "Egress"
            {% endif %}
          ]
        }
      }
    '''


class Job(FakeObject):
    namespaced = True
    template = '''
      {% set parallelism = obj.spec.parallelism|default_if_none(1) %}
      {% set completions = obj.spec.completions|default_if_none(parallelism) %}
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Job",
        "metadata": {
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
          "backoffLimit": {{ obj.spec.backoffLimit if "backoffLimit" in obj.spec else 6 }},
          "parallelism": {{ parallelism }},
          "completions": {{ completions }},
          "selector": {
            "matchLabels": {
              "job-name": "{{ obj.metadata.name }}"
            }
          },
          "template": {
            "metadata": {
              "labels": {
              {% if "labels" in obj.spec.template.metadata %}
                {% for key, value in obj.spec.template.metadata.labels.items() %}
                  {% if value is string %}
                    "{{ key }}": "{{ value }}",
                  {% else %}
                    "{{ key }}": {{ value }},
                  {% endif %}
                {% endfor %}
              {% endif %}
                "job-name": "{{ obj.metadata.name }}"
              },
              "annotations": {{ obj.spec.template.metadata.annotations|default_if_none("{}") }}
            },
            "spec": {{ obj.spec.template.spec }}
          }
        },
        "status": {
          "conditions": [
            {
              "lastProbeTime": "{{ current_time|datetime }}",
              "lastTransitionTime": "{{ current_time|datetime }}",
              "status": "True",
              "type": "Complete"
            }
          ],
          "completionTime": "{{ current_time|datetime }}",
          "startTime": "{{ current_time|datetime }}",
          "succeeded": {{ completions }}
        }
      }
    '''

    def __create_child_pods(self, template, completions):
        for completion in xrange(completions):
            pod_template = copy.deepcopy(template['spec']['template'])
            pod_template.update({'apiVersion': 'v1', 'kind': 'Pod'})
            pod_template['metadata'].update({
                'name': gen_child_name(self.name),
                'namespace': self.namespace,
                'ownerReferences': [{
                    'apiVersion': template['apiVersion'],
                    'kind': self.kind,
                    'name': self.name
                }]
            })
            pod_obj = Pod('Pod', pod_template['metadata']['name'],
                          self.namespace, 'pods',
                          pod_template)
            pod_obj.create()

    def create(self):
        obj = super(Job, self).create(current_time=datetime.utcnow())
        self.__create_child_pods(obj, obj['spec']['completions'])
        return obj

    def delete(self):
        obj = super(Job, self).delete()
        if obj:
            child_pods = self.get_objects_by_references('pods')
            for pod in child_pods:
                pod_obj = Pod(
                    'Pod', pod['metadata']['name'],
                     self.namespace, 'pods', pod)
                pod_obj.delete()
        return obj
