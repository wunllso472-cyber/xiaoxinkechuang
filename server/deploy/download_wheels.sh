#!/bin/bash
# 在有网络的机器上下载 ARM64 (aarch64) 离线依赖包，拷贝到内网服务器后使用 OFFLINE=1 安装
# 用法：bash deploy/download_wheels.sh [python版本，默认 39]
PYV=${1:-39}
cd "$(dirname "$0")"
mkdir -p wheels
pip download -r ../requirements.txt -d wheels \
  --platform manylinux2014_aarch64 --platform manylinux_2_17_aarch64 --platform manylinux_2_28_aarch64 \
  --python-version $PYV --implementation cp --only-binary=:all: \
  -i ${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple/}
echo "已下载到 deploy/wheels，共 $(ls wheels | wc -l) 个文件"
