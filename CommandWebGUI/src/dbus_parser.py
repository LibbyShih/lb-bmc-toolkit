import ast
import json
import re
from typing import Any


def parse_tree(output: str) -> list[str]:
    """Extract object paths from `busctl tree` output (preserves order, no duplicates)."""
    paths: list[str] = []
    seen: set[str] = set()
    for line in output.splitlines():
        for token in reversed(line.split()):
            if token.startswith("/"):
                if token not in seen:
                    paths.append(token)
                    seen.add(token)
                break
    return paths


def parse_introspect(output: str) -> dict[str, Any]:
    """Parse `busctl introspect` output.

    Returns: {interface_name: {members: {member_name: {type, signature}}}}
    """
    result: dict[str, Any] = {}
    current_iface: str | None = None
    lines = output.splitlines()
    # Skip the header line ("NAME  TYPE  SIGNATURE ...")
    if lines and lines[0].startswith("NAME"):
        lines = lines[1:]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        name, type_ = parts[0], parts[1]
        sig = parts[2] if len(parts) > 2 else "-"
        if name.startswith("."):
            if current_iface is not None:
                result[current_iface]["members"][name[1:]] = {
                    "type": type_,
                    "signature": sig,
                }
        else:
            current_iface = name
            result[name] = {"members": {}}
    return result


def parse_dbus_value(tokens: list[str], index: int) -> tuple[Any, int]:
    if index >= len(tokens):
        return None, index

    dtype = tokens[index]
    index += 1

    SIMPLE_TYPES = {'s', 'o', 'g', 'b', 't', 'u', 'i', 'x', 'q', 'n', 'y', 'd'}

    if dtype in SIMPLE_TYPES:
        if index >= len(tokens):
            return None, index
        val_str = tokens[index]
        index += 1
        if dtype in ('s', 'o', 'g'):
            try:
                val = ast.literal_eval(val_str)
            except Exception:
                val = val_str.strip('"')
            return val, index
        elif dtype == 'b':
            return val_str.lower() == 'true', index
        else:
            try:
                if '.' in val_str:
                    return float(val_str), index
                else:
                    return int(val_str, 0), index
            except Exception:
                return val_str, index

    elif dtype == 'v':
        return parse_dbus_value(tokens, index)

    elif dtype.startswith('a'):
        if index >= len(tokens):
            return None, index
        count_str = tokens[index]
        index += 1
        try:
            count = int(count_str)
        except Exception:
            return f"<{dtype} parse error>", index

        if dtype == 'a{sv}' or dtype == 'a{ss}':
            res_dict = {}
            for _ in range(count):
                if index >= len(tokens): break
                key_str = tokens[index]
                index += 1
                try:
                    key = ast.literal_eval(key_str)
                except Exception:
                    key = key_str.strip('"')
                
                if dtype == 'a{sv}':
                    val, index = parse_dbus_value(tokens, index)
                else:
                    if index >= len(tokens): break
                    val_str = tokens[index]
                    index += 1
                    try:
                        val = ast.literal_eval(val_str)
                    except Exception:
                        val = val_str.strip('"')
                res_dict[key] = val
            return res_dict, index

        elif dtype == 'as' or dtype == 'ao':
            res_list = []
            for _ in range(count):
                if index >= len(tokens): break
                val_str = tokens[index]
                index += 1
                try:
                    val = ast.literal_eval(val_str)
                except Exception:
                    val = val_str.strip('"')
                res_list.append(val)
            return res_list, index

        else:
            return f"<{dtype} array with {count} items>", index

    return f"<{dtype}>", index


def parse_get_all(output: str) -> dict[str, Any]:
    """Parse `busctl call GetAll` output. Returns {propName: displayValue}."""
    output = output.strip()
    if not output:
        return {}
    
    if output.startswith('{'):
        try:
            return json.loads(output)
        except Exception:
            pass

    if not output.startswith('a{sv}'):
        return {}

    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\S+', output)
    parsed_dict, _ = parse_dbus_value(tokens, 0)
    if isinstance(parsed_dict, dict):
        return parsed_dict
    return {}


def parse_services(output: str) -> list[dict[str, str]]:
    """Parse `busctl list` output.

    Returns: [{name, pid, process}]
    """
    result: list[dict[str, str]] = []
    lines = output.splitlines()
    if not lines:
        return result
    for line in lines[1:]:  # skip header
        parts = line.split()
        if len(parts) < 3:
            continue
        result.append({"name": parts[0], "pid": parts[1], "process": parts[2]})
    return result
