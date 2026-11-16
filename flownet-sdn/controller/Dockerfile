# Ryu is unmaintained for Python >= 3.10 and needs an older eventlet, hence the pins.
# (Verified: Ryu 4.34 + eventlet 0.30.2 on Python 3.9 serves the REST API.)
FROM python:3.9-slim
RUN pip install --no-cache-dir "setuptools<66" wheel pbr \
 && pip install --no-cache-dir --no-build-isolation eventlet==0.30.2 ryu==4.34
EXPOSE 6653 8080
# simple_switch_13 : learning-switch behaviour
# ofctl_rest       : REST API for flow/port stats and flow-entry add/delete
# rest_topology    : REST API for LLDP-discovered switches and links
CMD ["ryu-manager", "--observe-links", "--ofp-tcp-listen-port", "6653", \
     "--wsapi-host", "0.0.0.0", "--wsapi-port", "8080", \
     "ryu.app.simple_switch_13", "ryu.app.ofctl_rest", "ryu.app.rest_topology"]
