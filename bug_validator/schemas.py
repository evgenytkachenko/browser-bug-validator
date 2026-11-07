"""Internal phase contracts, sent to Ollama and independently checked locally.

This is a validator for the small schema subset used here, not a general JSON
Schema implementation. Callers cannot supply or relax a phase contract.
"""
from .common import ValidationError


def plan_schema(journey_id):
    return {"type": "object", "additionalProperties": False,
            "required": ["journey_id", "target_task_id", "expected_status"],
            "properties": {
                "journey_id": {"type": ["string", "null"], "enum": [journey_id, None]},
                "target_task_id": {"type": "string", "minLength": 3, "maxLength": 8},
                "expected_status": {"type": "string", "enum": ["todo", "doing", "done"]}}}


def assessment_schema(evidence_ids):
    return {"type": "object", "additionalProperties": False,
            "required": ["saved_status", "reloaded_status", "status_persisted", "evidence_ids", "explanation"],
            "properties": {
                "saved_status": {"type": "string", "enum": ["todo", "doing", "done"]},
                "reloaded_status": {"type": "string", "enum": ["todo", "doing", "done"]},
                "status_persisted": {"type": ["boolean", "null"]},
                "evidence_ids": {"type": "array", "minItems": 2, "maxItems": len(evidence_ids),
                                 "uniqueItems": True, "items": {"type": "string", "enum": list(evidence_ids)}},
                "explanation": {"type": "string", "minLength": 1, "maxLength": 2000}}}


def validate_response(value, schema, path="response"):
    supported = {"type", "enum", "properties", "required", "additionalProperties", "minLength", "maxLength",
                 "items", "minItems", "maxItems", "uniqueItems"}
    if set(schema) - supported:
        raise ValidationError("Unsupported internal response-schema keyword")
    kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    actual = "null" if value is None else {dict: "object", list: "array", str: "string", bool: "boolean"}.get(type(value))
    if actual not in kinds:
        raise ValidationError(f"{path}: response type violates phase contract")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{path}: value is outside phase contract")
    if actual == "object":
        properties = schema["properties"]
        if set(schema["required"]) - set(value):
            raise ValidationError(f"{path}: missing phase-contract field")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValidationError(f"{path}: unexpected field; do not salvage or strip model output")
        for key, item in value.items():
            validate_response(item, properties[key], path + "." + key)
    elif actual == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 100000):
            raise ValidationError(f"{path}: array length violates phase contract")
        if schema.get("uniqueItems") and any(item in value[:index] for index, item in enumerate(value)):
            raise ValidationError(f"{path}: duplicate evidence references")
        for index, item in enumerate(value):
            validate_response(item, schema["items"], f"{path}[{index}]")
    elif actual == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 100000):
            raise ValidationError(f"{path}: string length violates phase contract")


def reject_duplicate_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("Duplicate JSON field in model response")
        result[key] = value
    return result
