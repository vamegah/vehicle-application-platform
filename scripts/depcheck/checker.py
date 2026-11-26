"""Dependency pin checker (task 1.4). Python 3.12 standard library only.

Reads every manifest in the repository and DEPENDENCIES.lock.md and reports violations of the pinning
rules recorded in the ledger preamble. See `check()` for the entry point and RULES for the rule codes.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

LEDGER_NAME = "DEPENDENCIES.lock.md"
SIDECAR_DIR = "services/release-assurance/inference-sidecar"
FIXTURE_DIR = "scripts/tests/fixtures"
VERIFICATION_DIR = "scripts/verification"
EXCLUDED_DIRS = {".git", ".kiro", ".github", "node_modules", "target", ".venv", "venv", "__pycache__", "dist", "build", ".next"}

# Imported BOM that manages a Maven group, so artifacts in that group carry no <version>.
GROUP_BOMS = {
    "software.amazon.awssdk": "software.amazon.awssdk:bom",
    "org.springframework.cloud": "org.springframework.cloud:spring-cloud-dependencies",
    "io.opentelemetry.instrumentation": "io.opentelemetry.instrumentation:opentelemetry-instrumentation-bom",
}
BOOT_ROW = "org.springframework.boot:spring-boot-starter-parent"
BOOT_BOM = "org.springframework.boot:spring-boot-dependencies"
CLOUD_BOM = "org.springframework.cloud:spring-cloud-dependencies"

FORBIDDEN_MAVEN = {
    "org.springframework.cloud:spring-cloud-starter-gateway": "old gateway starter; use spring-cloud-starter-gateway-server-webflux",
    "org.springframework.cloud:spring-cloud-starter-vault-config": "Spring Cloud Vault starters are not used (ADR-010)",
    "org.springframework.cloud:spring-cloud-starter-vault": "Spring Cloud Vault starters are not used (ADR-010)",
    "com.fasterxml.jackson.core:jackson-databind": "direct Jackson 2 databind dependency (ADR-006)",
}
APPROVAL_ROWS = ("software.amazon.awssdk:bom", "software.amazon.awssdk:s3", "boto3")
APPROVAL_NOTE = "approved by user, decision 3"
SIDECAR_ONLY = ("xgboost", "scikit-learn")

IMAGE_REPOS = ("dxflrs/garage", "chrislusf/seaweedfs", "apache/kafka")
DIGEST_REQUIRED_REPOS = ("dxflrs/garage", "chrislusf/seaweedfs")
IMAGE_RE = re.compile(
    r"(?<![\w./-])(dxflrs/garage|chrislusf/seaweedfs|apache/kafka|neo4j)(?::([\w][\w.\-]*))?(@sha256:[0-9a-f]{64})?(?![\w.\-])"
)
MINIO_SPECIFIC_RE = re.compile(
    r"(?i)minio/minio|quay\.io/minio|testcontainers[-_.\[]minio|MinIOContainer|org\.testcontainers\.minio|io\.minio:|\"io\.minio\"|<groupId>io\.minio"
)
MINIO_ANY_RE = re.compile(r"(?i)\bminio\b")
JACKSON2_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?com\.fasterxml\.jackson\.databind\b", re.MULTILINE)
EXACT_NPM_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.\-]+)?(?:\+[0-9A-Za-z.\-]+)?$")
EXACT_PY_RE = re.compile(r"^==\s*(\d[0-9A-Za-z.!+_\-]*)$")
PY_REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$")

TEXT_SCAN_SUFFIXES = {".yml", ".yaml", ".java", ".kt", ".py", ".sh", ".toml", ".properties", ".json", ".txt", ".xml", ".ps1", ".cmd"}

RULES = {
    "unpinned-version": "a version is a range, wildcard, latest, snapshot, or missing",
    "ledger-missing": "a manifest dependency has no ledger row",
    "version-mismatch": "a manifest version differs from the ledger row",
    "unverified-in-use": "a manifest uses a ledger row marked UNVERIFIED",
    "ledger-unverified": "a ledger row is marked UNVERIFIED",
    "ledger-unused": "a ledger row has no manifest entry and is not marked unused or planned",
    "forbidden-artifact": "an artifact the platform does not use (langgraph, MinIO, Jackson 2 databind, Spring Cloud Vault starter, old gateway starter)",
    "sidecar-only": "xgboost or scikit-learn outside the release-assurance inference sidecar",
    "bom-not-imported": "a BOM-managed artifact has no <version> and its BOM is not imported",
    "bom-ledger-missing": "a BOM-managed artifact's BOM has no ledger row",
    "no-managing-bom": "a dependency has no <version> and no Spring Boot parent or BOM manages it",
    "boot-version": "Spring Boot parent or BOM is not 4.1.x (3.x and 4.0.x are rejected)",
    "cloud-train": "Spring Cloud BOM is older than 2025.1",
    "unresolved-property": "a version refers to a property that is not defined in the same pom",
    "image-no-digest": "a Garage or SeaweedFS image reference has no @sha256 digest",
    "image-ledger-mismatch": "an image reference differs from its ledger row",
    "minio": "a MinIO image or dependency",
    "jackson2-import": "an import of com.fasterxml.jackson.databind",
    "approval-note-missing": "an AWS SDK or boto3 ledger row lacks the 'approved by user, Decision 3' note",
    "ledger-rule": "the ledger itself breaks a recorded rule",
    "ledger-file": "the ledger file is missing or unreadable",
    "manifest-parse": "a manifest could not be parsed",
}


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"FAIL [{self.rule}] {self.path}: {self.message}"


@dataclass
class Row:
    section: str
    names: list[str]
    version: str
    notes: str
    not_used: bool


@dataclass
class Ledger:
    rows: list[Row] = field(default_factory=list)
    by_name: dict[str, Row] = field(default_factory=dict)

    def find(self, name: str) -> Row | None:
        return self.by_name.get(name.lower()) or self.by_name.get(norm_py(name))


def norm_py(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.lower())


def _clean_cell(cell: str) -> str:
    return cell.strip().replace("`", "")


def _split_names(cell: str) -> list[str]:
    cell = _clean_cell(cell)
    names: list[str] = []
    for token in re.split(r"\s/\s|,\s", cell):
        token = re.sub(r"\s*\(.*\)\s*$", "", token).strip()
        if token:
            names.append(token)
    return names


def parse_ledger(text: str) -> Ledger:
    ledger = Ledger()
    section = ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.startswith("|"):
            continue
        body = line.strip()[1:]
        if body.endswith("|"):
            body = body[:-1]
        cells = body.split("|", 2)
        if len(cells) < 3:
            continue
        first = cells[0].strip()
        if first.lower() in {"artifact", "package", "tool", "image", "server", "item"} or set(first) <= set("-: "):
            continue
        names = _split_names(cells[0])
        row = Row(
            section=section,
            names=names,
            version=_clean_cell(cells[1]),
            notes=cells[2].strip(),
            not_used="not used" in section.lower(),
        )
        ledger.rows.append(row)
        if row.not_used:
            continue
        for n in names:
            ledger.by_name.setdefault(n.lower(), row)
            ledger.by_name.setdefault(norm_py(n), row)
    return ledger


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_excluded(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in EXCLUDED_DIRS for p in parts[:-1]):
        return True
    return rel.startswith(FIXTURE_DIR + "/")


def _walk(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = _rel(p, root)
        if _is_excluded(rel):
            continue
        yield p, rel


# ----------------------------------------------------------------------------- ledger checks


def check_ledger(ledger: Ledger, ledger_path: str) -> list[Violation]:
    out: list[Violation] = []
    for row in ledger.rows:
        label = ", ".join(row.names) or "?"
        if not row.not_used and ("UNVERIFIED" in row.version or "UNVERIFIED" in row.notes[:80]):
            out.append(Violation("ledger-unverified", ledger_path, f"row '{label}' is marked UNVERIFIED"))
        if not row.not_used:
            joined = " ".join(row.names) + " " + row.version
            if re.search(r"(?i)minio", joined):
                out.append(Violation("ledger-rule", ledger_path, f"row '{label}' mentions MinIO outside the not-used section"))
            if re.search(r"(?i)langgraph", joined):
                out.append(Violation("ledger-rule", ledger_path, f"row '{label}' records langgraph outside the not-used section"))
    for name in APPROVAL_ROWS:
        row = ledger.find(name)
        if row is None:
            out.append(Violation("ledger-rule", ledger_path, f"required row '{name}' is missing"))
        elif APPROVAL_NOTE not in row.notes.lower():
            out.append(Violation("approval-note-missing", ledger_path, f"row '{name}' lacks the note 'approved by user, Decision 3'"))
    for name in SIDECAR_ONLY:
        if ledger.find(name) is None:
            out.append(Violation("ledger-rule", ledger_path, f"required row '{name}' is missing (ADR-004 keeps it for the sidecar)"))
    vault = ledger.find("org.springframework.vault:spring-vault-core")
    if vault is None:
        out.append(Violation("ledger-rule", ledger_path, "required row 'org.springframework.vault:spring-vault-core' is missing"))
    else:
        if vault.version != "4.1.2":
            out.append(Violation("ledger-rule", ledger_path, f"spring-vault-core row is {vault.version}, expected 4.1.2"))
        if "override" not in vault.notes.lower():
            out.append(Violation("ledger-rule", ledger_path, "spring-vault-core row must name the override of the Spring Cloud BOM"))
    boot = ledger.find(BOOT_ROW)
    if boot is None:
        out.append(Violation("ledger-rule", ledger_path, f"required row '{BOOT_ROW}' is missing"))
    elif not re.fullmatch(r"4\.1\.\d+", boot.version):
        out.append(Violation("boot-version", ledger_path, f"Spring Boot row is {boot.version}, expected 4.1.x"))
    cloud = ledger.find(CLOUD_BOM)
    if cloud is None:
        out.append(Violation("ledger-rule", ledger_path, f"required row '{CLOUD_BOM}' is missing"))
    elif not _cloud_ok(cloud.version):
        out.append(Violation("cloud-train", ledger_path, f"Spring Cloud BOM row is {cloud.version}, expected 2025.1 or later"))
    for repo in DIGEST_REQUIRED_REPOS:
        row = _image_row(ledger, repo)
        if row is None:
            out.append(Violation("ledger-rule", ledger_path, f"required image row for '{repo}' is missing"))
        elif not re.search(r"@sha256:[0-9a-f]{64}$", row.version):
            out.append(Violation("image-no-digest", ledger_path, f"image row for '{repo}' has no @sha256 digest: {row.version}"))
        elif row.version.startswith(repo + ":latest"):
            out.append(Violation("image-no-digest", ledger_path, f"image row for '{repo}' uses latest"))
    return out


def _image_row(ledger: Ledger, repo: str) -> Row | None:
    for row in ledger.rows:
        if not row.not_used and row.version.startswith(repo + ":"):
            return row
    return None


def _cloud_ok(version: str) -> bool:
    m = re.match(r"^(\d{4})\.(\d+)\.(\d+)", version)
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (2025, 1)


# ----------------------------------------------------------------------------- Maven


def _strip_ns(root: ET.Element) -> None:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def _text(el: ET.Element | None, tag: str) -> str | None:
    if el is None:
        return None
    child = el.find(tag)
    if child is None or child.text is None:
        return None
    return child.text.strip()


UNPINNED_MAVEN_RE = re.compile(r"[\[\](),*]|^(LATEST|RELEASE)$|SNAPSHOT", re.IGNORECASE)


def check_pom(path: Path, rel: str, ledger: Ledger, used: set[str]) -> list[Violation]:
    out: list[Violation] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        return [Violation("manifest-parse", rel, str(e))]
    root = tree.getroot()
    _strip_ns(root)
    props: dict[str, str] = {}
    pe = root.find("properties")
    if pe is not None:
        for child in pe:
            if child.text:
                props[child.tag] = child.text.strip()
    pgroup = _text(root, "groupId") or _text(root.find("parent"), "groupId") or ""
    props.setdefault("project.version", _text(root, "version") or _text(root.find("parent"), "version") or "")
    props.setdefault("project.groupId", pgroup)

    def resolve(value: str | None) -> tuple[str | None, bool]:
        if value is None:
            return None, True
        ok = True

        def sub(m: re.Match) -> str:
            nonlocal ok
            key = m.group(1)
            if key in props:
                return props[key]
            ok = False
            return m.group(0)

        return re.sub(r"\$\{([^}]+)\}", sub, value), ok

    has_boot = False
    boot_parent = root.find("parent")
    imported: dict[str, str] = {}

    if boot_parent is not None and _text(boot_parent, "artifactId") == "spring-boot-starter-parent":
        has_boot = True
        used.add(BOOT_ROW)
        out += _check_boot_version(rel, "parent", resolve(_text(boot_parent, "version"))[0], ledger)

    dm = root.find("dependencyManagement/dependencies")
    if dm is not None:
        for dep in dm.findall("dependency"):
            g, a = _text(dep, "groupId") or "", _text(dep, "artifactId") or ""
            if (_text(dep, "scope") == "import") and (_text(dep, "type") == "pom"):
                ver, ok = resolve(_text(dep, "version"))
                ga = f"{g}:{a}"
                imported[ga] = ver or ""
                if ga == BOOT_BOM:
                    has_boot = True
                    out += _check_boot_version(rel, "BOM import", ver, ledger)
                    used.add(BOOT_ROW)
                if ga == CLOUD_BOM and ver and not _cloud_ok(ver):
                    out.append(Violation("cloud-train", rel, f"Spring Cloud BOM {ver} is older than 2025.1"))
                out.extend(_check_versioned(rel, ga, ver, ok, ledger, used))

    def check_dep(dep: ET.Element, *, plugin: bool = False) -> None:
        g = _text(dep, "groupId") or ("org.apache.maven.plugins" if plugin else "")
        a = _text(dep, "artifactId") or ""
        ga = f"{g}:{a}"
        if g.startswith("com.autoreliance"):
            return
        if ga in FORBIDDEN_MAVEN:
            out.append(Violation("forbidden-artifact", rel, f"{ga}: {FORBIDDEN_MAVEN[ga]}"))
            return
        if re.search(r"(?i)minio", ga):
            out.append(Violation("minio", rel, f"{ga} is a MinIO dependency"))
            return
        ver, ok = resolve(_text(dep, "version"))
        if ver is None:
            if plugin:
                return
            out.extend(_check_managed(rel, ga, g, has_boot, imported, ledger, used))
        else:
            out.extend(_check_versioned(rel, ga, ver, ok, ledger, used))

    deps = root.find("dependencies")
    if deps is not None:
        for dep in deps.findall("dependency"):
            check_dep(dep)
    for plug in root.findall("build/plugins/plugin") + root.findall("build/pluginManagement/plugins/plugin"):
        check_dep(plug, plugin=True)
        for pdep in plug.findall("dependencies/dependency"):
            check_dep(pdep)
    # dependencyManagement entries that are not imports also carry versions
    if dm is not None:
        for dep in dm.findall("dependency"):
            if _text(dep, "scope") != "import":
                check_dep(dep)
    return out


def _check_boot_version(rel: str, what: str, version: str | None, ledger: Ledger) -> list[Violation]:
    if version is None:
        return []
    if not re.fullmatch(r"4\.1\.\d+", version):
        return [Violation("boot-version", rel, f"Spring Boot {what} {version} is not 4.1.x (3.x and 4.0.x are rejected)")]
    return []


def _check_versioned(rel: str, ga: str, ver: str | None, resolved: bool, ledger: Ledger, used: set[str]) -> list[Violation]:
    out: list[Violation] = []
    if ver is None or ver == "":
        return [Violation("unpinned-version", rel, f"{ga} has an empty version")]
    if not resolved:
        return [Violation("unresolved-property", rel, f"{ga} version {ver} uses an undefined property")]
    if UNPINNED_MAVEN_RE.search(ver):
        return [Violation("unpinned-version", rel, f"{ga} version '{ver}' is a range, wildcard, latest, or snapshot")]
    row = ledger.find(ga)
    if row is None:
        return [Violation("ledger-missing", rel, f"{ga} {ver} has no ledger row")]
    used.update(n.lower() for n in row.names)
    if "UNVERIFIED" in row.version:
        out.append(Violation("unverified-in-use", rel, f"{ga} uses a ledger row marked UNVERIFIED"))
    elif row.version != ver:
        out.append(Violation("version-mismatch", rel, f"{ga} is {ver} but the ledger row is {row.version}"))
    return out


def _check_managed(rel: str, ga: str, group: str, has_boot: bool, imported: dict[str, str], ledger: Ledger, used: set[str]) -> list[Violation]:
    bom = GROUP_BOMS.get(group)
    if bom is not None:
        out: list[Violation] = []
        if bom not in imported:
            out.append(Violation("bom-not-imported", rel, f"{ga} has no <version> and {bom} is not imported in dependencyManagement"))
        brow = ledger.find(bom)
        if brow is None:
            out.append(Violation("bom-ledger-missing", rel, f"{ga} is managed by {bom}, which has no ledger row"))
        else:
            used.update(n.lower() for n in brow.names)
            if "UNVERIFIED" in brow.version:
                out.append(Violation("unverified-in-use", rel, f"{bom} ledger row is marked UNVERIFIED"))
        own = ledger.find(ga)
        if own is not None:
            used.update(n.lower() for n in own.names)
        return out
    if not has_boot:
        return [Violation("no-managing-bom", rel, f"{ga} has no <version> and no Spring Boot parent or BOM manages it")]
    own = ledger.find(ga)
    if own is not None:
        used.update(n.lower() for n in own.names)
        if "UNVERIFIED" in own.version:
            return [Violation("unverified-in-use", rel, f"{ga} uses a ledger row marked UNVERIFIED")]
        return []
    if ledger.find(BOOT_ROW) is None:
        return [Violation("ledger-missing", rel, f"{ga} is Boot-managed but the Spring Boot row is missing from the ledger")]
    return []


# ----------------------------------------------------------------------------- Python


def _check_py_requirement(rel: str, req: str, ledger: Ledger, used: set[str], in_sidecar: bool) -> list[Violation]:
    req = req.split(";", 1)[0].strip()
    if not req:
        return []
    m = PY_REQ_RE.match(req)
    if not m:
        return [Violation("unpinned-version", rel, f"cannot parse requirement '{req}'")]
    name, rest = m.group(1), m.group(2).strip()
    n = norm_py(name)
    out: list[Violation] = []
    if n == "langgraph" or n.startswith("langgraph-"):
        out.append(Violation("forbidden-artifact", rel, f"{name}: langgraph is not used in Phase 1 (ADR-004)"))
    if re.search(r"(?i)minio", name):
        out.append(Violation("minio", rel, f"{name} is a MinIO dependency"))
    if n in SIDECAR_ONLY and not in_sidecar:
        out.append(Violation("sidecar-only", rel, f"{name} is allowed only in {SIDECAR_DIR}"))
    em = EXACT_PY_RE.match(rest)
    if not em or "*" in rest:
        out.append(Violation("unpinned-version", rel, f"{name} must be pinned with '==' to one exact version, found '{rest or 'no version'}'"))
        return out
    ver = em.group(1)
    row = ledger.find(name)
    if row is None:
        out.append(Violation("ledger-missing", rel, f"{name}=={ver} has no ledger row"))
        return out
    used.update(x.lower() for x in row.names)
    used.update(norm_py(x) for x in row.names)
    if "UNVERIFIED" in row.version:
        out.append(Violation("unverified-in-use", rel, f"{name} uses a ledger row marked UNVERIFIED"))
    elif row.version != ver:
        out.append(Violation("version-mismatch", rel, f"{name} is {ver} but the ledger row is {row.version}"))
    return out


def check_pyproject(path: Path, rel: str, ledger: Ledger, used: set[str]) -> list[Violation]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as e:
        return [Violation("manifest-parse", rel, str(e))]
    in_sidecar = rel.startswith(SIDECAR_DIR + "/")
    reqs: list[str] = []
    project = data.get("project", {})
    reqs += [r for r in project.get("dependencies", []) if isinstance(r, str)]
    for group in project.get("optional-dependencies", {}).values():
        reqs += [r for r in group if isinstance(r, str)]
    for group in data.get("dependency-groups", {}).values():
        reqs += [r for r in group if isinstance(r, str)]
    reqs += [r for r in data.get("build-system", {}).get("requires", []) if isinstance(r, str)]
    out: list[Violation] = []
    for r in reqs:
        out += _check_py_requirement(rel, r, ledger, used, in_sidecar)
    return out


def check_requirements(path: Path, rel: str, ledger: Ledger, used: set[str]) -> list[Violation]:
    in_sidecar = rel.startswith(SIDECAR_DIR + "/")
    out: list[Violation] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#") or line.startswith(("-r ", "-c ", "--")):
            continue
        if line.startswith(("-e", "git+", "http://", "https://")) or "@" in line.split(";", 1)[0]:
            out.append(Violation("unpinned-version", rel, f"'{line}' is not a pinned registry requirement"))
            continue
        line = re.sub(r"\s+--hash=\S+", "", line).rstrip("\\ ").strip()
        out += _check_py_requirement(rel, line, ledger, used, in_sidecar)
    return out


# ----------------------------------------------------------------------------- Node


def check_package_json(path: Path, rel: str, ledger: Ledger, used: set[str]) -> list[Violation]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return [Violation("manifest-parse", rel, str(e))]
    out: list[Violation] = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, ver in (data.get(section) or {}).items():
            if "langgraph" in name.lower():
                out.append(Violation("forbidden-artifact", rel, f"{name}: langgraph is not used in Phase 1"))
            if re.search(r"(?i)minio", name):
                out.append(Violation("minio", rel, f"{name} is a MinIO dependency"))
            if not isinstance(ver, str) or not EXACT_NPM_RE.match(ver):
                out.append(Violation("unpinned-version", rel, f"{name} version '{ver}' is not an exact version (no ^, ~, *, latest, or range)"))
                continue
            row = ledger.find(name)
            if row is None:
                out.append(Violation("ledger-missing", rel, f"{name}@{ver} has no ledger row"))
                continue
            used.update(x.lower() for x in row.names)
            if "UNVERIFIED" in row.version:
                out.append(Violation("unverified-in-use", rel, f"{name} uses a ledger row marked UNVERIFIED"))
            elif row.version != ver:
                out.append(Violation("version-mismatch", rel, f"{name} is {ver} but the ledger row is {row.version}"))
    return out


# ----------------------------------------------------------------------------- text scans


def _is_compose_or_manifest_text(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1].lower()
    return (
        name in {"pom.xml", "pyproject.toml", "package.json"}
        or name.startswith("requirements")
        or name.startswith("dockerfile")
        or re.match(r"(docker-)?compose.*\.ya?ml$", name) is not None
    )


def scan_text(path: Path, rel: str, ledger: Ledger) -> list[Violation]:
    name = path.name
    suffix = path.suffix.lower()
    if not (suffix in TEXT_SCAN_SUFFIXES or name.lower().startswith("dockerfile")):
        return []
    if rel.startswith("scripts/depcheck/") or rel.startswith("scripts/tests/") or rel == "scripts/check-dependency-pins":
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    out: list[Violation] = []
    if MINIO_SPECIFIC_RE.search(text) or (_is_compose_or_manifest_text(rel) and MINIO_ANY_RE.search(text)):
        out.append(Violation("minio", rel, "MinIO image, client, or Testcontainers module is not approved"))
    for m in IMAGE_RE.finditer(text):
        repo, tag, digest = m.group(1), m.group(2), m.group(3)
        if not tag and repo not in DIGEST_REQUIRED_REPOS:
            continue
        ref = m.group(0)
        if repo in DIGEST_REQUIRED_REPOS and (not digest or tag == "latest" or not tag):
            out.append(Violation("image-no-digest", rel, f"{ref} must be pinned by tag and @sha256 digest, never latest or bare"))
            continue
        row = _image_row(ledger, repo)
        if row is None:
            if repo in DIGEST_REQUIRED_REPOS:
                out.append(Violation("image-ledger-mismatch", rel, f"{ref} has no image row in the ledger"))
            continue
        if ref != row.version:
            out.append(Violation("image-ledger-mismatch", rel, f"{ref} differs from the ledger row {row.version}; change it only with a new dated decision and a ledger update (ADR-019)"))
    if suffix in {".java", ".kt"} and JACKSON2_IMPORT_RE.search(text):
        out.append(Violation("jackson2-import", rel, "imports com.fasterxml.jackson.databind; use tools.jackson.databind (ADR-006)"))
    return out


# ----------------------------------------------------------------------------- entry point


def check(root: Path, ledger_path: Path | None = None) -> tuple[list[Violation], list[str]]:
    """Return (violations, notes). Notes are informational lines (for example skipped checks)."""
    root = root.resolve()
    ledger_file = ledger_path or (root / LEDGER_NAME)
    notes: list[str] = []
    if not ledger_file.is_file():
        return [Violation("ledger-file", LEDGER_NAME, f"{ledger_file} not found")], notes
    ledger = parse_ledger(ledger_file.read_text(encoding="utf-8"))
    violations = check_ledger(ledger, ledger_file.name)
    used_real: set[str] = set()
    used_verification: set[str] = set()
    real_manifests = 0
    manifest_count = 0
    for path, rel in _walk(root):
        name = path.name
        used = used_verification if rel.startswith(VERIFICATION_DIR + "/") else used_real
        is_manifest = True
        if name == "pom.xml":
            violations += check_pom(path, rel, ledger, used)
        elif name == "pyproject.toml":
            violations += check_pyproject(path, rel, ledger, used)
        elif re.fullmatch(r"requirements.*\.txt", name):
            violations += check_requirements(path, rel, ledger, used)
        elif name == "package.json":
            violations += check_package_json(path, rel, ledger, used)
        else:
            is_manifest = False
        if is_manifest:
            manifest_count += 1
            if not rel.startswith(VERIFICATION_DIR + "/"):
                real_manifests += 1
        violations += scan_text(path, rel, ledger)

    if real_manifests == 0:
        notes.append("no service manifests exist yet: the ledger-unused check is skipped (it applies once task 1.1 creates manifests)")
    else:
        boot_used = BOOT_ROW in used_real
        for row in ledger.rows:
            if row.not_used or not re.match(r"(Java|Python|Node)", row.section):
                continue
            if "planned (task" in row.notes.lower():
                continue
            if boot_used and "boot-managed" in row.notes.lower():
                continue
            if not any(n.lower() in used_real or norm_py(n) in used_real for n in row.names):
                violations.append(Violation("ledger-unused", ledger_file.name, f"row '{', '.join(row.names)}' has no manifest entry; remove it, mark it 'Phase 2+, not used in Phase 1' in the not-used section, or add 'Planned (task N.M)' to its Notes"))
    notes.append(f"scanned {manifest_count} manifest(s), ledger has {len(ledger.rows)} rows")
    # stable, de-duplicated output
    seen = set()
    unique: list[Violation] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique, notes


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="check-dependency-pins", description="Check dependency pins against DEPENDENCIES.lock.md")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="repository root (default: this repository)")
    parser.add_argument("--ledger", type=Path, default=None, help=f"ledger file (default: <root>/{LEDGER_NAME})")
    args = parser.parse_args(argv)
    violations, notes = check(args.root, args.ledger)
    for n in notes:
        print(f"note: {n}")
    for v in violations:
        print(v)
    if violations:
        print(f"check-dependency-pins: {len(violations)} violation(s)")
        return 1
    print("check-dependency-pins: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
