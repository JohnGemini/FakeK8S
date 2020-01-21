# coding=UTF-8
# flake8: noqa
import ast
import copy
import random
import string
from datetime import datetime
from flask import current_app as app
from flask_cache import Cache
import utils


CACHE = Cache(app, config=app.config['CACHE_CONFIG'])


def gen_child_name(name, size=5, chars=string.ascii_lowercase + string.digits):
    return '%s-%s' % (name,
                      ''.join(random.choice(chars) for i in xrange(size)))


class FakeObject(object):
    namespaced = False
    template = ''

    def __init__(self, kind, name, namespace, key, content={}):
        self.kind = kind
        self.name = name
        self.namespace = namespace
        self.key = key
        self.content = content

    def render_template(self, **extra_prop):
        env = utils.JinjaEnvironment()
        tmpl = env.from_string(self.template)
        extra_prop['current_time'] = datetime.utcnow()
        return tmpl.render(extra_prop).strip()

    def get(self):
        objects = CACHE.get(self.key) or []
        for obj in objects:
            if (obj['kind'] == self.kind and
                    obj['metadata']['name'] == self.name and
                    obj['metadata'].get('namespace') == self.namespace):
                return obj
        return {}

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
          {% if "unschedulable" in obj.spec and obj.spec.unschedulable %}
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
        return super(Node, self).update()


class Namespace(FakeObject):
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Namespace",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
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
      {% if not status %}
        {% if "phase" in obj.status %}
          {% set status = obj.status.phase %}
        {% elif "ownerReferences" in obj.metadata and obj.metadata.ownerReferences[0].kind == "Job" %}
          {% set status = "Succeeded" %}
        {% else %}
          {% set status = "Running" %}
        {% endif %}
      {% endif %}
      {% set nodeName = node.metadata.name if node else obj.spec.nodeName %}
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Pod",
        "metadata": {
            "creationTimestamp": "{{ current_time|datetime }}",
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
                    "name": "{{ port.name }}",
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
          {% if nodeName %}
            "nodeName": "{{ nodeName }}"
          {% endif %}
        },
        "status": {
          {% if status != "Pending" %}
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
              {% if status == "Succeeded" %}
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
            "hostIP": "127.0.0.1",
            "podIP": "127.0.0.1",
            "startTime": "{{ current_time|datetime }}",
          {% endif %}
            "phase": "{{ status }}"
        }
      }
    '''

    def __pod_scheduler(self):
        nodes = CACHE.get('nodes') or []
        spec = self.content['spec']
        scheduled_node = None
        if 'nodeName' in spec:
            for node in nodes:
                if node['metadata']['name'] == spec['nodeName']:
                    scheduled_node = node
                    break
        else:
            selectors = utils.as_selectors(spec.get('nodeSelector', {}))
            nodeSelectors = spec.get('affinity', {}).get(
                'nodeAffinity', {}
            ).get(
                'requiredDuringSchedulingIgnoredDuringExecution', {}
            ).get('nodeSelectorTerms', [])
            for nodeSelector in nodeSelectors:
                selectors.extend(utils.as_selectors(nodeSelector.get(
                    'matchExpressions', [])))
            match_nodes = filter(
                lambda node: all(selector(node) for selector in selectors),
                nodes)
            if match_nodes:
                scheduled_node = random.choice(match_nodes)
            elif not selectors and nodes:
                scheduled_node = random.choice(nodes)
        return scheduled_node

    def create(self):
        node = self.__pod_scheduler()
        status = 'Pending' if not node else None
        return super(Pod, self).create(node=node, status=status)

    def log(self, **kwargs):
        return {'content': 'This is the log message from the fake client'}

    def __getattr__(self, attr):
        if attr == 'exec':
            return self.exec_command
        else:
            return super(Pod, self).__getattribute__(attr)

    def exec_command(self, **kwargs):
        command = ' '.join(kwargs['command'])
        container = kwargs['container'][0] \
            if isinstance(kwargs['container'], list) else kwargs['container']
        return {'content': (
            "This is the response from the fake client. "
            "Execute '%s' in the container '%s'" % (command, container))
        }


class ReplicationController(FakeObject):
    namespaced = True
    template = '''
      {% set replicas = obj.spec.replicas if "replicas" in obj.spec else 1 %}
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "ReplicationController",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
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
            pod_obj = Pod(pod_template['kind'],
                          pod_template['metadata']['name'],
                          pod_template['metadata']['namespace'],
                          'pods', pod_template)
            pod_obj.create()

    def create(self):
        obj = super(ReplicationController, self).create()
        if obj:
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
                                pod['kind'], pod['metadata']['name'],
                                pod['metadata']['namespace'], 'pods')
                            pod_obj.delete()
        return obj


