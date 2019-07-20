FROM python:2-alpine
ARG K8S_VERSION
RUN pip install flask Flask-Ext Flask-Cache && \
    sed -i 's/flask.ext.cache/flask_cache/' \
    /usr/local/lib/python2.7/site-packages/flask_cache/jinja2ext.py
COPY fake_k8s /fake_k8s
WORKDIR /fake_k8s
RUN wget https://raw.githubusercontent.com/kubernetes/kubernetes/${K8S_VERSION}/api/openapi-spec/swagger.json
EXPOSE 6443
ENTRYPOINT ["python", "server.py"]
