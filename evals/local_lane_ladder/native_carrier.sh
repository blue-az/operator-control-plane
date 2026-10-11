#!/bin/sh
set -eu
work=$1
pi_config=$2
shift 2
exec /usr/bin/bwrap --die-with-parent --unshare-all --share-net \
 --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /usr/local /usr/local \
 --proc /proc --dev /dev --tmpfs /tmp --dir /tmp/pi-home --dir /pi-config \
 --dir /work --bind "$work" /work --ro-bind /home/ef-tb/.local /work/.local \
 --dir /opt --ro-bind /home/ef-tb/.local-lane-native-v1/pi-wrapper /opt/pi-wrapper \
 --tmpfs /pi-config --ro-bind "$pi_config/models.json" /pi-config/models.json --chdir /work "$@"
