import json
import re
import threading
import time
from flask import request, jsonify
from dbus_parser import parse_tree, parse_introspect, parse_services, parse_get_all

def _parse_event(lines):
    """Parse a busctl monitor signal block into a structured dict."""
    if not lines or not lines[0].startswith('>'):
        return None
    ev = {'time': '', 'path': '', 'interface': '', 'member': '', 'brief': ''}
    m = re.search(r'Timestamp="\w+ \d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})', lines[0])
    if m:
        ev['time'] = m.group(1)
    if len(lines) > 1:
        for key in ('Path', 'Interface', 'Member'):
            m = re.search(rf'\b{key}=(\S+)', lines[1])
            if m:
                ev[key.lower()] = m.group(1)
    payload = '\n'.join(lines[3:])
    strings = re.findall(r'STRING "([^"]+)"', payload)
    numerics = re.findall(r'(?:DOUBLE|INT32|INT64|UINT32|UINT64|BYTE)\s+([\d.e+\-]+)', payload)
    booleans = re.findall(r'BOOLEAN\s+(true|false)', payload)
    if ev['member'] == 'PropertiesChanged' and len(strings) >= 2:
        prop = strings[1]
        val = numerics[0] if numerics else (booleans[0] if booleans else (strings[2] if len(strings) > 2 else ''))
        ev['brief'] = f"{prop}={val}" if val else prop
        ev['iface_changed'] = strings[0]
        ev['prop_changed'] = prop
        ev['val_changed'] = val
    elif numerics:
        ev['brief'] = numerics[0]
    elif strings:
        ev['brief'] = strings[0][:50]
    return ev


def stream_cmd(client, cmd):
    """Generator to yield lines from an SSH command stream."""
    transport = client.get_transport()
    channel = transport.open_session()
    channel.exec_command(cmd)
    
    # Read line by line
    buf = ""
    while True:
        if channel.recv_ready():
            chunk = channel.recv(4096).decode('utf-8', errors='replace')
            buf += chunk
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                yield line.strip('\r')
        elif channel.exit_status_ready():
            # flush remaining
            while channel.recv_ready():
                chunk = channel.recv(4096).decode('utf-8', errors='replace')
                buf += chunk
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                yield line.strip('\r')
            if buf:
                yield buf.strip('\r')
            break
        else:
            time.sleep(0.1)


def register_dbus_routes(app, sock, get_pooled_client, evict_from_pool):
    
    def _run(host, port, user, password, cmd):
        client = get_pooled_client(host, port, user, password)
        _, stdout, stderr = client.exec_command(cmd, timeout=30)
        out = stdout.read().decode('utf-8', errors='replace')
        return out

    @app.get("/api/dbus/services")
    def api_dbus_services():
        host = request.args.get("host")
        port = int(request.args.get("port", 22))
        user = request.args.get("user")
        password = request.args.get("password", "")
        if not host or not user: return jsonify({"error": "missing params"}), 400
        
        try:
            raw = _run(host, port, user, password, "busctl list")
            svcs = parse_services(raw)
            return jsonify([s for s in svcs if not s["name"].startswith(":")])
        except Exception as e:
            evict_from_pool(host, port, user)
            return jsonify({"error": str(e)}), 500

    @app.get("/api/dbus/tree")
    def api_dbus_tree():
        host = request.args.get("host")
        port = int(request.args.get("port", 22))
        user = request.args.get("user")
        password = request.args.get("password", "")
        service = request.args.get("service", "")
        
        cmd = f"busctl tree {service}" if service else "busctl tree"
        try:
            raw = _run(host, port, user, password, cmd)
            return jsonify(parse_tree(raw))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/api/dbus/object")
    def api_dbus_object():
        host = request.args.get("host")
        port = int(request.args.get("port", 22))
        user = request.args.get("user")
        password = request.args.get("password", "")
        service = request.args.get("service", "")
        path = request.args.get("path", "")
        
        if not service or not path:
            return jsonify({"error": "service and path required"}), 400
        
        try:
            raw = _run(host, port, user, password, f"busctl introspect {service} {path}")
            return jsonify(parse_introspect(raw))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/api/dbus/properties")
    def api_dbus_properties():
        host = request.args.get("host")
        port = int(request.args.get("port", 22))
        user = request.args.get("user")
        password = request.args.get("password", "")
        service = request.args.get("service", "")
        path = request.args.get("path", "")
        
        if not service or not path: return jsonify({"error": "service and path required"}), 400
        try:
            introspect_raw = _run(host, port, user, password, f"busctl introspect {service} {path}")
            introspect = parse_introspect(introspect_raw)
            result = {}
            for iface, info in introspect.items():
                if not any(m["type"] == "property" for m in info["members"].values()):
                    continue
                raw = _run(host, port, user, password, f'busctl call {service} {path} org.freedesktop.DBus.Properties GetAll s "{iface}"')
                result[iface] = parse_get_all(raw)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/api/dbus/snapshot")
    def api_dbus_snapshot():
        host = request.args.get("host")
        port = int(request.args.get("port", 22))
        user = request.args.get("user")
        password = request.args.get("password", "")
        service = request.args.get("service", "")
        
        if not service: return jsonify({"error": "service required"}), 400
        try:
            paths = parse_tree(_run(host, port, user, password, f"busctl tree {service}"))
            snapshot = {}
            for path in paths:
                introspect = parse_introspect(_run(host, port, user, password, f"busctl introspect {service} {path}"))
                path_data = {}
                for iface, info in introspect.items():
                    if not any(m["type"] == "property" for m in info["members"].values()):
                        continue
                    raw = _run(host, port, user, password, f'busctl call {service} {path} org.freedesktop.DBus.Properties GetAll s "{iface}"')
                    path_data[iface] = parse_get_all(raw)
                if path_data:
                    snapshot[path] = path_data
            return jsonify(snapshot)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @sock.route("/ws/dbus/watch")
    def ws_dbus_watch(ws):
        host = request.args.get("host")
        port = int(request.args.get("port", 22))
        user = request.args.get("user")
        password = request.args.get("password", "")
        path = request.args.get("path", "")
        iface = request.args.get("interface", "")
        
        args = []
        if path: args.append(f"path={path}")
        if iface: args.append(f"interface={iface}")
        cmd = ("busctl monitor " + " ".join(args)).strip()
        
        stop = threading.Event()
        
        def _stream():
            try:
                client = get_pooled_client(host, port, user, password)
                block = []
                for line in stream_cmd(client, cmd):
                    if stop.is_set(): break
                    if line.startswith('>'):
                        if block:
                            ev = _parse_event(block)
                            if ev:
                                try: ws.send(json.dumps({"event": ev}))
                                except Exception: return
                        block = [line]
                    else:
                        block.append(line)
            except Exception as e:
                try: ws.send(json.dumps({"error": str(e)}))
                except Exception: pass

        t = threading.Thread(target=_stream, daemon=True)
        t.start()
        try:
            while True:
                ws.receive()  # blocks until client closes; ConnectionClosed is raised and caught below
        except Exception:
            pass
        finally:
            stop.set()
