FROM python:3

COPY requirements.txt ./

RUN apt-get -y update && \
    apt install -y libvirt-dev

RUN pip install --no-cache-dir -r requirements.txt

COPY ./configs /configs
COPY proxmox_ubuntu_cloud.py .
COPY ubuntu_cloud.py .
COPY vmbuilder.py .
COPY vmtypes.py .
