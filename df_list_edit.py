#!/usr/bin/env python3
import argparse, csv, io, re, subprocess, json, sys
from pathlib import Path
import os

# Configurazione via variabili d'ambiente (es. export ADSB_REPO_PATH="/path/to/repo")
REPO = Path(os.getenv("ADSB_REPO_PATH", "./df-adsb-lists"))
BRANCH = os.getenv("ADSB_BRANCH", "main")
REMOTE = os.getenv("ADSB_REMOTE", "origin")

# File di esempio (adatta ai tuoi CSV su GitHub)
FILES = {
  "mil": "plane-alert-mil-images.csv",
  "gov": "plane-alert-gov-images.csv",
  "pol": "plane-alert-pol-images.csv",
  "flyingdocs": "plane-alert-flyingdocs.csv",
  "civcur": "plane-alert-civ-curated-images.csv",
}

# Alias liste (es. "civ" -> "civcur")
LIST_ALIASES = {
    "civ": "civcur",
}


def warn(msg: str):
    print(f"WARNING: {msg}", file=sys.stderr)


def norm_hex(h: str) -> str:
    h = (h or "").strip().lower().replace("0x", "")
    if not re.fullmatch(r"[0-9a-f]{6}", h):
        raise SystemExit("HEX non valido (serve 6 esadecimali)")
    return h.upper()


def parse_line(line: str):
    line = (line or "").strip()
    return next(csv.reader([line]))


def to_line(row):
    s = io.StringIO()
    csv.writer(s, lineterminator="").writerow(row)
    return s.getvalue() + "\n"


def normalize_url(u: str) -> str:
    u = (u or "").strip()
    if u and not (u.startswith("http://") or u.startswith("https://")):
        warn("Link senza schema, aggiungo https://")
        u = "https://" + u.lstrip("/")
    return u


def normalize_cmpg(list_name: str, cmpg: str) -> str:
    c = (cmpg or "").strip()
    if not c:
        return {"mil": "Mil", "pol": "Pol", "gov": "Gov", "flyingdocs": "", "civcur": "Civ"}.get(list_name, "")
    m = {
        "mil": "Mil", "Mil": "Mil", "MIL": "Mil",
        "pol": "Pol", "Pol": "Pol", "POL": "Pol",
        "gov": "Gov", "Gov": "Gov", "GOV": "Gov",
        "civ": "Civ", "Civ": "Civ", "CIV": "Civ",
    }
    if c in m:
        return m[c]
    warn(f"CMPG non standard '{c}' (consigliati: Mil/Pol/Gov/Civ)")
    return c


def looks_like_callsign(s: str) -> bool:
    s = (s or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z]{2,4}\d{2,6}", s))


