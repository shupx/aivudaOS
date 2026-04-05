# AivudaOS

aivudaOS is a lightweight OS on swarm robot's onboard computer. It offers a graphical panel which allows you to interact with the onboard system and manage the APPs.

## Install 

- Install from PyPI:

```bash
pip install aivudaos
```

- Install from a wheel:

```bash
pip install aivudaos-1.0.0.dev2026040501-py3-none-any.whl
```

- Install from source:

```bash
git clone https://gitee.com/buaa_iooda/aivudaOS.git
cd aivudaOS/
pip install .
```

After install the wheel, you must init aivudaos first:

```bash
aivudaos install
```

This will install all the dependencies and start aivudaOS and make aivudaOS autostart.

## Usage

Visit  [http://127.0.0.1:80](http://127.0.0.1:80) on the local browser, or vist  [https://<avahi_hostname>.local:443]() on a remote browser, where the `<avahi_hostname>` can be get by
```bash
aivudaos get-avahi-hostname
```

Each robot has a randomly generated and unique avahi_hostname on install, which can be also changed on the system setting of the aivudaOS panel.

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

## Develop

Refer to [README_dev.md](README_dev.md) 
