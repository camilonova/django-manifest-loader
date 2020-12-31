import json
import os

from django.templatetags.static import StaticNode
from django.conf import settings
from django.core.cache import cache
from django.utils.html import conditional_escape
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from manifest_loader.exceptions import WebpackManifestNotFound, \
    CustomManifestLoaderNotValid
from manifest_loader.loaders import DefaultLoader, LoaderABC


APP_SETTINGS = {
    'output_dir': None,
    'manifest_file': 'manifest.json',
    'cache': False,
    'loader': DefaultLoader
}

if hasattr(settings, 'MANIFEST_LOADER'):
    APP_SETTINGS.update(settings.MANIFEST_LOADER)


def manifest(key, context=None):
    manifest_obj = get_manifest()
    manifest_value = load_from_manifest(manifest_obj, key=key)
    return make_url(manifest_value, context)


def manifest_match(pattern, output, context=None):
    manifest_obj = get_manifest()
    files = load_from_manifest(manifest_obj, pattern=pattern)
    urls = []
    for file in files:
        url = make_url(file, context)
        urls.append(url)
    output_tags = [output.format(match=file) for file in urls]
    return '\n'.join(output_tags)


def get_manifest():
    """
    Returns the manifest file converted into a dict. If caching is enabled
    this will return the cached manifest.
    """
    cached_manifest = cache.get('webpack_manifest')
    if APP_SETTINGS['cache'] and cached_manifest:
        return cached_manifest

    if APP_SETTINGS['output_dir']:
        manifest_path = os.path.join(APP_SETTINGS['output_dir'],
                                     APP_SETTINGS['manifest_file'])
    else:
        manifest_path = find_manifest_path()

    try:
        with open(manifest_path) as manifest_file:
            data = json.load(manifest_file)
    except FileNotFoundError:
        raise WebpackManifestNotFound(manifest_path)

    if APP_SETTINGS['cache']:
        cache.set('webpack_manifest', data)

    return data


def find_manifest_path():
    """
    combs through settings.STATICFILES_DIRS to find the path of the manifest
    file.
    """
    static_dirs = settings.STATICFILES_DIRS
    if len(static_dirs) == 1:
        return os.path.join(static_dirs[0], APP_SETTINGS['manifest_file'])
    for static_dir in static_dirs:
        manifest_path = os.path.join(static_dir, APP_SETTINGS['manifest_file'])
        if os.path.isfile(manifest_path):
            return manifest_path
    raise WebpackManifestNotFound('settings.STATICFILES_DIRS')


def is_quoted_string(string):
    """
    checks if the string parameter is surrounded in quotes, which is how
    strings arrive from the template tags.
    """
    if len(string) < 2:
        return False
    return string[0] == string[-1] and string[0] in ('"', "'")


def get_value(string, context):
    """
    determines the true value of an input to a template tag. If the string is
    quoted it's interpreted as a string. If not quoted then it's treated as a
    variable and looked up against the context.
    """
    if is_quoted_string(string):
        return string[1:-1]
    return context.get(string, '')


def load_from_manifest(manifest, key=None, pattern=None):
    """
    uses the loader defined in settings to get the values
    from the manifest file
    """
    loader = APP_SETTINGS['loader']

    if not issubclass(loader, LoaderABC):
        raise CustomManifestLoaderNotValid

    if key:
        return loader.get_single_match(manifest, key)
    elif pattern:
        return loader.get_multi_match(manifest, pattern)
    return ''


def is_url(potential_url):
    """checks if a string is a valid url"""
    validate = URLValidator()
    try:
        validate(potential_url)
        return True
    except ValidationError:
        return False


def make_url(manifest_value, context=None):
    """
    uses the django staticfiles app to get the url of the file being asked for
    """
    if is_url(manifest_value):
        url = manifest_value
    else:
        url = StaticNode.handle_simple(manifest_value)
    if context is not None and context.autoescape:
        url = conditional_escape(url)
    return url
