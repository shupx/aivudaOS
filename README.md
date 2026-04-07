# AivudaOS

aivudaOS is a lightweight OS on swarm robot's onboard computer. It offers a graphical panel which allows you to interact with the onboard system and manage the APPs.

## Install 

- Install from PyPI:

```bash
pip install aivudaos
# pip install -i https://pypi.tuna.tsinghua.edu.cn/simple aivudaos  # use pypi mirror (may not be the latest)
# pip install aivudaos==1.0.0.dev2026040602  # for a certain version
```

- Install from a provided wheel:

```bash
pip install aivudaos-1.0.0.dev2026040501-py3-none-any.whl
```

- Install from source:

```bash
git clone https://gitee.com/buaa_iooda/aivudaOS.git
cd aivudaOS/
pip install -e . # need dated npm and node (>20) installed
# pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e .  # use pypi mirror for build
```

To upgrade:

```bash
# pip index versions aivudaos --pre  # inspect available versions on PyPI
pip install aivudaos --upgrade
```

To uninstall:

```bash
# stop and remove the systemd service by 'aivudaos uninstall' first:
aivudaos uninstall
pip uninstall aivudaos
```

## Usage

Add python local path first:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**After install the wheel, you need to install aivudaOS dependencies first:**

```bash
aivudaos install
```

This will install all the dependencies and start aivudaOS and make aivudaOS autostart.

Then get url and open it in your browser:

```bash
aivudaos web
```

It will remind you to visit  [http://127.0.0.1:80](http://127.0.0.1:80) on the local browser, or vist  [https://<avahi_hostname>.local:443]() on a remote browser

The following port is used by aivudaOS:

- `127.0.0.1:8000`: internal backend, reverse proxy by caddy;
- `http://127.0.0.1:80`: expose the service by caddy for http;
- `https://<avahi_hostname>.local:443 ` expose the service by caddy for https,

where the `<avahi_hostname>` can be read by

```bash
aivudaos get-avahi-hostname
aivudaos get-avahi-hostname --debug
```

> Each robot has a randomly generated and unique avahi_hostname on install, which can also be changed in the system setting of the aivudaOS panel.

After installation, you can use the unified CLI:

```bash
aivudaos --help
aivudaos --version
aivudaos install
aivudaos web
aivudaos start
aivudaos stop
aivudaos restart
aivudaos enable-autostart
aivudaos disable-autostart
aivudaos download-caddy
aivudaos uninstall
```

## Build wheel

Build release artifacts locally:

> Wheel artifacts include only `aivudaos/resources/ui/dist` for the frontend. The source distribution excludes `dist` and `node_modules`, while keeping the UI source files for development and rebuilding.

```bash
cd aivudaOS/
cd aivudaos/resources/ui/ && npm install && npm run build && cd ../../..
AIVUDAOS_BUILD_SEQ=01 
python -m build
# PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple python -m build  # use pypi mirror
```

If your environment does not provide `python -m build` isolation support, use:

```bash
AIVUDAOS_BUILD_SEQ=01 python -m build --no-isolation
```

Upload to [PyPi](https://pypi.org/):

```bash
cd aivudaOS
AIVUDAOS_BUILD_SEQ=01 \
TWINE_USERNAME=__token__ \
TWINE_PASSWORD="$PYPI_TOKEN" \
TWINE_NON_INTERACTIVE=1 \
./publish_aivudaos_pypi.sh

## or not upload
cd aivudaOS
AIVUDAOS_BUILD_SEQ=01 \
./publish_aivudaos_pypi.sh --skip-upload
```

The automated workflow is activated at https://github.com/shupx/aivudaOS/actions/workflows/nightly-build.yml, which deploys a check every night and build and publish wheels to PyPi if there is a update.

## Develop

Refer to [README_dev.md](README_dev.md) 
