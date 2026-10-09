#!/bin/bash
# 打包 Linux 客户端为 .deb（Ubuntu / 银河麒麟 / 统信UOS 通用）
# 注意：PyInstaller 不支持交叉编译，需分别在 x86_64（海光/兆芯）与 aarch64（飞腾/鲲鹏）终端上执行本脚本
set -e
cd "$(dirname "$0")"
ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
VERSION=$(python3 -c "import re;print(re.search(r'VERSION = \"(.+?)\"', open('xiaoxin_client/config.py',encoding='utf-8').read()).group(1))")

# 依赖：python3-tk（Tkinter）、中文字体
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get install -y python3-tk python3-pip fonts-noto-cjk >/dev/null || true
fi
python3 -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

python3 -m PyInstaller --noconfirm --windowed --name xiaoxin \
  --hidden-import xiaoxin_client --collect-submodules xiaoxin_client xiaoxin_client/main.py

PKG=build/deb/xiaoxin_${VERSION}_${ARCH}
rm -rf $PKG && mkdir -p $PKG/DEBIAN $PKG/opt/xiaoxin $PKG/usr/share/applications $PKG/etc/xdg/autostart $PKG/usr/bin
cp -r dist/xiaoxin/* $PKG/opt/xiaoxin/
cp config.json $PKG/opt/xiaoxin/config.json
ln -sf /opt/xiaoxin/xiaoxin $PKG/usr/bin/xiaoxin
cat > $PKG/usr/share/applications/xiaoxin.desktop <<EOF
[Desktop Entry]
Name=小信助手
Comment=信创终端智能助手
Exec=/opt/xiaoxin/xiaoxin
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=Utility;System;
EOF
cp $PKG/usr/share/applications/xiaoxin.desktop $PKG/etc/xdg/autostart/xiaoxin.desktop
cat > $PKG/DEBIAN/control <<EOF
Package: xiaoxin
Version: ${VERSION}
Architecture: ${ARCH}
Maintainer: xiaoxin
Depends: policykit-1 | pkexec
Description: 小信助手桌面客户端（一键提速、探针监测、悬浮助手、智能问答、合同智审）
EOF
dpkg-deb --build --root-owner-group $PKG
echo "打包完成：$PKG.deb"
echo "安装：sudo dpkg -i $PKG.deb   （安装后修改 /opt/xiaoxin/config.json 中的 server 地址）"
