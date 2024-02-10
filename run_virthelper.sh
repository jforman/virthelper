#!/bin/bash -x

# Args:
#   $1: path to proxmox API config file (/dev/null otherwise)
#   $2: Parameters to vmbuilder execution.

# Note: Do not pass the --config flag.
# TODO: Figure out a better way to handle the --config flag on the wrapper script.

# Example
# % ./run_virthelper.sh /foo/bar/proxmox-prod-apitoken.txt \
# --debug --cluster proxmox_bos create_vm ....

if ! test -f $1; then
    echo "Proxmox API config file $1 does not exist. Exiting."
    exit 1
fi

./build_container.sh

docker run \
    --rm -it \
    -v `realpath $1`:/proxmox-api-auth.txt:ro \
    jforman/virthelper:latest \
    ./vmbuilder.py --config /proxmox-api-auth.txt ${@:2}