class Service(FakeObject):
    namespaced = True
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Service",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
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
          "creationTimestamp": "{{ current_time|datetime }}",
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
          "creationTimestamp": "{{ current_time|datetime }}",
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          {% if "ownerReferences" in obj.metadata %}
            "ownerReferences": {{ obj.metadata.ownerReferences }},
          {% endif %}
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
            pod_obj = Pod(pod_template['kind'],
                          pod_template['metadata']['name'],
                          pod_template['metadata']['namespace'],
                          'pods', pod_template)
            pod_obj.create()

    def create(self):
        obj = super(Job, self).create()
        if obj:
            self.__create_child_pods(obj, obj['spec']['completions'])
        return obj

    def delete(self):
        obj = super(Job, self).delete()
        if obj:
            child_pods = self.get_objects_by_references('pods')
            for pod in child_pods:
                pod_obj = Pod(
                    pod['kind'], pod['metadata']['name'],
                    pod['metadata']['namespace'], 'pods')
                pod_obj.delete()
        return obj


class CronJob(FakeObject):
    namespaced = True
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "CronJob",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
          "concurrencyPolicy": "{{ obj.spec.concurrencyPolicy|default_if_none("Allow") }}",
          "schedule": "{{ obj.spec.schedule }}",
          "jobTemplate": {
            "metadata": {{ obj.spec.jobTemplate.metadata|default_if_none("{}") }},
            "spec": {{ obj.spec.jobTemplate.spec }}
          },
          "failedJobsHistoryLimit": {{ obj.spec.failedJobsHistoryLimit|default_if_none(1) }},
          "successfulJobsHistoryLimit": {{ obj.spec.successfulJobsHistoryLimit|default_if_none(3) }},
          "suspend": {{ obj.spec.suspend|default_if_none("False") }}
        },
        "status": {
          "lastScheduleTime": "{{ current_time|datetime }}"
        }
      }
    '''

    def __create_child_job(self, template):
        job_template = copy.deepcopy(template['spec']['jobTemplate'])
        job_template.update({'apiVersion': 'batch/v1', 'kind': 'Job'})
        job_template['metadata'].update({
            'name': gen_child_name(self.name, size=10, chars=string.digits),
            'namespace': self.namespace,
            'ownerReferences': [{
                'apiVersion': template['apiVersion'],
                'kind': self.kind,
                'name': self.name
            }]
        })
        job_obj = Job(job_template['kind'],
                      job_template['metadata']['name'],
                      job_template['metadata']['namespace'],
                      'jobs', job_template)
        job_obj.create()

    def create(self):
        obj = super(CronJob, self).create()
        if obj:
            self.__create_child_job(obj)
        return obj

    def delete(self):
        obj = super(CronJob, self).delete()
        if obj:
            child_jobs = self.get_objects_by_references('jobs')
            for job in child_jobs:
                job_obj = Job(
                    job['kind'], job['metadata']['name'],
                    job['metadata']['namespace'], 'jobs')
                job_obj.delete()
        return obj


class Ingress(FakeObject):
    namespaced = True
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Ingress",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {{ obj.spec }},
        "status": {
          "loadBalancer": {
            "ingress": [
              {
                "ip": "127.0.0.1"
              }
            ]
          }
        }
      }
    '''


