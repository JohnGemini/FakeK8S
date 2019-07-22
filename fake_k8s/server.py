# coding=UTF-8
from flask import Flask, json, request
import settings
import argparse
import os
import re


app = Flask(__name__)
app.config.from_object(settings)
cxt = app.app_context()
cxt.push()


from fake_client import FakeRequest
from fake_resources import FakeResources


@app.route('/')
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def api(path=''):
    url_pattern = ('^(\/(?P<base>[^\/]+))?(\/(?P<version>v1|[^\/]+\/[^\/]+))?'
                   '(\/(?P<global_kind>[^\/]+))?(\/(?P<global_name>[^\/]+))?'
                   '(\/(?P<kind>[^\/]+))?(\/(?P<name>[^\/]+))?'
                   '(\/(?P<operation>[^\/]+))?')
    match = re.match(url_pattern, '/' + path)
    assert match is not None, \
        ("The request url does not match with '%s'" % url_pattern)
    api_targets = match.groupdict()
    if api_targets['base'] and api_targets['version'] and \
            api_targets['global_kind']:
        session = FakeRequest()
        method = getattr(session, request.method.lower())
        output = method(api_targets=api_targets, data=request.data or {},
                        **request.args)
    else:
        resources = FakeResources()
        output = resources.get(path, api_targets)
    response = app.response_class(
        response=json.dumps(output['response']),
        status=output['code'],
        mimetype='application/json'
    )
    return response

@app.route('/version')
def version():
    version = {
        "buildDate": "2018-06-06T08:00:59Z",
        "compiler": "gc",
        "gitCommit": "5ca598b4ba5abb89bb773071ce452e33fb66339d",
        "gitTreeState": "clean",
        "gitVersion": "v1.10.4",
        "goVersion": "go1.9.3",
        "major": "1",
        "minor": "10",
        "platform": "linux/amd64"
    }
    response = app.response_class(
        response=json.dumps(version),
        status=200,
        mimetype='application/json'
    )
    return response


@app.route('/openapi/v2')
def openapi():
    swagger_path = os.path.join(os.path.dirname(__file__), 'swagger.json')
    with open(swagger_path) as f:
        swagger = json.load(f)
    response = app.response_class(
        response=json.dumps(swagger, indent=2),
        status=200,
        mimetype='application/json'
    )
    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache-dir', dest='cache_dir',
                        help='Directory to store cache')
    args = parser.parse_args()
    if args.cache_dir:
        app.config['CACHE_CONFIG']['CACHE_DIR'] = args.cache_dir
    app.run('0.0.0.0', 6443)

cxt.pop()
