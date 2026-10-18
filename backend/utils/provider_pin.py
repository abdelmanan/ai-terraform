import logging
import re

from backend.config import settings

logger = logging.getLogger(__name__)

REQUIRED_PROVIDERS_PATTERN = re.compile(r"\brequired_providers\s*\{")

VERSION_PATTERN = re.compile(r'(\bversion\s*=\s*)"[^"]*"')


def _pinned_versions():
    return {
        "aws": settings.AWS_PROVIDER_VERSION,
        "random": settings.RANDOM_PROVIDER_VERSION,
    }


def _block_end(text, open_brace_index):
    """Index of the brace closing the one at `open_brace_index`, or None."""

    depth = 0

    for index in range(open_brace_index, len(text)):

        if text[index] == "{":
            depth += 1

        elif text[index] == "}":
            depth -= 1

            if depth == 0:
                return index

    return None


def _pin_entry(body, name, version):
    """Force `version` inside the `name = { ... }` entry of a required_providers body."""

    entry = re.search(rf"\b{name}\s*=\s*\{{([^{{}}]*)\}}", body)

    if not entry:
        return body

    inner = entry.group(1)

    if VERSION_PATTERN.search(inner):
        new_inner = VERSION_PATTERN.sub(rf'\g<1>"{version}"', inner, count=1)
    else:
        new_inner = inner.rstrip() + f'\n      version = "{version}"\n    '

    return body[:entry.start(1)] + new_inner + body[entry.end(1):]


def _entry(name, version):
    return (
        f"    {name} = {{\n"
        f'      source  = "hashicorp/{name}"\n'
        f'      version = "{version}"\n'
        "    }\n"
    )


def _pin_file(content, uses_random):

    match = REQUIRED_PROVIDERS_PATTERN.search(content)

    if not match:
        return content, False

    open_brace = match.end() - 1
    close_brace = _block_end(content, open_brace)

    if close_brace is None:
        return content, True

    body = content[open_brace:close_brace]

    for name, version in _pinned_versions().items():
        body = _pin_entry(body, name, version)

    if uses_random and not re.search(r"\brandom\s*=\s*\{", body):
        body = body.rstrip() + "\n" + _entry("random", settings.RANDOM_PROVIDER_VERSION) + "  "

    return content[:open_brace] + body + content[close_brace:], True


def pin_provider_versions(files):
    """Rewrite provider constraints to the versions held in the plugin cache."""

    pinned = dict(files)
    declared = False

    uses_random = any(
        re.search(r'resource\s+"random_', content)
        for name, content in files.items() if name.endswith(".tf")
    )

    for filename, content in files.items():

        if not filename.endswith(".tf"):
            continue

        needs_random = uses_random and not any(
            re.search(r"\brandom\s*=\s*\{", other) for other in pinned.values()
        )

        new_content, has_block = _pin_file(content, needs_random)
        declared = declared or has_block

        if new_content != content:
            logger.info("Pinned provider versions in %s", filename)
            pinned[filename] = new_content

    if not declared and "provider.tf" in pinned:

        block = "terraform {\n  required_providers {\n"
        block += _entry("aws", settings.AWS_PROVIDER_VERSION)

        if uses_random:
            block += _entry("random", settings.RANDOM_PROVIDER_VERSION)

        block += "  }\n}\n\n"

        logger.info("Added a missing required_providers block to provider.tf")
        pinned["provider.tf"] = block + pinned["provider.tf"]

    return pinned
