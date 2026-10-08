# Embedded mode

## UI Appearance

Language (`aivuda_ui_locale`) and theme (`aivuda_theme`) default to `system`; existing explicit choices are retained. Language offers `system`, `en-US`, and `zh-CN`; theme offers `system`, `light`, and `dark` in the user menu.

Follow System reads `navigator.language` for language and `matchMedia('(prefers-color-scheme: dark)')` for theme. Standard `languagechange` and media-query change events refresh followers without reloading. Unsupported languages or unavailable APIs fall back to English and Light. The appearance resolver lives in `resources/ui/src/appearance.js` and has no dependency on any desktop host. An embedding application can provide its preferences through the browser environment.

## Runtime

`AIVUDAOS_EMBEDDED_MODE=1` disables Avahi hostname write/restart and Caddy
HTTPS hostname synchronization/reload at bootstrap and OS-config updates.
Bootstrap keeps the editable `avahi_hostname` field in `os.yaml` and uses
`aceswarm` when the field is first created; it does not invoke Avahi to create
or publish that name.
An embedded manager supplies `AIVUDAOS_WS_ROOT` and owns the loopback Caddy
listener. AivudaOS continues to update and reload installed application
routes using its workspace Caddy binary and Caddyfile. This flag does not
change standalone service installation scripts or disable app routing.

### Desktop exit

ACEswarm first terminates the embedded AivudaOS gateway and allows its shutdown
hook to finish Popen app cleanup, then tears down the other local services.
The existing Electron guardian cleans desktop service groups after a crash;
AivudaOS's independent pipe guardian cleans the apps' separate sessions when
the gateway exits or is killed. This policy does not stop systemd applications.
