"""First project adapter. The orchestration engine does not know Java endpoint names."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "proposals"
BASE = EXAMPLES / "base"
JAVA = "src/main/java/dev/canopy/links/"
STATS = JAVA + "StatsController.java"
PREVIEW = JAVA + "PreviewController.java"
PACK = EXAMPLES / "link-preview"


def prepare_preview(base, supplied):
    if not {STATS, JAVA + "LinksController.java", "pom.xml"} <= base.keys():
        raise ValueError("Link preview requires accepted create, redirect and aggregate statistics")
    additions = [PREVIEW, "src/test/java/dev/canopy/links/PreviewContractTest.java",
                 "src/test/resources/dev/canopy/links/preview.feature"]
    if set(additions) & base.keys():
        raise ValueError("Link preview files already exist in the accepted baseline")
    if supplied is not None and (not isinstance(supplied, dict) or set(supplied) != {PREVIEW}
                                 or not isinstance(supplied[PREVIEW], str) or not supplied[PREVIEW].strip()
                                 or len(supplied[PREVIEW].encode()) > 128_000):
        raise ValueError("Only the planned preview controller may be supplied")
    changes = {p: (PACK / p).read_text(encoding="utf-8") for p in additions}
    if supplied is not None:
        changes.update(supplied)
    marker = "  </dependencies>"
    if base["pom.xml"].count(marker) != 1 or "karate-junit5" in base["pom.xml"]:
        raise ValueError("Unexpected baseline Maven dependency layout; review the test integration")
    changes["pom.xml"] = base["pom.xml"].replace(marker, """    <dependency>
      <groupId>com.intuit.karate</groupId>
      <artifactId>karate-junit5</artifactId>
      <version>1.4.1</version>
      <scope>test</scope>
    </dependency>
""" + marker)
    return changes, base, sorted(p for p in base if p.startswith(JAVA))


def interpret(request):
    words = set(re.findall(r"[a-z]+", request.lower()))
    if "karate" in words and words & {"expand", "expansion"}:
        return "expansion-contract", "Preview a stored destination without redirecting or recording a visit; verify the HTTP contract with Karate."
    if words & {"secure", "faster", "optimize", "scale", "safer"}:
        return None, "Which behavior should change, for whom, and what observable result is acceptable?"
    create = bool(words & {"shortener", "shorten", "short"} and words & {"build", "create", "redirect", "generate"})
    if words & {"stats", "analytics", "counts"}:
        if create:
            return "full-product", "Create and redirect short HTTP(S) links and expose aggregate usage totals."
        return "analytics", "Expose aggregate redirect counts; preserve create and redirect behavior."
    if create:
        return "create-redirect", "Create short links for HTTP(S) destinations and redirect known codes."
    return None, "This adapter supports create/redirect and aggregate analytics. Clarify or review a new adapter."


def source_paths():
    return sorted(p.relative_to(BASE).as_posix() for p in (BASE / JAVA).glob("*.java"))


def prepare(feature, baseline, supplied):
    paths = source_paths()
    if not paths or STATS not in paths:
        raise ValueError("Missing product source fixture")
    if feature == "analytics" and not baseline:
        raise ValueError("Analytics requires a previously accepted create/redirect baseline")
    allowed = {STATS} if feature == "analytics" else set(paths) if feature == "full-product" else set(paths) - {STATS}
    if feature != "analytics" and baseline:
        raise ValueError("Greenfield creation requires an empty baseline")
    if allowed & baseline.keys():
        raise ValueError("Feature already present in accepted baseline")
    creates = ({p: (BASE / p).read_text(encoding="utf-8") for p in sorted(allowed)}
               if supplied is None else supplied)
    if not isinstance(creates, dict) or set(creates) != allowed:
        raise ValueError("Proposal must contain exactly the planned Java file paths; scaffolding is protected")
    if any(not isinstance(s, str) or not s.strip() or len(s.encode()) > 128_000 for s in creates.values()):
        raise ValueError("Expected bounded nonempty Java source text")
    scaffold = {"pom.xml": (BASE / "pom.xml").read_text(encoding="utf-8")}
    for folder in ("src/main/resources", "src/test"):
        for path in sorted((BASE / folder).rglob("*")):
            if path.is_file() and not (feature == "create-redirect" and path.name == "StatsTest.java"):
                scaffold[path.relative_to(BASE).as_posix()] = path.read_text(encoding="utf-8")
    impact = sorted(p for p in baseline if p.startswith(JAVA))
    return creates, scaffold, impact
