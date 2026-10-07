"""Opt-in packaged RAW checks, used only by --smoke-report on Windows."""
from io import BytesIO
import json
from urllib.request import Request, urlopen

from PIL import Image


def check_raw(server, roots):
    if not roots:
        return None
    base = f'http://127.0.0.1:{server.server_port}'

    def request(route, body=None):
        headers = {'X-Fuji-Session': server.session_token}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        req = Request(base + route, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        with urlopen(req, timeout=120) as response:
            return response.read()

    files = json.loads(request('/api/folder', {'path': str(roots[0])}))['files']
    if not files:
        return None
    identifier = files[0]['id']

    def image_size(data):
        with Image.open(BytesIO(data)) as image:
            image.load()
            if image.mode != 'RGB' or image.format != 'JPEG':
                raise RuntimeError('Packaged renderer did not produce an RGB JPEG')
            if not image.info.get('icc_profile'):
                raise RuntimeError('Packaged JPEG has no color profile')
            return list(image.size)

    info = json.loads(request('/api/photo/' + identifier))
    source = [info['developed_size']['width'], info['developed_size']['height']]
    results = {}
    for film in ('provia', 'classic_negative', 'pro_neg_hi'):
        recipe = {'film': film}
        body = {'id': identifier, 'recipe': recipe, 'quality': 'display', 'edge': 1024}
        preview = image_size(request('/api/render', body))
        if max(preview) > 1024 or min(preview) < 128:
            raise RuntimeError(f'Unexpected preview dimensions: {preview}')
        results[film] = preview
    tile = image_size(request('/api/tile', {
        'id': identifier, 'recipe': recipe, 'x': 0, 'y': 0, 'size': 256,
    }))
    if tile != [256, 256]:
        raise RuntimeError(f'Unexpected source-detail tile: {tile}')
    exported = image_size(request('/api/export', {'id': identifier, 'recipe': recipe}))
    if exported != source:
        raise RuntimeError(f'Export {exported} does not match the RAW dimensions {source}')
    return {'previews': results, 'tile': tile, 'export': exported, 'icc': True}