def ensure_git_safe_directory(repo: Path):
    try:
        subprocess.run(["git", "-C", str(repo), "status"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    except Exception:
        pass

    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(repo)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        warn("Git safe.directory non impostabile automaticamente.")
        warn(f"Esegui: git config --global --add safe.directory {repo}")


def repo_sync_hard(repo: Path, offline_ok: bool):
    ensure_git_safe_directory(repo)

    if not (repo / ".git").exists():
        raise SystemExit(f"{repo} non sembra un repository git (manca .git)")

    # Backup uncommitted changes
    diff = subprocess.run(["git", "-C", str(repo), "diff"], capture_output=True, text=True)
    diff_cached = subprocess.run(["git", "-C", str(repo), "diff", "--cached"], capture_output=True, text=True)
    content = (diff.stdout or "") + "\n" + (diff_cached.stdout or "")
    if content.strip():
        import time
        ts = time.strftime("%Y%m%d-%H%M%S")
        bdir = repo / ".local-backup"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / f"uncommitted-{ts}.patch").write_text(content, encoding="utf-8", errors="replace")
        warn(f"Modifiche locali salvate in .local-backup/uncommitted-{ts}.patch")

    subprocess.run(["git", "-C", str(repo), "reset", "--hard"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "clean", "-fd"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    r = subprocess.run(["git", "-C", str(repo), "fetch", REMOTE])
    if r.returncode != 0:
        if offline_ok:
            warn("git fetch fallito (offline?), continuo con repo locale.")
            return
        raise SystemExit("git fetch fallito. Se vuoi continuare offline usa --offline-ok.")

    subprocess.run(["git", "-C", str(repo), "checkout", BRANCH], check=True)
    subprocess.run(["git", "-C", str(repo), "reset", "--hard", f"{REMOTE}/{BRANCH}"], check=True)
    subprocess.run(["git", "-C", str(repo), "clean", "-fd"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def apply_list_aliases(args):
    args.list = (args.list or "").strip()
    if args.list in LIST_ALIASES:
        args.list = LIST_ALIASES[args.list]


def apply_args_normalizations(args):
    hx = norm_hex(args.hex)
    args.hex = hx
    args.link = normalize_url(getattr(args, "link", ""))
    args.cmpg = normalize_cmpg(args.list, getattr(args, "cmpg", ""))
    if args.reg and looks_like_callsign(args.reg) and not args.reg.upper().startswith("MM"):
        warn(f"Registrazione '{args.reg}' sembra un callsign (mettila in Tag3?)")
    return hx


def print_json(args, hx: str):
    print(json.dumps({
        "hex": hx,
        "reg": args.reg,
        "operator": args.operator,
        "type": args.atype,
        "icao_type": args.icao_type,
        "cmpg": args.cmpg,
        "tag1": args.tag1,
        "tag2": args.tag2,
        "tag3": args.tag3,
        "category": args.category,
        "link": args.link,
        "img1": args.img1,
        "img2": args.img2,
        "img3": args.img3,
        "img4": args.img4,
    }, ensure_ascii=False))


def _norm_cell(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _row_pad(row, n):
    return (row + [""] * n)[:n]


def _rows_equal(a, b) -> bool:
    return [_norm_cell(x) for x in a] == [_norm_cell(x) for x in b]


def read_csv_file(path: Path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        raise SystemExit(f"File vuoto: {path}")
    header = parse_line(lines[0])
    rows = [parse_line(x) for x in lines[1:] if x.strip()]
    return header, rows


def write_csv_file(path: Path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(to_line(header))
        for r in rows:
            f.write(to_line(r))


def remove_hex_from_file(path: Path, hx_up: str) -> bool:
    header, rows = read_csv_file(path)
    hx = hx_up.strip().upper()
    new_rows = [r for r in rows if (r and (r[0] or "").strip().upper() != hx)]
    if len(new_rows) == len(rows):
        return False
    new_rows.sort(key=lambda r: (r[0] or "").strip().upper() if r else "")
    write_csv_file(path, header, new_rows)
    return True


def delete_hex_everywhere(hx_up: str):
    hx = (hx_up or "").strip().upper()
    changed_files = []

    for lk, fn in FILES.items():
        p = REPO / fn
        if not p.is_file():
            continue
        if remove_hex_from_file(p, hx):
            print(f"Deleted: removed {hx} from {lk}({fn})")
            changed_files.append(p)

    # Dedup paths
    uniq = []
    seen = set()
    for p in changed_files:
        if str(p) not in seen:
            uniq.append(p)
            seen.add(str(p))
    return uniq


def find_hex_locations(hex_up: str):
    hx = (hex_up or "").strip().upper()
    hits = []
    for lk, fn in FILES.items():
        p = REPO / fn
        if not p.is_file():
            continue
        try:
            _, rows = read_csv_file(p)
            for row in rows:
                if row and (row[0] or "").strip().upper() == hx:
                    hits.append((lk, fn))
                    break
        except Exception as e:
            warn(f"Impossibile leggere {fn}: {e}")
    return hits


def _row_to_dict(header, row):
    row = _row_pad(row, len(header))
    return {header[i]: row[i] for i in range(len(header))}


def _clean_colname(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("$", "").replace("#", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _record_to_gui_keys(rec_raw: dict) -> dict:
    m = {
        "ICAO": "hex",
        "Registration": "reg",
        "Operator": "operator",
        "Type": "atype",
        "ICAO Type": "icao_type",
        "CMPG": "cmpg",
        "Tag 1": "tag1",
        "Tag 2": "tag2",
        "Tag 3": "tag3",
        "Category": "category",
        "Link": "link",
        "ImageLink": "img1",
        "ImageLink2": "img2",
        "ImageLink3": "img3",
        "ImageLink4": "img4",
    }

    out = {}
    for k, v in (rec_raw or {}).items():
        kk = m.get(_clean_colname(k))
        if kk:
            out[kk] = (v or "").strip()
    return out


def find_hex_locations_with_records(hex_up: str):
    hx = (hex_up or "").strip().upper()
    hits = []
    for lk, fn in FILES.items():
        p = REPO / fn
        if not p.is_file():
            continue
        try:
            header, rows = read_csv_file(p)
            for row in rows:
                if row and (row[0] or "").strip().upper() == hx:
                    rec_raw = _row_to_dict(header, row)
                    rec = _record_to_gui_keys(rec_raw)

                    out_list = "civ" if lk == "civcur" else lk
                    hits.append({"list": out_list, "file": fn, "record": rec})
                    break
        except Exception as e:
            warn(f"Impossibile leggere {fn}: {e}")
    return hits


def _field_names_from_header(header):
    return header


def diff_against_target(args, hx: str):
    target_path = REPO / FILES[args.list]
    header, rows = read_csv_file(target_path)

    new_row = [
        hx, args.reg, args.operator, args.atype, args.icao_type, args.cmpg,
        args.tag1, args.tag2, args.tag3, args.category, args.link,
        args.img1, args.img2, args.img3, args.img4
    ]
    new_row = _row_pad(new_row, len(header))

    old_row = None
    for r in rows:
        if r and (r[0] or "").strip().upper() == hx:
            old_row = _row_pad(r, len(header))
            break

    locations = [{"list": lk, "file": fn} for lk, fn in find_hex_locations(hx)]
    will_move_from = [x for x in locations if x["list"] != args.list]

    changes = []
    field_names = _field_names_from_header(header)
    old_dict = _row_to_dict(field_names, old_row or [""] * len(header))
    new_dict = _row_to_dict(field_names, new_row)

    for k in field_names:
        new_val = _norm_cell(new_dict.get(k, ""))
        if new_val:
            old_val = _norm_cell(old_dict.get(k, ""))
            if old_val != new_val:
                changes.append({
                    "field": k, 
                    "old": old_dict.get(k, ""), 
                    "new": new_val
                })

    return {
        "hex": hx,
        "target_list": args.list,
        "target_file": target_path.name,
        "exists_in_target": bool(old_row),
        "locations": locations,
        "will_move_from": will_move_from,
        "changes": changes,
    }


def upsert_into_target(args, hx: str):
    p = REPO / FILES[args.list]
    header, rows = read_csv_file(p)

    new_row = [
        hx, args.reg, args.operator, args.atype, args.icao_type, args.cmpg,
        args.tag1, args.tag2, args.tag3, args.category, args.link,
        args.img1, args.img2, args.img3, args.img4
    ]
    new_row = _row_pad(new_row, len(header))

    idx = None
    for i, r in enumerate(rows):
        if r and (r[0] or "").strip().upper() == hx:
            idx = i
            break

    if idx is None:
        rows.append(new_row)
        changed = True
        action = "Added"
    else:
        old_row = _row_pad(rows[idx], len(header))
        if _rows_equal(old_row, new_row):
            changed = False
            action = "Unchanged"
        else:
            rows[idx] = new_row
            changed = True
            action = "Updated"

    rows.sort(key=lambda r: (r[0] or "").strip().upper() if r else "")
    write_csv_file(p, header, rows)
    return p, changed, action


def write_csv(args, hx: str):
    changed_files = []

    locs = find_hex_locations(hx)
    for lk, fn in locs:
        if lk == args.list:
            continue
        path_src = REPO / fn
        if remove_hex_from_file(path_src, hx):
            print(f"Moved: removed {hx} from {lk}({fn})")
            changed_files.append(path_src)

    p_tgt, changed, action = upsert_into_target(args, hx)
    if changed:
        print(action, hx, "in", p_tgt.name)
        changed_files.append(p_tgt)
    else:
        print(f"ERROR: HEX {hx} già presente in: {args.list}({p_tgt.name}). Nessuna modifica applicata (identico).")
        raise SystemExit(2)

    uniq = []
    seen = set()
    for p in changed_files:
        if str(p) not in seen:
            uniq.append(p)
            seen.add(str(p))
    return uniq


def git_push(args, paths, hx: str):
    ensure_git_safe_directory(REPO)

    for p in paths:
        subprocess.run(["git", "-C", str(REPO), "add", p.name], check=True)

    r = subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet"])
    if r.returncode != 0:
        msg = f"Upsert {hx} -> {args.list}"
        subprocess.run(["git", "-C", str(REPO), "commit", "-m", msg], check=True)
        subprocess.run(["git", "-C", str(REPO), "push"], check=True)
        print("Pushed")
    else:
        print("Nothing to commit")


def apply_stdin_json(args):
    req = json.loads(sys.stdin.read() or "{}")

    action = (req.get("action") or "").strip().lower()
    args._action = action

    if action == "ping":
        print("OK")
        raise SystemExit(0)

    if action == "sync":
        args.offline_ok = bool(req.get("offline_ok", False))
        return

    if req.get("list"):
        args.list = req.get("list")
    if req.get("hex"):
        args.hex = req.get("hex")

    for k in ["reg","operator","cmpg","tag1","tag2","tag3","category","link","img1","img2","img3","img4"]:
        if k in req:
            setattr(args, k, req.get(k) or "")

    if "icao_type" in req:
        args.icao_type = req.get("icao_type") or ""
    if "type" in req:
        args.atype = req.get("type") or ""

    if action == "autofill":
        args.autofill = True
        args.json = True
    elif action == "publish":
        args.push = bool(req.get("push", True))
    elif action == "delete":
        args.push = bool(req.get("push", True))
    elif action in ("where", "diff"):
        pass
    else:
        args.autofill = bool(req.get("autofill", args.autofill))
        args.json = bool(req.get("json", args.json))
        args.push = bool(req.get("push", args.push))


def parse_args_cli():
    ap = argparse.ArgumentParser(description="Gestisce liste ADS-B in repo GitHub (publish/delete/sync)")

    ap.add_argument("--list", choices=list(FILES.keys()))
    ap.add_argument("--hex")

    ap.add_argument("--reg", default="")
    ap.add_argument("--operator", default="")
    ap.add_argument("--type", dest="atype", default="")
    ap.add_argument("--icao-type", dest="icao_type", default="")
    ap.add_argument("--cmpg", default="")
    ap.add_argument("--tag1", default="")
    ap.add_argument("--tag2", default="")
    ap.add_argument("--tag3", default="")
    ap.add_argument("--category", default="")
    ap.add_argument("--link", default="")
    ap.add_argument("--img1", default="")
    ap.add_argument("--img2", default="")
    ap.add_argument("--img3", default="")
    ap.add_argument("--img4", default="")

    ap.add_argument("--autofill", action="store_true", help="Auto-riempi campi da fonti esterne (disabilitato)")
    ap.add_argument("--json", action="store_true", help="Output JSON invece di modificare")
    ap.add_argument("--push", action="store_true", help="Commit/push su Git dopo modifiche")

    ap.add_argument("--stdin-json", action="store_true",
                    help="Legge una richiesta JSON da stdin (per GUI/Telegram bot).")

    ap.add_argument("--offline-ok", action="store_true",
                    help="Se GitHub non raggiungibile, continua comunque (NO sync).")

    ap.set_defaults(_action="")

    args = ap.parse_args()
    return ap, args


def main():
    ap, args = parse_args_cli()

    if args.stdin_json:
        apply_stdin_json(args)

    apply_list_aliases(args)

    if args._action == "sync":
        repo_sync_hard(REPO, offline_ok=getattr(args, "offline_ok", False))
        print("OK")
        return 0

    if args._action == "where":
        if not args.hex:
            ap.error("the following arguments are required: --hex")
        repo_sync_hard(REPO, offline_ok=args.offline_ok)
        hx = norm_hex(args.hex)
        locs = find_hex_locations_with_records(hx)
        print(json.dumps({"hex": hx, "locations": locs}, ensure_ascii=False))
        return 0

    if args._action == "diff":
        if not args.hex or not args.list:
            ap.error("the following arguments are required: --list, --hex")
        repo_sync_hard(REPO, offline_ok=args.offline_ok)
        hx = apply_args_normalizations(args)
        dj = diff_against_target(args, hx)
        print(json.dumps(dj, ensure_ascii=False))
        return 0

    if args._action == "delete":
        if not args.hex:
            ap.error("the following arguments are required: --hex")

        repo_sync_hard(REPO, offline_ok=args.offline_ok)

        hx = norm_hex(args.hex)
        changed_paths = delete_hex_everywhere(hx)

        if args.push and changed_paths:
            args.list = "DELETE"
            git_push(args, changed_paths, hx)
        elif args.push and not changed_paths:
            print("Nothing to commit")

        return 0

    if not args.list or not args.hex:
        ap.error("the following arguments are required: --list, --hex")

    repo_sync_hard(REPO, offline_ok=args.offline_ok)

    hx = apply_args_normalizations(args)

    # Autofill disabilitato per privacy (no paths locali)
    if args.autofill:
        warn("--autofill disabilitato in questa versione pulita")

    if args.json:
        print_json(args, hx)
        return 0

    changed_paths = write_csv(args, hx)

    if args.push:
        git_push(args, changed_paths, hx)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
