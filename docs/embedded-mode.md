# Embedded mode

`AIVUDAOS_EMBEDDED_MODE=1` disables Avahi hostname generation/write/restart
and Caddy HTTPS hostname synchronization at bootstrap and OS-config updates.
An embedded manager supplies `AIVUDAOS_WS_ROOT` and owns the loopback Caddy
listener. AivudaOS continues to update and reload installed application
routes using its workspace Caddy binary and Caddyfile. This flag does not
change standalone service installation scripts or disable app routing.
