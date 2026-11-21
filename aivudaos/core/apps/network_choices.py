"""Presentation choices for an app's interface, source IPv4 and destination fields."""
from aivudaos.core.apps.config_validation import normalize_config_schema
from aivudaos.core.apps.device_network import NetworkSnapshot
from aivudaos.core.apps.network_schema import device_ipv4_fields


def app_config_schema(schema, data, network=None):
    normalized = normalize_config_schema(schema)
    network = network or NetworkSnapshot()
    for key in normalized.get('properties', {}):
        fields = device_ipv4_fields(schema['properties'][key])
        if not fields:
            continue
        nic, addr, dest = fields
        props = normalized['properties'][key]['properties']
        nic_field, ip_field, dst_field = props[nic], props[addr], props[dest]
        nic_field['resetAutoSibling'] = addr
        dst_field['resetAutoSibling'] = addr

        config = data.get(key) if isinstance(data, dict) else None
        if not isinstance(config, dict):
            continue
        selected = config.get(nic, 'auto')
        saved_address = config.get(addr, 'auto')
        if not isinstance(selected, str) or not isinstance(saved_address, str):
            continue
        cards = network.cards
        route = network.route(config.get(dest))
        name = route[0] if selected == 'auto' else selected
        card = cards.get(name, {})
        addresses = card.get('addresses', [])
        source = None
        if card.get('up'):
            if name == route[0] and route[1] in addresses:
                source = route[1]
            elif len(addresses) == 1:
                source = addresses[0]
        names = sorted(cards, key=lambda n: (not cards[n]['up'], n))
        nic_field['enum'] = list(dict.fromkeys(['auto', *names, selected]))
        labels = {'auto': ' · '.join(filter(None, ['auto', *route]))}
        for n, card in cards.items():
            labels[n] = ' · '.join([n, *card['addresses'], '↑' if card['up'] else '↓'])
        nic_field['enumLabels'] = [labels.get(n, n + ' · ↓') for n in nic_field['enum']]
        ip_field['enum'] = list(dict.fromkeys(['auto', *addresses, saved_address]))
        ip_field['enumLabels'] = [('auto · ' + (source or '—')) if ip == 'auto' else ip for ip in ip_field['enum']]
    return normalized
