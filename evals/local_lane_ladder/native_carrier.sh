#!/bin/sh
set -eu
work=$1; shift
exec /usr/bin/bwrap --die-with-parent --unshare-all --share-net \
 --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /usr/local /usr/local \
 --proc /proc --dev /dev --tmpfs /tmp --dir /work --bind "$work" /work --ro-bind /home/ef-tb/.local /work/.local --dir /opt --ro-bind /home/ef-tb/.local-lane-native-v1/pi-wrapper /opt/pi-wrapper \
 --tmpfs /work/home --tmpfs /work/pi-config --ro-bind "$work/pi-config/models.json" /work/pi-config/models.json --chdir /work "$@"
