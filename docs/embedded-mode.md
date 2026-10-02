# Embedded mode

`AIVUDAOS_EMBEDDED_MODE=1` disables Avahi hostname write/restart and Caddy
HTTPS hostname synchronization/reload at bootstrap and OS-config updates.
Bootstrap keeps the editable `avahi_hostname` field in `os.yaml` and uses
`aceswarm` when the field is first created; it does not invoke Avahi to create
or publish that name.
An embedded manager supplies `AIVUDAOS_WS_ROOT` and owns the loopback Caddy
listener. AivudaOS continues to update and reload installed application
routes using its workspace Caddy binary and Caddyfile. This flag does not
change standalone service installation scripts or disable app routing.
