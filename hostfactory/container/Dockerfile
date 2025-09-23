FROM mcr.microsoft.com/mirror/docker/library/ubuntu:22.04 AS build
# To build:
# docker build -t <NAME:VER> . --output=.
# ex. docker build -t azurecc:latest .
#     docker run -v /opt/ibm/spectrumcomputing/hostfactory/log/:/hostfactory/log 
#                -v /opt/ibm/spectrumcomputing/hostfactory/conf:/hostfactory/conf 
#                -v /opt/ibm/spectrumcomputing/hostfactory/work:/hostfactory/work
#                --network host 
#                -it azurecc:latest /bin/bash

ENV EGO_TOP=/opt/ibm/spectrumcomputing
ENV HF_TOP=/opt/ibm/spectrumcomputing/hostfactory
ENV HF_VERSION=1.1
ENV HF_LOGDIR=$HF_TOP/log
ENV HF_CONFDIR=$HF_TOP/conf
ENV HF_WORKDIR=$HF_TOP/work
ENV PRO_SCRIPTDIR=$HF_TOP/$HF_VERSION/providerplugins/azurecc/scripts
ENV PRO_VENV=$HF_TOP/$HF_VERSION/providerplugins/azurecc/venv

WORKDIR $PRO_SCRIPTDIR

RUN apt update && apt install -y \
    ca-certificates \
    language-pack-en \
    lsb-release \
    sudo \
    nano \
    jq \
    git \
    dos2unix \
    curl \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --set python3 /usr/bin/python3.11 \
    && ln -s /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

RUN update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

RUN mkdir -p ${EGO_TOP}/kernel/conf ${HF_TOP} ${HF_CONFDIR} ${HF_LOGDIR} ${HF_WORKDIR} ${PRO_SCRIPTDIR} \
 && cd / \
 && git clone https://github.com/Azure/cyclecloud-symphony.git

COPY ./cyclecloud_api-*-py2.py3-none-any.whl /tmp/

RUN cd /cyclecloud-symphony \
 && echo "Building package..." \
 && ./build_package_from_source.sh /tmp/cyclecloud_api-*-py2.py3-none-any.whl

# Make the host_provider plugin executable from /hostfactory/host_provider
RUN cd / \
 && apt update && apt install -y zip \
 && unzip /cyclecloud-symphony/blobs/symphony/cyclecloud-symphony-pkg* \
 && cp -a /hostfactory/host_provider/* ${PRO_SCRIPTDIR}/ \
 && chmod a+x ${PRO_SCRIPTDIR}/*.sh \
 && python3 -m venv ${PRO_VENV} \
 && . ${PRO_VENV}/bin/activate \
 && pip install --upgrade packages/* \
 && echo "{}" > /tmp/input.json
 

# Copy resulting host_provider blob back to container host with docker build --output=.
#FROM scratch
#COPY --from=build /cyclecloud-symphony/blobs/symphony/cyclecloud-symphony-pkg* .
    

