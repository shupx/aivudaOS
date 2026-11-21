"""Build uploadable app packages for installer and gateway tests."""
import io
import zipfile

import yaml


def app_package(app_id, version, defaults, schema, *, start='#!/bin/sh\nexit 0\n', manifest=None, files=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('manifest.yaml', yaml.safe_dump({
            'app_id': app_id, 'version': version, 'run': {'entrypoint': 'start.sh'},
            'default_config_path': 'defaults.yaml', 'config_schema_path': 'schema.yaml', **(manifest or {}),
        }))
        archive.writestr('defaults.yaml', yaml.safe_dump(defaults))
        archive.writestr('schema.yaml', yaml.safe_dump(schema))
        archive.writestr('start.sh', start)
        for name, content in (files or {}).items():
            archive.writestr(name, content)
    return output.getvalue()