class Secret(FakeObject):
    namespaced = True
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Secret",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "type": "{{ obj.type }}",
        "data": {{ obj.data }}
      }
    '''


class PersistentVolumeClaim(FakeObject):
    namespaced = True
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "PersistentVolumeClaim",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {{ obj.spec }},
        "status": {
        {% if bind_pv %}
          "accessModes": {{ bind_pv.spec.accessModes }},
          "capacity": {{ bind_pv.spec.capacity }},
        {% endif %}
          "phase": "{{ "Bound" if bind_pv else "Pending" }}"
        }
      }
    '''

    def __get_bind_pv(self):
        bind_pv = None
        pvs = CACHE.get('persistentvolumes') or []
        spec = self.content['spec']
        for pv in pvs:
            if pv['status']['phase'] != 'Available':
                continue
            elif spec.get('volumeName') == pv['metadata']['name']:
                bind_pv = pv
                break
            selectors = utils.as_selectors(
                spec.get('selector', {}).get('matchLabels', {}))
            selectors.extend(utils.as_selectors(
                spec.get('selector', {}).get('matchExpressions', [])))
            if all(selector(pv) for selector in selectors):
                bind_pv = pv
                break
        return bind_pv

    def create(self):
        bind_pv = self.__get_bind_pv()
        obj = super(PersistentVolumeClaim, self).create(bind_pv=bind_pv)
        if obj and bind_pv:
            update_content = {
                'spec': {
                    'claimRef': {
                        'apiVersion': obj['apiVersion'],
                        'kind': obj['kind'],
                        'name': obj['metadata']['name'],
                        'namespace': obj['metadata']['namespace']
                    }
                }
            }
            pv_obj = PersistentVolume(bind_pv['kind'],
                                      bind_pv['metadata']['name'],
                                      None, 'persistentvolumes',
                                      update_content)
            pv_obj.update(status='Bound')
        return obj

    def delete(self):
        obj = super(PersistentVolumeClaim, self).delete()
        if obj and obj['status']['phase'] == 'Bound':
            pvs = CACHE.get('persistentvolumes') or []
            for pv in pvs:
                claimRef = pv['spec'].get('claimRef')
                if claimRef and claimRef['kind'] == self.kind and \
                        claimRef['name'] == self.name and \
                        claimRef['namespace'] == self.namespace:
                    pv_obj = PersistentVolume(pv['kind'],
                                              pv['metadata']['name'],
                                              None, 'persistentvolumes')
                    if pv['status']['phase'] == 'Bound':
                        pv_obj.update(status='Release')
                    elif pv['status']['phase'] == 'Terminating':
                        pv_obj.delete()
                    break
        return obj


