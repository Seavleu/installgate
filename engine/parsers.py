"""Parse install commands into TargetRef objects. No network, no execution."""

from __future__ import annotations

import re
import shlex

from contracts.contracts import Ecosystem, TargetRef

# A name that survives TargetRef's pattern; anything else is rejected before any fetch.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9@/_.\-:]+$")

# pip accepts ==, >=, <=, ~=, !=, <, >; only == pins an exact version.
_PEP508 = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._\-]*)"
    r"(?:\[[A-Za-z0-9,._\-]+\])?"
    r"(?:(?P<op>==|>=|<=|~=|!=|<|>)(?P<version>[A-Za-z0-9._*+!\-]+))?$"
)

# npm: optional @scope/, then name, then optional @version
_NPM_SPEC = re.compile(
    r"^(?P<name>(?:@[a-z0-9][a-z0-9._\-]*/)?[a-z0-9][a-z0-9._\-]*)"
    r"(?:@(?P<version>[A-Za-z0-9._*^~>=<\-+|\s]+))?$"
)

_HF_REPO = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._\-]*/[A-Za-z0-9][A-Za-z0-9._\-]*)$")

_DOCKER_FROM = re.compile(
    r"^\s*FROM\s+(?P<image>\S+)(?:\s+AS\s+\S+)?\s*$",
    re.IGNORECASE,
)

_PIP_FLAGS_WITH_VALUE = {
    "-r",
    "--requirement",
    "-i",
    "--index-url",
    "--extra-index-url",
    "-f",
    "--find-links",
    "-c",
    "--constraint",
    "-t",
    "--target",
    "--prefix",
    "--root",
    "--python-version",
    "--platform",
    "--implementation",
    "--abi",
    "--hash",
}

_NPM_FLAGS_WITH_VALUE = {"--registry", "--prefix", "--workspace", "-w", "--tag"}


class ParseError(ValueError):
    """The input is not an install command we can read."""


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError as exc:
        raise ParseError(f"could not tokenise command: {exc}") from exc


def _strip_flags(tokens: list[str], flags_with_value: set[str]) -> list[str]:
    out: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok.startswith("-"):
            base = tok.split("=", 1)[0]
            if base in flags_with_value and "=" not in tok:
                skip_next = True
            continue
        out.append(tok)
    return out


def parse_pip(command: str) -> list[TargetRef]:
    """`pip install requests==2.31.0` -> [TargetRef(pypi, requests, 2.31.0)]."""
    tokens = _tokens(command)
    if not tokens:
        raise ParseError("empty command")
    # Accept `pip`, `pip3`, `python -m pip`, `uv pip`.
    try:
        idx = tokens.index("install")
    except ValueError as exc:
        raise ParseError("not a pip install command") from exc
    specs = _strip_flags(tokens[idx + 1 :], _PIP_FLAGS_WITH_VALUE)
    if not specs:
        raise ParseError("pip install with no package named")

    targets: list[TargetRef] = []
    for spec in specs:
        # A local path, URL, or VCS ref is not a registry target we can check.
        if "://" in spec or spec.startswith((".", "/")) or spec.endswith((".whl", ".tar.gz")):
            raise ParseError(f"non-registry install target: {spec!r}")
        m = _PEP508.match(spec)
        if not m:
            raise ParseError(f"unreadable pip requirement: {spec!r}")
        version = m.group("version") if m.group("op") == "==" else None
        targets.append(TargetRef(ecosystem=Ecosystem.PYPI, name=m.group("name"), version=version))
    return targets


def parse_npm(command: str) -> list[TargetRef]:
    """`npm install left-pad@1.3.0` -> [TargetRef(npm, left-pad, 1.3.0)]."""
    tokens = _tokens(command)
    if not tokens:
        raise ParseError("empty command")
    verb_idx = next(
        (i for i, t in enumerate(tokens) if t in {"install", "i", "add"}),
        None,
    )
    if verb_idx is None:
        raise ParseError("not an npm install command")
    specs = _strip_flags(tokens[verb_idx + 1 :], _NPM_FLAGS_WITH_VALUE)
    if not specs:
        raise ParseError("npm install with no package named")

    targets: list[TargetRef] = []
    for spec in specs:
        if "://" in spec or spec.startswith((".", "/")):
            raise ParseError(f"non-registry install target: {spec!r}")
        m = _NPM_SPEC.match(spec)
        if not m:
            raise ParseError(f"unreadable npm spec: {spec!r}")
        raw_version = m.group("version")
        # Only an exact semver string counts as pinned; a range does not.
        version = (
            raw_version
            if raw_version and re.fullmatch(r"\d+\.\d+\.\d+(?:[.\-+][A-Za-z0-9.\-]+)?", raw_version)
            else None
        )
        targets.append(TargetRef(ecosystem=Ecosystem.NPM, name=m.group("name"), version=version))
    return targets


def parse_hf_repo_id(repo_id: str) -> TargetRef:
    """`org/model` -> TargetRef(huggingface, org/model). Accepts a `@revision` suffix."""
    text = repo_id.strip()
    revision: str | None = None
    if "@" in text:
        text, revision = text.rsplit("@", 1)
        revision = revision or None
    m = _HF_REPO.match(text)
    if not m:
        raise ParseError(f"not a Hugging Face repo id: {repo_id!r}")
    return TargetRef(ecosystem=Ecosystem.HUGGINGFACE, name=m.group("name"), version=revision)


def parse_dockerfile(content: str) -> list[TargetRef]:
    """Every `FROM` line in a Dockerfile -> TargetRef(docker, image, tag).

    Build stage aliases (`FROM x AS build` then `FROM build`) are not registry targets
    and are skipped.
    """
    stage_aliases: set[str] = set()
    targets: list[TargetRef] = []
    for line in content.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _DOCKER_FROM.match(line)
        if not m:
            continue
        image = m.group("image")
        as_match = re.search(r"\sAS\s+(\S+)\s*$", line, re.IGNORECASE)
        if as_match:
            stage_aliases.add(as_match.group(1).lower())
        if image.lower() in stage_aliases:
            continue
        if image.startswith("$"):
            continue

        digest: str | None = None
        if "@sha256:" in image:
            image, digest = image.split("@sha256:", 1)

        name, tag = image, None
        # A colon after the last slash is a tag; a colon before it is a registry port.
        last_slash = image.rfind("/")
        colon = image.rfind(":")
        if colon > last_slash:
            name, tag = image[:colon], image[colon + 1 :]

        if not _SAFE_NAME.match(name):
            raise ParseError(f"unreadable image name: {image!r}")
        targets.append(
            TargetRef(
                ecosystem=Ecosystem.DOCKER,
                name=name,
                version=tag,
                artifact_sha256=digest
                if digest and re.fullmatch(r"[0-9a-f]{64}", digest)
                else None,
            )
        )
    return targets


def parse_command(command: str) -> list[TargetRef]:
    """Dispatch on the leading verb of an install command."""
    tokens = _tokens(command)
    if not tokens:
        raise ParseError("empty command")
    head = {t for t in tokens[:3]}
    if "pip" in head or "pip3" in head:
        return parse_pip(command)
    if head & {"npm", "pnpm", "yarn"}:
        return parse_npm(command)
    raise ParseError(f"unsupported command: {command!r}")
