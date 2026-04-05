# AivudaOS

aivudaOS is a lightweight OS on swarm robot's onboard computer. It offers a graphical panel which allows you to interact with the onboard system and manage the APPs.

## Install 

- Install from gitee/github repository release:

```bash
pip install git+https://gitee.com/buaa_iooda/aivudaOS.git@nightly
```

- Install from PyPI (may not be the newest):

```bash
pip install aivudaos
```

- Install from a provided wheel:

```bash
pip install aivudaos-1.0.0.dev2026040501-py3-none-any.whl
```

- Install from source:

```bash
git clone https://gitee.com/buaa_iooda/aivudaOS.git
cd aivudaOS/
pip install . # need dated npm and node installed
```

**After install the wheel, you need to install aivudaOS dependencies first:**

```bash
aivudaos install
```

This will install all the dependencies and start aivudaOS and make aivudaOS autostart.

The following port is used by aivudaOS:

- `127.0.0.1:8000`: internal backend, reverse proxy by caddy;
- `http://127.0.0.1:80`: expose the service by caddy for http;
- `https://<avahi_hostname>.local:443 ` expose the service by caddy for https.

## Usage

Visit  [http://127.0.0.1:80](http://127.0.0.1:80) on the local browser, or vist  [https://<avahi_hostname>.local:443]() on a remote browser, where the `<avahi_hostname>` can be get by
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

```bash
cd aivudaOS/
cd ui/ && npm install && npm run build && cd ..
AIVUDAOS_BUILD_SEQ=01 python -m build
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

## Develop

Refer to [README_dev.md](README_dev.md) 
