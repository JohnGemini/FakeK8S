# coding=UTF-8
# flake8: noqa
import ast
import copy
import random
import string
from datetime import datetime
from flask import current_app as app
from flask_cache import Cache
from jinja2 import Template


CACHE = Cache(app, config={'CACHE_TYPE': 'filesystem',
                           'CACHE_DIR': '/tmp/cache'})


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
        tmpl = Template(self.template)
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
          "annotations": {{ obj.metadata.annotations if obj.metadata.annotations else "{}" }}
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
          "labels": {{ obj.metadata.labels if obj.metadata.labels else "{}" }},
          "annotations": {{ obj.metadata.annotations if obj.metadata.annotations else "{}" }}
        },
        "status": {
          "phase": "Active"
        }
      }
    '''


class Pod(FakeObject):
    namespaced = True
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Pod",
        "metadata": {
            "name": "{{ obj.metadata.name }}",
            "namespace": "{{ obj.metadata.namespace if obj.metadata.namespace else "default" }}",
            {% if "ownerReferences" in obj.metadata %}
              "ownerReferences": {{ obj.metadata.ownerReferences }},
            {% endif %}
            "labels": {{ obj.metadata.labels if obj.metadata.labels else "{}" }},
            "annotations": {{ obj.metadata.annotations if obj.metadata.annotations else "{}" }}
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
                    "protocol": "{{ port.protocol if port.protocol else "TCP" }}"
                  },
                {% endfor %}
                ],
                "resources": {{ container.resources if container.resources else "{}" }},
                "volumeMounts": {{ container.volumeMounts if container.volumeMounts else "[]" }}
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
                "lastTransitionTime": "{{ current_time }}",
                "status": "True",
                "type": "{{ type }}"
              },
            {% endfor %}
            ],
            "containerStatuses": [
            {% for container in obj.spec.containers %}
              {
                  "containerID": "docker://{% for n in range(12) %}{{ [0,1,2,3,4,5,6,7,8,9]|random }}{% endfor %}",
                  "image": "{{ container.image }}",
                  "name": "{{ container.name }}",
                  "ready": True,
                  "restartCount": 0,
                  "state": {
                      "running": {
                        "startedAt": "{{ current_time }}"
                      }
                  }
              },
            {% endfor %}
            ],
            "hostIP": "slave",
            "phase": "Running",
            "podIP": "127.0.0.1",
            "startTime": "{{ current_time }}"
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
          "namespace": "{{ obj.metadata.namespace if obj.metadata.namespace else "default" }}",
          "labels": {{ obj.metadata.labels if obj.metadata.labels else "{}" }},
          "annotations": {{ obj.metadata.annotations if obj.metadata.annotations else "{}" }}
        },
        "spec": {
          "replicas": {{ replicas }},
          "selector": {{ obj.spec.template.metadata.labels }},
          "template": {
            "metadata": {
              "labels": {{ obj.spec.template.metadata.labels if obj.spec.template.metadata.labels else "{}" }},
              "annotations": {{ obj.spec.template.metadata.annotations if obj.spec.template.metadata.annotations else "{}" }}
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

    def __gen_child_name(self):
        chars = string.ascii_lowercase + string.digits
        return '%s-%s' % (self.name,
                          ''.join(random.choice(chars) for i in xrange(5)))

    def __create_child_pods(self, template, replicas):
        for replica in xrange(replicas):
            pod_template = copy.deepcopy(template)
            pod_template.update({'apiVersion': 'v1', 'kind': 'Pod'})
            pod_template['metadata'].update({
                'name': self.__gen_child_name(),
                'namespace': self.namespace,
                'ownerReferences': [{
                    'apiVersion': 'v1',
                    'kind': self.kind,
                    'name': self.name
                }]
            })
            pod_obj = Pod('Pod', pod_template['metadata']['name'],
                          self.namespace, 'pods',
                          pod_template)
            pod_obj.create()

    def create(self):
        content = super(ReplicationController, self).create()
        self.__create_child_pods(content['spec']['template'],
                                 content['spec']['replicas'])
        return content

    def update(self):
        obj = super(ReplicationController, self).update()
        if obj:
            replicas = obj['spec']['replicas']
            child_pods = self.get_objects_by_references('pods')
            childs_num = len(child_pods)
            if childs_num != replicas:
                if childs_num < replicas:
                    self.__create_child_pods(obj['spec']['template'],
                                             replicas - childs_num)
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
          "namespace": "{{ obj.metadata.namespace if obj.metadata.namespace else "default" }}",
          "labels": {{ obj.metadata.labels if obj.metadata.labels else "{}" }},
          "annotations": {{ obj.metadata.annotations if obj.metadata.annotations else "{}" }}
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
                    "nodePort": 3{% for n in range(4) %}{{ [0,1,2,3,4,5,6,7,8,9]|random }}{% endfor %},
                  {% endif %}
                {% endif %}
                "port": {{ port.port }},
                "protocol": "{{ port.protocol if port.protocol else "TCP" }}",
                "targetPort": {{ port.targetPort if port.targetPort else port.port }}
              },
            {% endfor %}
          ],
          "selector": {{ obj.spec.selector }},
          "type": "{{ obj.spec.type if obj.spec.type else "ClusterIP" }}",
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
          "namespace": "{{ obj.metadata.namespace if obj.metadata.namespace else "default" }}",
          "labels": {{ obj.metadata.labels if obj.metadata.labels else "{}" }},
          "annotations": {{ obj.metadata.annotations if obj.metadata.annotations else "{}" }}
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