class PersistentVolume(FakeObject):
    template = '''
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "PersistentVolume",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
          "name": "{{ obj.metadata.name }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
        {% if not obj.spec.persistentVolumeReclaimPolicy %}
          "persistentVolumeReclaimPolicy": "Retain",
        {% endif %}
        {% for key, value in obj.spec.items() %}
          {% if value is string %}
            "{{ key }}": "{{ value }}",
          {% else %}
            "{{ key }}": {{ value }},
          {% endif %}
        {% endfor %}
        },
        "status": {
          "phase": "{{ status|default_if_none("Available") }}"
        }
      }
    '''

    def __get_reference_claims(self):
        pvcs = CACHE.get('persistentvolumeclaims') or []
        claims = []
        for pvc in pvcs:
            if pvc['spec'].get('volumeName') == self.name:
                claims.append(pvc)
                continue
            selectors = utils.as_selectors(
                pvc['spec'].get('selector', {}).get('matchLabels', {}))
            selectors.extend(utils.as_selectors(
                pvc['spec'].get('selector', {}).get('matchExpressions', [])))
            if all(selector(self.content) for selector in selectors):
                claims.append(pvc)
        return claims

    def create(self):
        status = 'Available'
        for claim in self.__get_reference_claims():
            if claim['status']['phase'] == 'Pending':
                update_content = {
                    'spec': {'volumeName': self.name},
                }
                pvc_obj = PersistentVolumeClaim(
                    claim['kind'], claim['metadata']['name'],
                    claim['metadata']['namespace'], 'persistentvolumeclaims',
                    update_content)
                pvc_obj.update(bind_pv=self.content)
                self.content['spec']['claimRef'] = {
                    'apiVersion': claim['apiVersion'],
                    'kind': claim['kind'],
                    'name': claim['metadata']['name'],
                    'namespace': claim['metadata']['namespace']
                }
                status = 'Bound'
                break
        return super(PersistentVolume, self).create(status=status)

    def delete(self):
        obj = self.get()
        if obj and obj['spec'].get('claimRef'):
            pvc_obj = PersistentVolumeClaim(
                obj['spec']['claimRef']['kind'],
                obj['spec']['claimRef']['name'],
                obj['spec']['claimRef']['namespace'],
                'persistentvolumeclaims')
            if pvc_obj.get():
                if obj['status']['phase'] != 'Terminating':
                    return self.update(status='Terminating')
                else:
                    return obj
        return super(PersistentVolume, self).delete()


