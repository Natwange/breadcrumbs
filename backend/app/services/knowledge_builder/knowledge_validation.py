"""Validate extracted architecture proposals.

Artifact text is untrusted input — validation ensures proposals are well-formed
and do not smuggle secrets or instruction-like payloads into the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.knowledge_builder.secret_redactor import contains_likely_secret

_MAX_NAME_LEN = 255
_MAX_ITEMS = 200


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_extraction(payload: dict) -> ValidationResult:
    errors: list[str] = []

    services = payload.get("services", [])
    dependencies = payload.get("dependencies", [])
    runbooks = payload.get("runbooks", [])

    if not isinstance(services, list):
        errors.append("services must be a list")
        services = []
    if not isinstance(dependencies, list):
        errors.append("dependencies must be a list")
        dependencies = []
    if not isinstance(runbooks, list):
        errors.append("runbooks must be a list")
        runbooks = []

    total = len(services) + len(dependencies) + len(runbooks)
    if total > _MAX_ITEMS:
        errors.append(f"too many proposed items ({total} > {_MAX_ITEMS})")

    service_names: set[str] = set()
    for idx, svc in enumerate(services):
        if not isinstance(svc, dict):
            errors.append(f"services[{idx}] must be an object")
            continue
        name = svc.get("name")
        if not name or not isinstance(name, str):
            errors.append(f"services[{idx}].name is required")
            continue
        if len(name) > _MAX_NAME_LEN:
            errors.append(f"services[{idx}].name too long")
        if contains_likely_secret(name) or contains_likely_secret(str(svc.get("description", ""))):
            errors.append(f"services[{idx}] contains likely secret material")
        service_names.add(name.lower())

    for idx, dep in enumerate(dependencies):
        if not isinstance(dep, dict):
            errors.append(f"dependencies[{idx}] must be an object")
            continue
        up = dep.get("upstream")
        down = dep.get("downstream")
        if not up or not down:
            errors.append(f"dependencies[{idx}] requires upstream and downstream")
        if up and down and str(up).lower() == str(down).lower():
            errors.append(f"dependencies[{idx}] cannot be self-referential")

    for idx, rb in enumerate(runbooks):
        if not isinstance(rb, dict):
            errors.append(f"runbooks[{idx}] must be an object")
            continue
        title = rb.get("title")
        if not title:
            errors.append(f"runbooks[{idx}].title is required")
        content = str(rb.get("content", ""))
        if contains_likely_secret(content):
            errors.append(f"runbooks[{idx}] content contains likely secret material")

    return ValidationResult(valid=len(errors) == 0, errors=errors)
