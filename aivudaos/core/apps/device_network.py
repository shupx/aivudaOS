"""Read the target's IPv4 interfaces and ask the kernel for its direct route."""
import ipaddress
import json
import subprocess


class NetworkSnapshot:
    """Lazy discovery shared during one config request, never across requests."""

    def __init__(self):
        self._cards = None
        self._routes = {}

    @property
    def cards(self):
        if self._cards is None:
            try:
                self._cards = interfaces()
            except (OSError, ValueError, subprocess.SubprocessError):
                self._cards = {}
        return self._cards

    def route(self, destination):
        if not isinstance(destination, str) or not self.cards:
            return None, None
        if destination not in self._routes:
            try:
                self._routes[destination] = direct_route(destination, self.cards)
            except (OSError, ValueError, subprocess.SubprocessError):
                self._routes[destination] = (None, None)
        return self._routes[destination]


def ip_json(*args):
    return json.loads(subprocess.check_output(
        ['ip', '-j', *args], text=True, timeout=3, stderr=subprocess.DEVNULL))


def interfaces():
    cards = {}
    for row in ip_json('addr', 'show'):
        flags = row.get('flags', [])
        if 'LOOPBACK' in flags:
            continue
        addresses = [a['local'] for a in row.get('addr_info', [])
                     if a.get('family') == 'inet' and a.get('scope') != 'host']
        if not addresses and row.get('link_type') != 'ether':
            continue
        cards[row['ifname']] = {'addresses': addresses, 'up': 'UP' in flags and 'LOWER_UP' in flags}
    return cards


def direct_route(target, cards):
    ip = str(ipaddress.IPv4Address(target))
    try:
        routes = ip_json('-4', 'route', 'get', ip)
    except subprocess.CalledProcessError:
        return None, None
    if routes:
        route = routes[0]
        name, source = route.get('dev'), route.get('prefsrc')
        card = cards.get(name, {})
        if (not route.get('gateway') and route.get('type', 'unicast') == 'unicast'
                and card.get('up') and source in card.get('addresses', [])):
            return name, source
    return None, None