class ReplicaSet(FakeObject):
    namespaced = True
    template = '''
      {% set replicas = obj.spec.replicas if "replicas" in obj.spec else 1 %}
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "ReplicaSet",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          {% if "ownerReferences" in obj.metadata %}
            "ownerReferences": {{ obj.metadata.ownerReferences }},
          {% endif %}
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {{ obj.metadata.annotations|default_if_none("{}") }}
        },
        "spec": {
          "replicas": {{ replicas }},
          "selector": {
            "matchLabels": {{ obj.spec.template.metadata.labels }}
          },
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
            pod_obj = Pod(pod_template['kind'],
                          pod_template['metadata']['name'],
                          pod_template['metadata']['namespace'],
                          'pods', pod_template)
            pod_obj.create()

    def create(self):
        obj = super(ReplicaSet, self).create()
        if obj:
            self.__create_child_pods(obj, obj['spec']['replicas'])
        return obj

    def update(self):
        obj = super(ReplicaSet, self).update()
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
                                pod['kind'], pod['metadata']['name'],
                                pod['metadata']['namespace'], 'pods')
                            pod_obj.delete()
        return obj


class Deployment(FakeObject):
    namespaced = True
    template = '''
      {% set replicas = obj.spec.replicas if "replicas" in obj.spec else 1 %}
      {
        "apiVersion": "{{ obj.apiVersion }}",
        "kind": "Deployment",
        "metadata": {
          "creationTimestamp": "{{ current_time|datetime }}",
          "name": "{{ obj.metadata.name }}",
          "namespace": "{{ obj.metadata.namespace|default_if_none("default") }}",
          "labels": {{ obj.metadata.labels|default_if_none("{}") }},
          "annotations": {
            {% for key, value in obj.metadata.annotations.items() %}
              {% if key != "deployment.kubernetes.io/revision" %}
                {% if value is string %}
                  "{{ key }}": "{{ value }}",
                {% else %}
                  "{{ key }}": {{ value }},
                {% endif %}
              {% endif %}
            {% endfor %}
            {% set revision = (obj.metadata.annotations["deployment.kubernetes.io/revision"]|default_if_none('0')|int) %}
            "deployment.kubernetes.io/revision": "{{ revision + 1 }}"
          }
        },
        "spec": {
          {% if "minReadySeconds" in obj.spec %}
            "minReadySeconds": {{ obj.spec.minReadySeconds }},
          {% endif %}
          {% if "paused" in obj.spec and obj.spec.paused %}
            "paused": True,
          {% endif %}
          "progressDeadlineSeconds": {{ obj.spec.progressDeadlineSeconds|default_if_none(600) }},
          "revisionHistoryLimit": {{ obj.spec.revisionHistoryLimit|default_if_none(10) }},
          "replicas": {{ replicas }},
          "selector": {
            "matchLabels": {{ obj.spec.template.metadata.labels }}
          },
          "strategy": {
            {% set strategy = obj.spec.strategy or {} %}
            {% set type = strategy.type or "RollingUpdate" %}
            {% if type == "RollingUpdate" %}
              {% set maxSurge = strategy.rollingUpdate.maxSurge if strategy.rollingUpdate and "maxSurge" in strategy.rollingUpdate else 1 %}
              {% set maxUnavailable = strategy.rollingUpdate.maxUnavailable if strategy.rollingUpdate and "maxUnavailable" in strategy.rollingUpdate else 1 %}
              "rollingUpdate": {
                {% if maxSurge is string %}
                  "maxSurge": "{{ maxSurge }}",
                {% else %}
                  "maxSurge": {{ maxSurge }},
                {% endif %}
                {% if maxUnavailable is string %}
                  "maxUnavailable": "{{ maxUnavailable }}"
                {% else %}
                  "maxUnavailable": {{ maxUnavailable }}
                {% endif %}
              },
            {% endif %}
            "type": "{{ type }}"
          },
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
          "updatedReplicas": {{ replicas }},
          "observedGeneration": {{ replicas }},
          "readyReplicas": {{ replicas }},
          "replicas": {{ replicas }}
        }
      }
    '''

    def __create_child_rs(self, template, replicas, revision='1'):
        rs_template = copy.deepcopy(template)
        rs_template.update({'apiVersion': 'apps/v1', 'kind': 'ReplicaSet'})
        rs_template['metadata'].update({
            'name': gen_child_name(self.name, size=9),
            'namespace': self.namespace,
            'labels': template['spec']['selector']['matchLabels'],
            'annotations': {
               'deployment.kubernetes.io/revision': revision
            },
            'ownerReferences': [{
                'apiVersion': template['apiVersion'],
                'kind': self.kind,
                'name': self.name
            }]
        })
        rs_obj = ReplicaSet(rs_template['kind'],
                            rs_template['metadata']['name'],
                            rs_template['metadata']['namespace'],
                            'replicasets', rs_template)
        rs_obj.create()

    def create(self):
        if 'annotations' not in self.content['metadata']:
            self.content['metadata']['annotations'] = {}
        obj = super(Deployment, self).create()
        if obj:
            self.__create_child_rs(obj, obj['spec']['replicas'])
        return obj

    def update(self):
        obj = super(Deployment, self).update()
        if obj:
            limit = obj['spec']['revisionHistoryLimit']
            revision = obj['metadata']['annotations'][
                'deployment.kubernetes.io/revision']
            child_rs = self.get_objects_by_references('replicasets')
            for index, rs in enumerate(child_rs):
                rs_obj = ReplicaSet(rs['kind'],
                                    rs['metadata']['name'],
                                    rs['metadata']['namespace'],
                                    'replicasets',
                                    {'spec': {'replicas': 0}})
                rs_obj.update()
                if index >= (limit - 1):
                    rs_obj.delete()
            self.__create_child_rs(obj, obj['spec']['replicas'], revision)
        return obj

    def delete(self):
        obj = self.get()
        if obj:
            for rs in self.get_objects_by_references('replicasets'):
                rs_obj = ReplicaSet(rs['kind'],
                                    rs['metadata']['name'],
                                    rs['metadata']['namespace'],
                                    'replicasets')
                rs_obj.delete()
        return super(Deployment, self).delete()
