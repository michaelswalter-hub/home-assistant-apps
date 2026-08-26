from flask import Flask, request, redirect, render_template, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
import sqlite3, re, uuid, json, socket, ipaddress, html, base64, mimetypes, os, io
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from pathlib import Path
from datetime import datetime, date, timedelta

app = Flask(__name__)
DB = "/data/rezepte.db"
IMG_DIR = Path("/data/images")
IMG_DIR.mkdir(parents=True, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def ensure_column(con, table, name, ddl):
    cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
    if name not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

def init_db():
    con = db()
    con.execute("""CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, ingredients TEXT DEFAULT '', steps TEXT DEFAULT '',
        book TEXT DEFAULT '', created_at TEXT NOT NULL)""")
    ensure_column(con, "recipes", "image", "TEXT DEFAULT ''")
    ensure_column(con, "recipes", "image_source", "TEXT DEFAULT ''")
    ensure_column(con, "recipes", "source_url", "TEXT DEFAULT ''")
    ensure_column(con, "recipes", "source_name", "TEXT DEFAULT ''")
    ensure_column(con, "recipes", "servings", "TEXT DEFAULT ''")
    ensure_column(con, "recipes", "prep_minutes", "INTEGER DEFAULT 0")
    ensure_column(con, "recipes", "cook_minutes", "INTEGER DEFAULT 0")
    ensure_column(con, "recipes", "total_minutes", "INTEGER DEFAULT 0")
    ensure_column(con, "recipes", "calories_total", "REAL DEFAULT 0")
    ensure_column(con, "recipes", "calories_serving", "REAL DEFAULT 0")
    ensure_column(con, "recipes", "protein_g", "REAL DEFAULT 0")
    ensure_column(con, "recipes", "carbs_g", "REAL DEFAULT 0")
    ensure_column(con, "recipes", "fat_g", "REAL DEFAULT 0")
    ensure_column(con, "recipes", "fiber_g", "REAL DEFAULT 0")
    ensure_column(con, "recipes", "nutrition_updated_at", "TEXT DEFAULT ''")
    con.execute("""CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, recipe_id INTEGER NOT NULL,
        note TEXT DEFAULT '', rating INTEGER DEFAULT 0, cooked_at TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS meal_plan (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_date TEXT NOT NULL,
        meal TEXT NOT NULL, recipe_id INTEGER, UNIQUE(plan_date, meal))""")
    con.execute("""CREATE TABLE IF NOT EXISTS cookbooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE)""")
    cookbook_cols={x["name"] for x in con.execute("PRAGMA table_info(cookbooks)").fetchall()}
    if "cover" not in cookbook_cols:
        con.execute("ALTER TABLE cookbooks ADD COLUMN cover TEXT NOT NULL DEFAULT ''")
    if "color" not in cookbook_cols:
        con.execute("ALTER TABLE cookbooks ADD COLUMN color TEXT NOT NULL DEFAULT '#6f5bd3'")
    con.execute("""CREATE TABLE IF NOT EXISTS recipe_cookbooks (
        recipe_id INTEGER NOT NULL, cookbook_id INTEGER NOT NULL,
        UNIQUE(recipe_id,cookbook_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE)""")
    con.execute("""CREATE TABLE IF NOT EXISTS recipe_tags (
        recipe_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        UNIQUE(recipe_id, tag_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS recipe_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT '',
        is_cover INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT '',
        UNIQUE(recipe_id, filename))""")
    con.execute("""CREATE TABLE IF NOT EXISTS ingredient_state (
        recipe_id INTEGER NOT NULL,
        ingredient TEXT NOT NULL,
        checked INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(recipe_id, ingredient))""")
    # Existing single recipe image becomes the first gallery/cover image.
    for rr in con.execute("SELECT id,image,image_source FROM recipes WHERE image IS NOT NULL AND image!=''").fetchall():
        exists=con.execute("SELECT 1 FROM recipe_images WHERE recipe_id=? AND filename=?",(rr["id"],rr["image"])).fetchone()
        if not exists:
            con.execute("INSERT OR IGNORE INTO recipe_images(recipe_id,filename,source,is_cover,created_at) VALUES(?,?,?,?,?)",
                        (rr["id"],rr["image"],rr["image_source"] or "",1,datetime.now().isoformat()))
    tag_cols={x["name"] for x in con.execute("PRAGMA table_info(tags)").fetchall()}
    if "color" not in tag_cols:
        con.execute("ALTER TABLE tags ADD COLUMN color TEXT NOT NULL DEFAULT '#5b7cfa'")
    for row in con.execute("SELECT id,book FROM recipes WHERE TRIM(COALESCE(book,'')) != ''").fetchall():
        name=row["book"].strip()
        con.execute("INSERT OR IGNORE INTO cookbooks(name) VALUES(?)",(name,))
        cb=con.execute("SELECT id FROM cookbooks WHERE name=? COLLATE NOCASE",(name,)).fetchone()
        if cb: con.execute("INSERT OR IGNORE INTO recipe_cookbooks VALUES(?,?)",(row["id"],cb["id"]))
    con.commit(); con.close()

init_db()

def safe_date(iso):
    try: return datetime.fromisoformat(iso).strftime("%d.%m.%Y")
    except: return iso or ""

def monday_for(d): return d - timedelta(days=d.weekday())

def safe_book_color(v):
    v=(v or "").strip().lower()
    return v if v in BOOK_COLORS else BOOK_COLORS[0]

def safe_tag_color(v):
    v=(v or "").strip().lower()
    return v if v in TAG_COLORS else TAG_COLORS[0]

TAG_COLORS_EXT=["#5b7cfa","#e85d75","#e49b0f","#35a36f","#8b5cf6","#0f9fb5","#d66a1f","#64748b","#ec4899","#14b8a6","#f97316","#84cc16","#06b6d4","#6366f1","#a855f7","#ef4444","#22c55e","#f59e0b","#0ea5e9","#78716c"]
TAG_COLORS=TAG_COLORS_EXT
BOOK_COLORS=["#6f5bd3","#d35d7f","#2f8f83","#d18936","#4d78c8","#a05aa8","#6a7f43","#a65d4d","#566272","#a17b45"]
SETTINGS_FILE=Path("/data/settings.json")
OPENAI_API_BASE="https://api.openai.com/v1"

def load_settings():
    defaults={
        "provider":"openai",
        "api_key":"",
        "text_model":"gpt-5",
        "image_model":"gpt-image-1",
        "image_quality":"medium",
        "auto_ai_image":False,
        "bring_entity":""
    }
    try:
        if SETTINGS_FILE.exists():
            data=json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            defaults.update({k:v for k,v in data.items() if k in defaults})
    except Exception:
        pass
    return defaults

def save_settings(data):
    SETTINGS_FILE.parent.mkdir(parents=True,exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    try:
        SETTINGS_FILE.chmod(0o600)
    except Exception:
        pass

def masked_key(value):
    if not value: return "Nicht eingerichtet"
    if len(value)<10: return "••••••••"
    return value[:5]+"••••••••"+value[-4:]

def openai_json(path,payload,timeout=90):
    settings=load_settings()
    key=settings.get("api_key","").strip()
    if not key:
        raise ValueError("OpenAI API-Schlüssel fehlt. Bitte zuerst unter Einstellungen → KI eintragen.")
    body=json.dumps(payload).encode("utf-8")
    req=Request(OPENAI_API_BASE+path,data=body,method="POST",headers={
        "Authorization":"Bearer "+key,
        "Content-Type":"application/json",
        "User-Agent":"Meine-Rezepte/0.4.0"
    })
    try:
        with urlopen(req,timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail=json.loads(exc.read().decode("utf-8")).get("error",{}).get("message","")
        except Exception:
            detail=""
        raise ValueError("OpenAI-Fehler: "+(detail or f"HTTP {exc.code}"))
    except URLError as exc:
        raise ValueError("OpenAI ist nicht erreichbar: "+str(exc.reason))

def response_text(data):
    # Raw Responses API parser; SDK-only output_text is not assumed.
    texts=[]
    for item in data.get("output",[]) or []:
        for content in item.get("content",[]) or []:
            if content.get("type") in ("output_text","text") and content.get("text"):
                texts.append(content["text"])
    if texts:
        return "\n".join(texts)
    return str(data.get("output_text") or "")

def parse_json_text(text):
    text=(text or "").strip()
    text=re.sub(r"^```(?:json)?\s*|\s*```$","",text,flags=re.I|re.S).strip()
    try:
        return json.loads(text)
    except Exception:
        hit=re.search(r"\{.*\}",text,re.S)
        if hit:
            return json.loads(hit.group(0))
        raise ValueError("Die KI-Antwort konnte nicht als Rezept gelesen werden.")

def normalize_scan_image(file):
    """
    Normalize camera/photo-library images before sending to AI.
    Returns (data_url, saved_filename).
    """
    raw=file.read()
    if not raw:
        raise ValueError("Das ausgewählte Bild ist leer.")
    if len(raw)>15*1024*1024:
        raise ValueError("Das Bild ist zu groß (max. 15 MB).")

    try:
        img=Image.open(io.BytesIO(raw))
        img=ImageOps.exif_transpose(img)
        img.load()
    except Exception:
        raise ValueError(
            "Das Bildformat konnte nicht gelesen werden. "
            "Bitte auf dem iPhone ein JPEG/PNG auswählen oder das Foto als Screenshot speichern."
        )

    # Reduce extremely large camera images for faster / cheaper vision requests.
    img.thumbnail((2400,2400))
    if img.mode not in ("RGB","L"):
        background=Image.new("RGB",img.size,"white")
        if "A" in img.getbands():
            background.paste(img,mask=img.getchannel("A"))
        else:
            background.paste(img)
        img=background
    elif img.mode=="L":
        img=img.convert("RGB")

    buffer=io.BytesIO()
    img.save(buffer,format="JPEG",quality=88,optimize=True)
    normalized=buffer.getvalue()

    filename=f"scan_{uuid.uuid4().hex}.jpg"
    (IMG_DIR/filename).write_bytes(normalized)

    return "data:image/jpeg;base64,"+base64.b64encode(normalized).decode("ascii"), filename

def file_to_data_url(file):
    # kept for compatibility with any older call sites
    data_url,_=normalize_scan_image(file)
    return data_url


def ai_scan_recipe(file):
    settings=load_settings()
    data_url,scan_image=normalize_scan_image(file)
    prompt="""Lies dieses fotografierte oder gescannte Rezept. Gib ausschließlich valides JSON zurück:
{
 "title": "Rezeptname",
 "ingredients": ["eine Zutat pro Eintrag; Abschnittsüberschriften als **Für ...** eigener Eintrag"],
 "steps": ["ein vollständiger Arbeitsschritt pro Eintrag"],
 "servings": "Portionsangabe oder leer",
 "prep_minutes": Zahl oder 0,
 "cook_minutes": Zahl oder 0,
 "total_minutes": Zahl oder 0,
 "calories_total": Zahl oder 0,
 "calories_serving": Zahl oder 0,
 "protein_g": Zahl oder 0,
 "carbs_g": Zahl oder 0,
 "fat_g": Zahl oder 0,
 "fiber_g": Zahl oder 0
}
Übernimm Mengen und Einheiten möglichst exakt. Wenn die Zutaten im Original gruppiert sind, erhalte diese Gruppen mit Überschriften wie **Für das Dressing** als eigene Zeile. Entferne Werbung, Seitenköpfe, Bildunterschriften und sonstigen Zeitungstext. Erfinde keine fehlenden Angaben."""
    payload={
        "model":settings.get("text_model") or "gpt-5",
        "input":[{
            "role":"user",
            "content":[
                {"type":"input_text","text":prompt},
                {"type":"input_image","image_url":data_url,"detail":"high"}
            ]
        }]
    }
    result=openai_json("/responses",payload,timeout=120)
    obj=parse_json_text(response_text(result))
    return {
        "title":str(obj.get("title","")).strip(),
        "ingredients":[str(x).strip() for x in obj.get("ingredients",[]) if str(x).strip()],
        "steps":[str(x).strip() for x in obj.get("steps",[]) if str(x).strip()],
        "servings":str(obj.get("servings","")).strip(),
        "prep_minutes":int(obj.get("prep_minutes",0) or 0),
        "cook_minutes":int(obj.get("cook_minutes",0) or 0),
        "total_minutes":int(obj.get("total_minutes",0) or 0),
        "calories_total":float(obj.get("calories_total",0) or 0),
        "calories_serving":float(obj.get("calories_serving",0) or 0),
        "protein_g":float(obj.get("protein_g",0) or 0),
        "carbs_g":float(obj.get("carbs_g",0) or 0),
        "fat_g":float(obj.get("fat_g",0) or 0),
        "fiber_g":float(obj.get("fiber_g",0) or 0),
        "scan_image":scan_image
    }

def ai_generate_image(prompt, prefix="ai"):
    settings=load_settings()
    payload={
        "model":settings.get("image_model") or "gpt-image-1",
        "prompt":prompt,
        "size":"1024x1024",
        "quality":settings.get("image_quality") or "medium",
        "output_format":"jpeg"
    }
    result=openai_json("/images/generations",payload,timeout=180)
    items=result.get("data") or []
    if not items or not items[0].get("b64_json"):
        raise ValueError("Die Bild-KI hat kein Bild zurückgegeben.")
    raw=base64.b64decode(items[0]["b64_json"])
    name=f"{prefix}_{uuid.uuid4().hex}.jpg"
    (IMG_DIR/name).write_bytes(raw)
    return name

def add_recipe_gallery_image(con,rid,filename,source=""):
    has_cover=con.execute("SELECT 1 FROM recipe_images WHERE recipe_id=? AND is_cover=1",(rid,)).fetchone()
    con.execute("INSERT OR IGNORE INTO recipe_images(recipe_id,filename,source,is_cover,created_at) VALUES(?,?,?,?,?)",
                (rid,filename,source,0 if has_cover else 1,datetime.now().isoformat()))
    if not has_cover:
        con.execute("UPDATE recipes SET image=?,image_source=? WHERE id=?",(filename,source,rid))
    con.commit()

def recipe_image_prompt(recipe):
    ingredients=", ".join([x.strip() for x in (recipe["ingredients"] or "").splitlines() if x.strip()][:12])
    return f"""Erzeuge ein appetitliches, realistisches Food-Foto für das Rezept „{recipe['title']}“.
Wichtige Zutaten: {ingredients}.
Fotografischer Stil: natürliches Tageslicht, moderne Food-Fotografie, realistisches angerichtetes Gericht, keine Schrift, keine Logos, keine Personen, quadratisches Bild."""

def cookbook_cover_prompt(name):
    return f"""Gestalte ein hochwertiges quadratisches Kochbuch-Cover für „{name}“.
Stil: moderne Editorial-Food-Fotografie mit passenden kulinarischen Motiven, elegant, warm, hochwertig.
Keine lesbare Schrift, keine Logos, keine Personen. Das Bild soll als Kochbuchcover funktionieren."""

def int_form(name, default=0):
    try:
        return max(0,int(request.form.get(name,default) or default))
    except Exception:
        return default

def float_form(name, default=0):
    try:
        return max(0,float(str(request.form.get(name,default) or default).replace(",", ".")))
    except Exception:
        return default

def iso_duration_minutes(value):
    """Parse simple ISO-8601 durations such as PT15M, PT1H30M."""
    if not value:
        return 0
    if isinstance(value,(int,float)):
        return int(value)
    text=str(value).strip().upper()
    m=re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?",text)
    if not m:
        return 0
    days=int(m.group(1) or 0); hours=int(m.group(2) or 0); mins=int(m.group(3) or 0)
    secs=int(m.group(4) or 0)
    return days*1440+hours*60+mins+(1 if secs>=30 else 0)

def servings_count(value):
    text=str(value or "").strip().replace(",", ".")
    hit=re.search(r"(\d+(?:\.\d+)?)",text)
    if not hit:
        return 0
    try:
        num=float(hit.group(1))
        return int(num) if num.is_integer() else num
    except Exception:
        return 0

def ingredient_groups(text):
    groups=[]
    current={"title":"","items":[]}

    def push():
        nonlocal current
        if current["title"] or current["items"]:
            groups.append(current)
        current={"title":"","items":[]}

    for raw in (text or "").splitlines():
        line=raw.strip()
        if not line:
            continue
        if re.fullmatch(r"-{3,}",line):
            continue

        title=""
        bold=re.fullmatch(r"\*\*(.+?)\*\*",line)
        heading=re.fullmatch(r"#{1,3}\s+(.+)",line)
        bracket=re.fullmatch(r"\[(.+?)\]",line)

        if bold:
            title=bold.group(1).strip()
        elif heading:
            title=heading.group(1).strip()
        elif bracket:
            title=bracket.group(1).strip()

        if title:
            push()
            current={"title":title,"items":[]}
        else:
            current["items"].append(line)

    push()
    if not groups:
        groups=[{"title":"","items":[]}]
    return groups

def human_minutes(value):
    try: value=int(value or 0)
    except: value=0
    if value<=0: return ""
    h,m=divmod(value,60)
    if h and m: return f"{h} Std. {m} Min."
    if h: return f"{h} Std."
    return f"{m} Min."


app.jinja_env.globals["human_minutes"]=human_minutes
app.jinja_env.globals["ingredient_groups"]=ingredient_groups

def ha_api(path, payload=None, method="GET", timeout=30):
    token=os.environ.get("SUPERVISOR_TOKEN","")
    if not token:
        raise ValueError("Home-Assistant-API ist für diese App nicht verfügbar.")
    data=None if payload is None else json.dumps(payload).encode("utf-8")
    req=Request("http://supervisor/core/api"+path,data=data,method=method,headers={
        "Authorization":"Bearer "+token,
        "Content-Type":"application/json"
    })
    try:
        with urlopen(req,timeout=timeout) as response:
            raw=response.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        try: detail=exc.read().decode("utf-8")
        except: detail=""
        raise ValueError(f"Home Assistant API-Fehler {exc.code}: {detail[:250]}")

def ha_connection_diagnostics():
    info={
        "token_present":bool(os.environ.get("SUPERVISOR_TOKEN","")),
        "api_ok":False,
        "todo_count":0,
        "error":""
    }
    try:
        states=ha_api("/states")
        info["api_ok"]=True
        info["todo_count"]=len([x for x in states if str(x.get("entity_id","")).startswith("todo.")])
    except Exception as exc:
        info["error"]=str(exc)
    return info

def ha_todo_entities():
    """
    Return writable Home Assistant to-do entities.

    Home Assistant's /states response does not reliably expose the source
    integration for a to-do entity. Bring lists can therefore be named simply
    "Einkaufsliste" without the word "bring". Prefer entities that can be
    identified as Bring, but fall back to all writable to-do entities rather
    than hiding valid Bring lists.
    """
    try:
        states=ha_api("/states")
        writable=[]
        bring=[]

        for x in states:
            entity_id=str(x.get("entity_id",""))
            if not entity_id.startswith("todo."):
                continue

            attrs=x.get("attributes",{}) or {}
            supported=attrs.get("supported_features")
            try:
                supported=int(supported) if supported is not None else None
            except Exception:
                supported=None

            # CREATE_TODO_ITEM is feature bit 1.
            if supported is not None and not (supported & 1):
                continue

            name=str(attrs.get("friendly_name") or entity_id)
            row={"entity_id":entity_id,"name":name}
            writable.append(row)

            marker=" ".join([
                entity_id,
                name,
                str(attrs.get("integration","")),
                str(attrs.get("platform","")),
                str(attrs.get("attribution",""))
            ]).lower()

            if "bring" in marker:
                bring.append(row)

        rows=bring if bring else writable
        # Remove duplicates and sort.
        unique={x["entity_id"]:x for x in rows}
        return sorted(unique.values(),key=lambda x:x["name"].lower())

    except Exception:
        return []


def bring_add_items(entity_id, ingredients):
    entity_id=(entity_id or "").strip()
    if not entity_id.startswith("todo."):
        raise ValueError("Bitte eine gültige Einkaufsliste auswählen.")

    items=[x.strip() for x in ingredients if x.strip()]
    if not items:
        raise ValueError("Dieses Rezept enthält keine ausgewählten Zutaten.")

    failures=[]
    added=0

    for item in items:
        try:
            # REST /api/services/<domain>/<service> expects service_data directly.
            ha_api("/services/todo/add_item",{
                "entity_id":entity_id,
                "item":item
            },"POST",20)
            added+=1
        except Exception as exc:
            failures.append(f"{item}: {exc}")

    if failures:
        first=failures[0]
        if added:
            raise ValueError(
                f"{added} Zutaten wurden übertragen, {len(failures)} nicht. "
                f"Erster Fehler: {first}"
            )
        raise ValueError(
            f"Keine Zutat konnte übertragen werden. Home Assistant meldet: {first}"
        )

    return added


def ai_calculate_nutrition(recipe):
    settings=load_settings()
    prompt=f"""Schätze die Nährwerte für dieses Rezept sachlich und plausibel.
Titel: {recipe['title']}
Portionen: {recipe['servings'] or 'nicht angegeben'}
Zutaten:
{recipe['ingredients']}

Gib ausschließlich valides JSON zurück:
{{
 "calories_total": Zahl,
 "calories_serving": Zahl,
 "protein_g": Zahl pro Portion,
 "carbs_g": Zahl pro Portion,
 "fat_g": Zahl pro Portion,
 "fiber_g": Zahl pro Portion
}}
Wenn Portionszahl fehlt, schätze eine sinnvolle Portionszahl nur zur Berechnung.
Die Werte sind Näherungen, keine medizinischen Angaben."""
    result=openai_json("/responses",{
        "model":settings.get("text_model") or "gpt-5",
        "input":prompt
    },timeout=90)
    obj=parse_json_text(response_text(result))
    def n(k):
        try:return round(float(obj.get(k,0) or 0),1)
        except:return 0
    return {k:n(k) for k in ["calories_total","calories_serving","protein_g","carbs_g","fat_g","fiber_g"]}

def form_steps():
    """Zubereitungsschritte aus dynamischen Formularfeldern normalisieren."""
    steps = request.form.getlist("steps[]")
    if not steps:
        legacy = request.form.get("steps", "")
        steps = legacy.splitlines()
    return "\n".join(s.strip() for s in steps if s and s.strip())

def split_steps(text):
    """Gespeicherten Zeilentext als Liste für die Oberfläche liefern."""
    return [s.strip() for s in (text or "").splitlines() if s.strip()]


def save_image(file):
    if not file or not file.filename: return None
    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in {".jpg",".jpeg",".png",".webp",".heic",".heif"}: ext = ".jpg"
    name = uuid.uuid4().hex + ".jpg"
    path = IMG_DIR / name
    im = Image.open(file.stream)
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((1600,1600))
    im.save(path, "JPEG", quality=84, optimize=True)
    return name

def delete_image(name):
    if name:
        p = IMG_DIR / Path(name).name
        if p.exists(): p.unlink()

@app.route("/images/<name>")
def images(name):
    return send_from_directory(IMG_DIR, Path(name).name)

@app.route("/", methods=["GET","POST"])
def index():
    view = request.args.get("view","")
    routes = {
        "new": recipe_add_menu, "create": new_recipe, "pdf_import": pdf_import, "recipe": recipe_detail, "edit": edit_recipe,
        "delete": delete_recipe, "note": add_note, "cook": cook_mode,
        "books": books, "book": book_detail, "book_new": book_new, "book_rename": book_rename, "book_delete": book_delete, "book_cover": book_cover, "tags": tags, "tag_new": tag_new, "tag_rename": tag_rename, "tag_delete": tag_delete, "settings": settings_page, "scan": scan_recipe, "ai_image": recipe_ai_image, "nutrition": recipe_nutrition, "bring": recipe_bring, "ingredient_toggle": ingredient_toggle, "own_images": recipe_own_images, "image_cover": recipe_image_cover, "image_delete": recipe_image_delete, "week": week_plan, "import": import_recipe,
    }
    return routes[view]() if view in routes else recipe_list()

def recipe_add_menu():
    return render_template("add_recipe.html")

def pdf_import():
    preview=None
    error=""

    if request.method=="POST":
        action=request.form.get("action","scan")

        if action=="scan":
            file=request.files.get("pdf_file")
            if not file or not file.filename:
                error="Bitte eine PDF-Datei auswählen."
            else:
                try:
                    preview=ai_import_pdf(file)
                except Exception as exc:
                    error=str(exc)

        elif action=="save":
            title=request.form.get("title","").strip()
            if not title:
                error="Bitte einen Rezeptnamen eingeben."
            else:
                con=db()
                cur=con.execute("""INSERT INTO recipes
                    (title,ingredients,steps,book,created_at,image,image_source,source_url,source_name,
                     servings,prep_minutes,cook_minutes,total_minutes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (title,request.form.get("ingredients","").strip(),form_steps(),"",
                     datetime.now().isoformat(),"","","","PDF-Import",
                     request.form.get("servings","").strip(),int_form("prep_minutes"),
                     int_form("cook_minutes"),int_form("total_minutes")))
                rid=cur.lastrowid

                for cid in request.form.getlist("cookbooks"):
                    con.execute("INSERT OR IGNORE INTO recipe_cookbooks VALUES(?,?)",(rid,int(cid)))
                for tid in request.form.getlist("tags"):
                    con.execute("INSERT OR IGNORE INTO recipe_tags VALUES(?,?)",(rid,int(tid)))

                con.commit()
                con.close()
                return redirect(f"?view=recipe&id={rid}")

    con=db()
    cookbooks=con.execute("SELECT * FROM cookbooks ORDER BY name COLLATE NOCASE").fetchall()
    tags=con.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
    con.close()
    return render_template("pdf_import.html",preview=preview,error=error,
                           cookbooks=cookbooks,tags=tags)


def recipe_list():
    q=request.args.get("q","").strip()
    selected_tags=[int(x) for x in request.args.getlist("tag") if str(x).isdigit()]
    con=db()
    params=[]; where=[]
    if q:
        like=f"%{q}%"
        where.append("""(r.title LIKE ? COLLATE NOCASE OR r.ingredients LIKE ? COLLATE NOCASE
        OR r.steps LIKE ? COLLATE NOCASE OR c.name LIKE ? COLLATE NOCASE
        OR n.note LIKE ? COLLATE NOCASE OR t.name LIKE ? COLLATE NOCASE)""")
        params += [like]*6
    if selected_tags:
        ph=",".join("?" for _ in selected_tags)
        where.append(f"""r.id IN (
            SELECT recipe_id FROM recipe_tags WHERE tag_id IN ({ph})
            GROUP BY recipe_id HAVING COUNT(DISTINCT tag_id)=?
        )""")
        params += selected_tags + [len(selected_tags)]
    sql="""SELECT DISTINCT r.* FROM recipes r
      LEFT JOIN recipe_cookbooks rc ON rc.recipe_id=r.id
      LEFT JOIN cookbooks c ON c.id=rc.cookbook_id
      LEFT JOIN notes n ON n.recipe_id=r.id
      LEFT JOIN recipe_tags rx ON rx.recipe_id=r.id
      LEFT JOIN tags t ON t.id=rx.tag_id"""
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.created_at DESC"
    rows=con.execute(sql,tuple(params)).fetchall()
    recipe_tags_by_id={}
    for tr in con.execute("""SELECT rt.recipe_id,t.name,t.color
        FROM recipe_tags rt JOIN tags t ON t.id=rt.tag_id
        ORDER BY t.name COLLATE NOCASE""").fetchall():
        recipe_tags_by_id.setdefault(tr["recipe_id"],[]).append(tr)
    tags=con.execute("""SELECT t.*,COUNT(rt.recipe_id) count FROM tags t
      LEFT JOIN recipe_tags rt ON rt.tag_id=t.id
      GROUP BY t.id ORDER BY t.name COLLATE NOCASE""").fetchall()
    con.close()
    return render_template("recipes.html",recipes=rows,safe_date=safe_date,title="Alle Rezepte",
                           q=q,tags=tags,selected_tags=selected_tags,recipe_tags_by_id=recipe_tags_by_id)

def new_recipe():
    if request.method=="POST":
        title=request.form.get("title","").strip()
        if title:
            con=db()
            cur=con.execute("""INSERT INTO recipes
                (title,ingredients,steps,book,created_at,image,image_source,source_url,source_name,
                 servings,prep_minutes,cook_minutes,total_minutes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (title,request.form.get("ingredients","").strip(),form_steps(),"",
                 datetime.now().isoformat(),"","",
                 request.form.get("source_url","").strip(),request.form.get("source_name","").strip(),
                 request.form.get("servings","").strip(),
                 int_form("prep_minutes"),int_form("cook_minutes"),int_form("total_minutes")))
            rid=cur.lastrowid
            for cid in request.form.getlist("cookbooks"):
                con.execute("INSERT OR IGNORE INTO recipe_cookbooks VALUES(?,?)",(rid,int(cid)))
            for tid in request.form.getlist("tags"):
                con.execute("INSERT OR IGNORE INTO recipe_tags VALUES(?,?)",(rid,int(tid)))
            for uploaded in request.files.getlist("images"):
                if uploaded and uploaded.filename:
                    filename=save_image(uploaded)
                    if filename:add_recipe_gallery_image(con,rid,filename,"upload")
            con.commit(); con.close()
            return redirect(f"?view=recipe&id={rid}")
    con=db()
    cookbooks=con.execute("SELECT * FROM cookbooks ORDER BY name COLLATE NOCASE").fetchall()
    tags=con.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
    con.close()
    return render_template("edit.html",recipe=None,cookbooks=cookbooks,selected_cookbooks=set(),
        tags=tags,selected_tags=set(),steps=[],gallery=[])


def recipe_detail():
    rid=request.args.get("id",type=int); con=db()
    ensure_ingredient_state_table(con)
    r=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
    if not r:
        con.close()
        return redirect("./")
    notes=con.execute("SELECT * FROM notes WHERE recipe_id=? ORDER BY cooked_at DESC,id DESC",(rid,)).fetchall()
    cookbook_names=[x["name"] for x in con.execute("""SELECT c.name FROM cookbooks c
        JOIN recipe_cookbooks rc ON rc.cookbook_id=c.id
        WHERE rc.recipe_id=? ORDER BY c.name COLLATE NOCASE""",(rid,)).fetchall()]
    recipe_tags=con.execute("""SELECT t.name,t.color FROM tags t
        JOIN recipe_tags rt ON rt.tag_id=t.id
        WHERE rt.recipe_id=? ORDER BY t.name COLLATE NOCASE""",(rid,)).fetchall()
    gallery=con.execute("""SELECT * FROM recipe_images
        WHERE recipe_id=? ORDER BY is_cover DESC,id DESC""",(rid,)).fetchall()
    ingredient_sections=ingredient_groups(r["ingredients"] or "")
    base_servings=servings_count(r["servings"] or "")
    checked_ingredients={x["ingredient"] for x in con.execute(
        "SELECT ingredient FROM ingredient_state WHERE recipe_id=? AND checked=1",(rid,)).fetchall()}
    con.close()
    return render_template("recipe.html",recipe=r,notes=notes,safe_date=safe_date,
        cookbook_names=cookbook_names,tag_names=[x["name"] for x in recipe_tags],
        recipe_tags=recipe_tags,gallery=gallery,ingredient_sections=ingredient_sections,checked_ingredients=checked_ingredients,base_servings=base_servings)

def edit_recipe():
    rid=request.args.get("id",type=int)
    con=db()
    r=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
    if not r:
        con.close()
        return redirect("./")

    if request.method=="POST":
        con.execute("""UPDATE recipes SET title=?,ingredients=?,steps=?,book='',
            source_url=?,source_name=?,servings=?,prep_minutes=?,cook_minutes=?,total_minutes=?,
            calories_total=?,calories_serving=?,protein_g=?,carbs_g=?,fat_g=?,fiber_g=?
            WHERE id=?""",
            (request.form.get("title","").strip(),
             request.form.get("ingredients","").strip(),
             form_steps(),
             request.form.get("source_url","").strip(),
             request.form.get("source_name","").strip(),
             request.form.get("servings","").strip(),
             int_form("prep_minutes"),int_form("cook_minutes"),int_form("total_minutes"),
             float_form("calories_total"),float_form("calories_serving"),
             float_form("protein_g"),float_form("carbs_g"),float_form("fat_g"),float_form("fiber_g"),
             rid))

        con.execute("DELETE FROM recipe_cookbooks WHERE recipe_id=?",(rid,))
        for cid in request.form.getlist("cookbooks"):
            con.execute("INSERT OR IGNORE INTO recipe_cookbooks VALUES(?,?)",(rid,int(cid)))

        con.execute("DELETE FROM recipe_tags WHERE recipe_id=?",(rid,))
        for tid in request.form.getlist("tags"):
            con.execute("INSERT OR IGNORE INTO recipe_tags VALUES(?,?)",(rid,int(tid)))

        # Eigene Bilder ergänzen; vorhandene Galerie bleibt erhalten.
        uploads=request.files.getlist("images")
        for uploaded in uploads:
            if uploaded and uploaded.filename:
                filename=save_image(uploaded)
                if filename:
                    add_recipe_gallery_image(con,rid,filename,"upload")

        con.commit()
        con.close()
        return redirect(f"?view=recipe&id={rid}")

    cookbooks=con.execute("SELECT * FROM cookbooks ORDER BY name COLLATE NOCASE").fetchall()
    selected_cookbooks={x["cookbook_id"] for x in con.execute(
        "SELECT cookbook_id FROM recipe_cookbooks WHERE recipe_id=?",(rid,)).fetchall()}
    tags=con.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
    selected_tags={x["tag_id"] for x in con.execute(
        "SELECT tag_id FROM recipe_tags WHERE recipe_id=?",(rid,)).fetchall()}
    gallery=con.execute("""SELECT * FROM recipe_images
        WHERE recipe_id=? ORDER BY is_cover DESC,id DESC""",(rid,)).fetchall()
    con.close()

    return render_template("edit.html",recipe=r,cookbooks=cookbooks,
        selected_cookbooks=selected_cookbooks,tags=tags,selected_tags=selected_tags,
        steps=split_steps(r["steps"]),gallery=gallery)


def delete_recipe():
    rid=request.args.get("id",type=int); con=db()
    r=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
    if not r: con.close(); return redirect("./")
    if request.method=="POST":
        delete_image(r["image"])
        con.execute("DELETE FROM notes WHERE recipe_id=?",(rid,))
        con.execute("DELETE FROM meal_plan WHERE recipe_id=?",(rid,))
        con.execute("DELETE FROM recipe_cookbooks WHERE recipe_id=?",(rid,))
        con.execute("DELETE FROM recipes WHERE id=?",(rid,))
        con.commit(); con.close(); return redirect("./")
    con.close(); return render_template("delete.html",recipe=r)

def add_note():
    rid=request.args.get("id",type=int)
    if request.method=="POST":
        con=db(); con.execute("""INSERT INTO notes(recipe_id,note,rating,cooked_at)
            VALUES(?,?,?,?)""",(rid,request.form.get("note","").strip(),
            request.form.get("rating",type=int) or 0,datetime.now().isoformat()))
        con.commit(); con.close()
    return redirect(f"?view=recipe&id={rid}")

def books():
    con=db()
    rows=con.execute("""SELECT c.id,c.name,c.color,c.cover,COUNT(rc.recipe_id) count
        FROM cookbooks c
        LEFT JOIN recipe_cookbooks rc ON rc.cookbook_id=c.id
        GROUP BY c.id,c.name,c.color,c.cover
        ORDER BY c.name COLLATE NOCASE""").fetchall()
    con.close()
    return render_template("books.html",books=rows)


def book_new():
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if name:
            con=db(); con.execute("INSERT OR IGNORE INTO cookbooks(name,color) VALUES(?,?)",(name,safe_book_color(request.form.get("color")))); con.commit(); con.close()
        return redirect("?view=books")
    return render_template("book_form.html",mode="new",cookbook=None)

def book_rename():
    cid=request.args.get("id",type=int); con=db(); cb=con.execute("SELECT * FROM cookbooks WHERE id=?",(cid,)).fetchone()
    if not cb: con.close(); return redirect("?view=books")
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if name:
            try: con.execute("UPDATE cookbooks SET name=?,color=? WHERE id=?",(name,safe_book_color(request.form.get("color")),cid)); con.commit()
            except sqlite3.IntegrityError: pass
        con.close(); return redirect("?view=books")
    con.close(); return render_template("book_form.html",mode="rename",cookbook=cb)

def book_delete():
    cid=request.args.get("id",type=int); con=db(); cb=con.execute("SELECT * FROM cookbooks WHERE id=?",(cid,)).fetchone()
    if not cb: con.close(); return redirect("?view=books")
    if request.method=="POST":
        con.execute("DELETE FROM recipe_cookbooks WHERE cookbook_id=?",(cid,)); con.execute("DELETE FROM cookbooks WHERE id=?",(cid,))
        con.commit(); con.close(); return redirect("?view=books")
    con.close(); return render_template("book_delete.html",cookbook=cb)

def book_detail():
    cid=request.args.get("id",type=int)
    con=db()
    cb=con.execute("SELECT * FROM cookbooks WHERE id=?",(cid,)).fetchone()
    if not cb:
        con.close()
        return redirect("?view=books")

    rows=con.execute("""SELECT r.* FROM recipes r
        JOIN recipe_cookbooks rc ON rc.recipe_id=r.id
        WHERE rc.cookbook_id=?
        ORDER BY r.title COLLATE NOCASE""",(cid,)).fetchall()

    recipe_ids=[r["id"] for r in rows]
    recipe_tags_by_id={}
    if recipe_ids:
        ph=",".join("?" for _ in recipe_ids)
        tag_rows=con.execute(f"""SELECT rt.recipe_id,t.name,t.color
            FROM recipe_tags rt
            JOIN tags t ON t.id=rt.tag_id
            WHERE rt.recipe_id IN ({ph})
            ORDER BY t.name COLLATE NOCASE""",tuple(recipe_ids)).fetchall()
        for tr in tag_rows:
            recipe_tags_by_id.setdefault(tr["recipe_id"],[]).append(tr)

    tags=con.execute("""SELECT t.*,COUNT(rt.recipe_id) count
        FROM tags t LEFT JOIN recipe_tags rt ON rt.tag_id=t.id
        GROUP BY t.id ORDER BY t.name COLLATE NOCASE""").fetchall()
    con.close()

    return render_template("recipes.html",
        recipes=rows,
        safe_date=safe_date,
        title="📚 "+cb["name"],
        q="",
        tags=tags,
        selected_tags=[],
        recipe_tags_by_id=recipe_tags_by_id,
        cookbook=cb)


def tags():
    con=db()
    rows=con.execute("""SELECT t.id,t.name,COUNT(rt.recipe_id) count FROM tags t
      LEFT JOIN recipe_tags rt ON rt.tag_id=t.id GROUP BY t.id ORDER BY t.name COLLATE NOCASE""").fetchall()
    con.close()
    return render_template("tags.html",tags=rows)

def tag_new():
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if name:
            con=db(); con.execute("INSERT OR IGNORE INTO tags(name,color) VALUES(?,?)",(name,safe_tag_color(request.form.get("color")))); con.commit(); con.close()
        return redirect("?view=tags")
    return render_template("tag_form.html",mode="new",tag=None)

def tag_rename():
    tid=request.args.get("id",type=int); con=db()
    tag=con.execute("SELECT * FROM tags WHERE id=?",(tid,)).fetchone()
    if not tag: con.close(); return redirect("?view=tags")
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if name:
            try: con.execute("UPDATE tags SET name=?,color=? WHERE id=?",(name,safe_tag_color(request.form.get("color")),tid)); con.commit()
            except sqlite3.IntegrityError: pass
        con.close(); return redirect("?view=tags")
    con.close(); return render_template("tag_form.html",mode="rename",tag=tag)

def tag_delete():
    tid=request.args.get("id",type=int); con=db()
    tag=con.execute("SELECT * FROM tags WHERE id=?",(tid,)).fetchone()
    if not tag: con.close(); return redirect("?view=tags")
    if request.method=="POST":
        con.execute("DELETE FROM recipe_tags WHERE tag_id=?",(tid,))
        con.execute("DELETE FROM tags WHERE id=?",(tid,))
        con.commit(); con.close(); return redirect("?view=tags")
    con.close(); return render_template("tag_delete.html",tag=tag)

def settings_page():
    current=load_settings()
    message=""
    error=""
    if request.method=="POST":
        action=request.form.get("action","save")
        if action=="save":
            key=request.form.get("api_key","").strip()
            saved_key=current.get("api_key","")
            data={
                "provider":"openai",
                "api_key":key if key else saved_key,
                "text_model":request.form.get("text_model","gpt-5").strip() or "gpt-5",
                "image_model":request.form.get("image_model","gpt-image-1").strip() or "gpt-image-1",
                "image_quality":request.form.get("image_quality","medium") if request.form.get("image_quality","medium") in ("low","medium","high") else "medium",
                "auto_ai_image":request.form.get("auto_ai_image")=="1",
                "bring_entity":request.form.get("bring_entity","").strip()
            }
            if request.form.get("clear_key")=="1":
                data["api_key"]=""
            save_settings(data)
            current=data
            message="KI-Einstellungen gespeichert."
        elif action=="test":
            try:
                # lightweight text request
                result=openai_json("/responses",{
                    "model":current.get("text_model") or "gpt-5",
                    "input":"Antworte ausschließlich mit OK."
                },timeout=45)
                message="Verbindung erfolgreich: "+(response_text(result).strip() or "OK")
            except Exception as exc:
                error=str(exc)
    con=db()
    tag_rows=con.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
    cookbook_rows=con.execute("SELECT * FROM cookbooks ORDER BY name COLLATE NOCASE").fetchall()
    con.close()
    return render_template("settings.html",settings=current,masked_key=masked_key(current.get("api_key","")),
                           message=message,error=error,tags=tag_rows,cookbooks=cookbook_rows,
                           colors=TAG_COLORS_EXT,todo_entities=ha_todo_entities())

def scan_recipe():
    preview=None; error=""
    if request.method=="POST":
        action=request.form.get("action","scan")
        if action=="scan":
            file=request.files.get("scan_image")
            if not file or not file.filename:
                error="Bitte ein Foto oder Bild auswählen."
            else:
                try:
                    preview=ai_scan_recipe(file)
                except Exception as exc:
                    error=str(exc)
        elif action=="save":
            title=request.form.get("title","").strip()
            if not title:
                error="Bitte einen Rezeptnamen eingeben."
            else:
                con=db()
                cur=con.execute("""INSERT INTO recipes
                    (title,ingredients,steps,book,created_at,image,image_source,source_url,source_name,
                     servings,prep_minutes,cook_minutes,total_minutes,
                     calories_total,calories_serving,protein_g,carbs_g,fat_g,fiber_g)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (title,request.form.get("ingredients","").strip(),form_steps(),"",
                     datetime.now().isoformat(),"","","","KI-Scan",
                     request.form.get("servings","").strip(),int_form("prep_minutes"),
                     int_form("cook_minutes"),int_form("total_minutes"),
                     float_form("calories_total"),float_form("calories_serving"),
                     float_form("protein_g"),float_form("carbs_g"),float_form("fat_g"),float_form("fiber_g")))
                rid=cur.lastrowid
                for cid in request.form.getlist("cookbooks"):
                    con.execute("INSERT OR IGNORE INTO recipe_cookbooks VALUES(?,?)",(rid,int(cid)))
                for tid in request.form.getlist("tags"):
                    con.execute("INSERT OR IGNORE INTO recipe_tags VALUES(?,?)",(rid,int(tid)))
                scan_image=Path(request.form.get("scan_image","")).name
                if scan_image and (IMG_DIR/scan_image).exists():
                    add_recipe_gallery_image(con,rid,scan_image,"scan")
                con.commit()
                auto=load_settings().get("auto_ai_image")
                if auto:
                    recipe=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
                    try:
                        image=ai_generate_image(recipe_image_prompt(recipe),"recipe")
                        con.execute("UPDATE recipes SET image=?,image_source='ai' WHERE id=?",(image,rid))
                        con.commit()
                    except Exception:
                        pass
                con.close()
                return redirect(f"?view=recipe&id={rid}")
    con=db()
    cookbooks=con.execute("SELECT * FROM cookbooks ORDER BY name COLLATE NOCASE").fetchall()
    tags=con.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
    con.close()
    return render_template("scan.html",preview=preview,error=error,cookbooks=cookbooks,tags=tags)

def recipe_ai_image():
    rid=request.args.get("id",type=int)
    con=db()
    recipe=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
    if not recipe:
        con.close(); return redirect("./")
    error=""
    generated=""
    if request.method=="POST":
        action=request.form.get("action","generate")
        if action=="generate":
            try:
                generated=ai_generate_image(recipe_image_prompt(recipe),"recipe")
                add_recipe_gallery_image(con,rid,generated,"ai")
            except Exception as exc:
                error=str(exc)
        elif action=="use":
            filename=Path(request.form.get("filename","")).name
            row=con.execute("SELECT id FROM recipe_images WHERE recipe_id=? AND filename=?",(rid,filename)).fetchone()
            if row and (IMG_DIR/filename).exists():
                con.execute("UPDATE recipe_images SET is_cover=0 WHERE recipe_id=?",(rid,))
                con.execute("UPDATE recipe_images SET is_cover=1 WHERE id=?",(row["id"],))
                con.execute("UPDATE recipes SET image=?,image_source='ai' WHERE id=?",(filename,rid))
                con.commit()
                con.close()
                return redirect(f"?view=recipe&id={rid}")
    con.close()
    return render_template("ai_image.html",recipe=recipe,generated=generated,error=error)

def recipe_nutrition():
    rid=request.args.get("id",type=int)
    con=db()
    recipe=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
    if not recipe:
        con.close()
        return redirect("./")

    error=""
    success=""
    if request.method=="POST":
        try:
            values=ai_calculate_nutrition(recipe)
            con.execute("""UPDATE recipes SET calories_total=?,calories_serving=?,
                protein_g=?,carbs_g=?,fat_g=?,fiber_g=?,nutrition_updated_at=?
                WHERE id=?""",
                (values["calories_total"],values["calories_serving"],
                 values["protein_g"],values["carbs_g"],values["fat_g"],values["fiber_g"],
                 datetime.now().isoformat(),rid))
            con.commit()
            recipe=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
            success="Nährwerte wurden berechnet und gespeichert."
        except Exception as exc:
            error=str(exc)

    con.close()
    return render_template("nutrition.html",recipe=recipe,error=error,success=success)


def ensure_ingredient_state_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS ingredient_state (
        recipe_id INTEGER NOT NULL,
        ingredient TEXT NOT NULL,
        checked INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(recipe_id, ingredient))""")
    con.commit()

def ingredient_toggle():
    rid=request.args.get("id",type=int)
    ingredient=request.form.get("ingredient","").strip()
    checked=1 if request.form.get("checked")=="1" else 0
    if rid and ingredient:
        con=db()
        ensure_ingredient_state_table(con)
        con.execute("""INSERT INTO ingredient_state(recipe_id,ingredient,checked)
            VALUES(?,?,?)
            ON CONFLICT(recipe_id,ingredient) DO UPDATE SET checked=excluded.checked""",
            (rid,ingredient,checked))
        con.commit(); con.close()
    return ("",204)

def recipe_bring():
    rid=request.args.get("id",type=int)
    error=""
    success=""
    recipe=None
    checked=set()

    try:
        con=db()
        ensure_ingredient_state_table(con)
        recipe=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
        if not recipe:
            con.close()
            return redirect("./")
        checked={x["ingredient"] for x in con.execute(
            "SELECT ingredient FROM ingredient_state WHERE recipe_id=? AND checked=1",(rid,)).fetchall()}
        con.close()
    except Exception as exc:
        try: con.close()
        except: pass
        return render_template("bring.html",
            recipe={"id":rid,"title":"Rezept"},
            ingredients=[],error=f"Datenbankfehler: {exc}",success="",
            todo_entities=[],selected_entity="")

    settings=load_settings()
    try:
        todo_entities=ha_todo_entities()
    except Exception as exc:
        todo_entities=[]
        error=f"Home-Assistant-Listen konnten nicht geladen werden: {exc}"

    all_ingredients=[x.strip() for x in (recipe["ingredients"] or "").splitlines()
                     if x.strip() and not re.fullmatch(r"-{3,}",x.strip())
                     and not re.fullmatch(r"\*\*(.+?)\*\*",x.strip())]
    ingredients=[x for x in all_ingredients if x not in checked]

    selected_entity=(request.form.get("bring_entity","").strip()
                     if request.method=="POST"
                     else settings.get("bring_entity","").strip())

    if request.method=="POST" and not error:
        if not selected_entity:
            error="Bitte zuerst eine Einkaufsliste auswählen."
        elif not ingredients:
            error="Alle Zutaten sind bereits als vorhanden markiert."
        else:
            try:
                count=bring_add_items(selected_entity,ingredients)
                current=load_settings()
                current["bring_entity"]=selected_entity
                save_settings(current)
                success=f"{count} Zutaten wurden zur Einkaufsliste hinzugefügt."
            except Exception as exc:
                error=str(exc)

    return render_template("bring.html",
        recipe=recipe,ingredients=ingredients,error=error,success=success,
        todo_entities=todo_entities,selected_entity=selected_entity)


def recipe_own_images():
    rid=request.args.get("id",type=int)
    con=db()
    recipe=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
    if not recipe:
        con.close()
        return redirect("./")

    error=""
    if request.method=="POST":
        uploads=request.files.getlist("images")
        added=0
        for uploaded in uploads:
            if uploaded and uploaded.filename:
                try:
                    filename=save_image(uploaded)
                    if filename:
                        add_recipe_gallery_image(con,rid,filename,"upload")
                        added+=1
                except Exception as exc:
                    error=str(exc)
        if added and not error:
            con.close()
            return redirect(f"?view=own_images&id={rid}")

    gallery=con.execute("""SELECT * FROM recipe_images
        WHERE recipe_id=? ORDER BY is_cover DESC,id DESC""",(rid,)).fetchall()
    con.close()
    return render_template("own_images.html",recipe=recipe,gallery=gallery,error=error)

def recipe_image_cover():
    rid=request.args.get("id",type=int); iid=request.args.get("image_id",type=int)
    con=db()
    img=con.execute("SELECT * FROM recipe_images WHERE id=? AND recipe_id=?",(iid,rid)).fetchone()
    if img:
        con.execute("UPDATE recipe_images SET is_cover=0 WHERE recipe_id=?",(rid,))
        con.execute("UPDATE recipe_images SET is_cover=1 WHERE id=?",(iid,))
        con.execute("UPDATE recipes SET image=?,image_source=? WHERE id=?",(img["filename"],img["source"],rid))
        con.commit()
    con.close()
    return redirect(f"?view=recipe&id={rid}")

def recipe_image_delete():
    rid=request.args.get("id",type=int); iid=request.args.get("image_id",type=int)
    con=db()
    img=con.execute("SELECT * FROM recipe_images WHERE id=? AND recipe_id=?",(iid,rid)).fetchone()
    if img:
        was_cover=bool(img["is_cover"])
        filename=img["filename"]
        con.execute("DELETE FROM recipe_images WHERE id=?",(iid,))
        replacement=None
        if was_cover:
            replacement=con.execute("SELECT * FROM recipe_images WHERE recipe_id=? ORDER BY id DESC LIMIT 1",(rid,)).fetchone()
            if replacement:
                con.execute("UPDATE recipe_images SET is_cover=1 WHERE id=?",(replacement["id"],))
                con.execute("UPDATE recipes SET image=?,image_source=? WHERE id=?",(replacement["filename"],replacement["source"],rid))
            else:
                con.execute("UPDATE recipes SET image='',image_source='' WHERE id=?",(rid,))
        con.commit()
        # only remove file if no other gallery row references it
        still=con.execute("SELECT 1 FROM recipe_images WHERE filename=?",(filename,)).fetchone()
        if not still: delete_image(filename)
    con.close()
    return redirect(f"?view=recipe&id={rid}")

def book_cover():
    cid=request.args.get("id",type=int)
    con=db()
    book=con.execute("SELECT * FROM cookbooks WHERE id=?",(cid,)).fetchone()
    if not book:
        con.close(); return redirect("?view=books")
    error=""; generated=""
    if request.method=="POST":
        action=request.form.get("action","generate")
        if action=="generate":
            try:
                generated=ai_generate_image(cookbook_cover_prompt(book["name"]),"cover")
            except Exception as exc:
                error=str(exc)
        elif action=="use":
            filename=Path(request.form.get("filename","")).name
            if filename and (IMG_DIR/filename).exists():
                old=book["cover"]
                con.execute("UPDATE cookbooks SET cover=? WHERE id=?",(filename,cid))
                con.commit()
                if old and old != filename:
                    delete_image(old)
                con.close()
                return redirect("?view=books")
    con.close()
    return render_template("book_cover.html",book=book,generated=generated,error=error)

def week_plan():
    try: current=datetime.strptime(request.args.get("week",""),"%Y-%m-%d").date()
    except: current=date.today()
    monday=monday_for(current)
    con=db()
    recipes=con.execute("SELECT id,title,image FROM recipes ORDER BY title COLLATE NOCASE").fetchall()
    plan_rows=con.execute("""SELECT m.*,r.title,r.image FROM meal_plan m LEFT JOIN recipes r ON r.id=m.recipe_id
        WHERE plan_date>=? AND plan_date<=?""",(monday.isoformat(),(monday+timedelta(days=6)).isoformat())).fetchall()
    con.close()
    plan={(r["plan_date"],r["meal"]):r for r in plan_rows}
    return render_template("week.html",monday=monday,recipes=recipes,plan=plan,today=date.today(),
        timedelta=timedelta)

@app.post("/plan/move")
def plan_move():
    data=request.get_json(force=True)
    recipe_id=int(data["recipe_id"]); target_date=data["date"]; target_meal=data["meal"]
    source_date=data.get("source_date"); source_meal=data.get("source_meal")
    con=db()
    if source_date and source_meal:
        con.execute("DELETE FROM meal_plan WHERE plan_date=? AND meal=?",(source_date,source_meal))
    con.execute("DELETE FROM meal_plan WHERE plan_date=? AND meal=?",(target_date,target_meal))
    con.execute("INSERT INTO meal_plan(plan_date,meal,recipe_id) VALUES(?,?,?)",(target_date,target_meal,recipe_id))
    con.commit(); con.close()
    return jsonify(ok=True)

@app.post("/plan/set")
def plan_set():
    data=request.get_json(force=True); d=data["date"]; meal=data["meal"]; rid=data.get("recipe_id")
    con=db(); con.execute("DELETE FROM meal_plan WHERE plan_date=? AND meal=?",(d,meal))
    if rid: con.execute("INSERT INTO meal_plan(plan_date,meal,recipe_id) VALUES(?,?,?)",(d,meal,int(rid)))
    con.commit(); con.close(); return jsonify(ok=True)


# ---------------------------------------------------------
# Web-Import
# ---------------------------------------------------------

def _public_http_url(url):
    """Nur öffentliche http/https URLs zulassen (SSRF-Schutz)."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False, "Bitte eine vollständige http- oder https-Adresse eingeben."
        host = parsed.hostname.lower()
        if host in ("localhost",) or host.endswith(".local"):
            return False, "Lokale Netzwerkadressen werden beim Web-Import nicht geöffnet."
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            for info in infos:
                ip = ipaddress.ip_address(info[4][0])
                if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                        or ip.is_reserved or ip.is_unspecified):
                    return False, "Diese Adresse zeigt auf ein lokales oder nicht öffentliches Netzwerk."
        except socket.gaierror:
            return False, "Die Webseite konnte nicht gefunden werden."
        return True, ""
    except Exception:
        return False, "Die Webadresse ist ungültig."


def _fetch_html(url):
    ok, msg = _public_http_url(url)
    if not ok:
        raise ValueError(msg)
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 RecipeCollector/0.3.0",
            "Accept": "text/html,application/xhtml+xml"
        }
    )
    with urlopen(req, timeout=12) as response:
        ctype = response.headers.get_content_type()
        if ctype not in ("text/html", "application/xhtml+xml"):
            raise ValueError("Die Adresse liefert keine normale Webseite.")
        raw = response.read(3 * 1024 * 1024 + 1)
        if len(raw) > 3 * 1024 * 1024:
            raise ValueError("Die Webseite ist für den Import zu groß.")
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def _flatten_jsonld(value):
    out = []
    if isinstance(value, dict):
        out.append(value)
        if "@graph" in value:
            out.extend(_flatten_jsonld(value["@graph"]))
    elif isinstance(value, list):
        for item in value:
            out.extend(_flatten_jsonld(item))
    return out


def _is_recipe_type(value):
    t = value.get("@type", "")
    if isinstance(t, list):
        return any(str(x).lower() == "recipe" for x in t)
    return str(t).lower() == "recipe"


def _extract_jsonld(html_text):
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text, flags=re.I | re.S
    )
    for script in scripts:
        cleaned = html.unescape(script).strip()
        try:
            data = json.loads(cleaned)
        except Exception:
            # Manche Seiten enthalten harmlose Steuerzeichen oder Kommentare.
            cleaned = re.sub(r'^\s*<!--|-->\s*$', '', cleaned).strip()
            try:
                data = json.loads(cleaned)
            except Exception:
                continue
        for obj in _flatten_jsonld(data):
            if isinstance(obj, dict) and _is_recipe_type(obj):
                return obj
    return None


def _instructions_list(value):
    """Schema.org recipeInstructions robust in einzelne Kochschritte zerlegen."""
    lines = []

    def clean_text(text):
        text = html.unescape(str(text or ""))
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    if value is None:
        return lines

    if isinstance(value, str):
        text = clean_text(value)

        # Bevorzugt echte Zeilenumbrüche.
        parts = [x.strip(" \t\r\n-•") for x in re.split(r'\r?\n+', text) if x.strip()]

        # Falls alles in einem Block steckt, nur bei klaren Nummerierungen trennen.
        if len(parts) <= 1:
            numbered = re.split(r'(?=(?:^|\s)\d{1,2}[\.\)]\s+)', text)
            numbered = [re.sub(r'^\s*\d{1,2}[\.\)]\s*', '', x).strip() for x in numbered if x.strip()]
            if len(numbered) > 1:
                parts = numbered

        return [p for p in parts if p]

    if isinstance(value, list):
        for item in value:
            lines.extend(_instructions_list(item))
        return lines

    if isinstance(value, dict):
        typ = value.get("@type", "")
        if isinstance(typ, list):
            typ = " ".join(str(x) for x in typ)
        typ = str(typ).lower()

        if "howtosection" in typ:
            # Sektionsüberschrift nur dann aufnehmen, wenn darunter nichts anderes steht.
            nested = value.get("itemListElement") or value.get("steps") or []
            nested_lines = _instructions_list(nested)
            if nested_lines:
                lines.extend(nested_lines)
            else:
                name = clean_text(value.get("name"))
                if name:
                    lines.append(name)
            return lines

        text = value.get("text") or value.get("name")
        if text:
            cleaned = clean_text(text)
            if cleaned:
                lines.append(cleaned)

        nested = value.get("itemListElement")
        if nested:
            lines.extend(_instructions_list(nested))

    return lines


def _instructions_text(value):
    return "\\n".join(_instructions_list(value))

def _site_name(html_text, url):
    m = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)', html_text, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:site_name["\']', html_text, re.I)
    if m:
        return html.unescape(m.group(1)).strip()
    return urlparse(url).hostname or ""


def _recipe_image_url(recipe,page_url,page_html=""):
    image=recipe.get("image")
    candidates=[]
    if isinstance(image,str):
        candidates.append(image)
    elif isinstance(image,list):
        for x in image:
            if isinstance(x,str):
                candidates.append(x)
            elif isinstance(x,dict):
                candidates.append(x.get("url") or x.get("contentUrl") or "")
    elif isinstance(image,dict):
        candidates.append(image.get("url") or image.get("contentUrl") or "")

    # Fallbacks: OpenGraph/Twitter/itemprop, useful for Chefkoch and other sites.
    patterns=[
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
        r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\']'
    ]
    for pat in patterns:
        hit=re.search(pat,page_html or "",flags=re.I)
        if hit:
            candidates.append(html.unescape(hit.group(1)))

    for candidate in candidates:
        candidate=(candidate or "").strip()
        if candidate:
            return urljoin(page_url,candidate)
    return ""

def _download_recipe_image(url):
    if not url:return ""
    ok,_=_public_http_url(url)
    if not ok:return ""
    try:
        req=Request(url,headers={"User-Agent":"Mozilla/5.0 RecipeCollector/0.3.2","Accept":"image/webp,image/png,image/jpeg,*/*"})
        with urlopen(req,timeout=12) as response:
            ext={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}.get((response.headers.get_content_type() or "").lower())
            if not ext:return ""
            data=response.read(6*1024*1024+1)
            if len(data)>6*1024*1024:return ""
            name=f"{uuid.uuid4().hex}{ext}";(IMG_DIR/name).write_bytes(data);return name
    except Exception:return ""

def parse_recipe_url(url):
    page_html = _fetch_html(url)
    recipe = _extract_jsonld(page_html)
    if not recipe:
        raise ValueError(
            "Auf dieser Seite wurde kein strukturiertes Rezept erkannt. "
            "Diese erste Import-Version funktioniert mit Webseiten, die schema.org/Recipe (JSON-LD) bereitstellen."
        )
    ingredients = recipe.get("recipeIngredient") or []
    if isinstance(ingredients, str):
        ingredients = [ingredients]
    title = recipe.get("name") or ""
    steps = _instructions_text(recipe.get("recipeInstructions"))
    servings = recipe.get("recipeYield") or ""
    if isinstance(servings, list):
        servings = ", ".join(str(x) for x in servings)
    return {
        "title": str(title).strip(),
        "ingredients": "\n".join(str(x).strip() for x in ingredients if str(x).strip()),
        "steps": steps,
        "steps_list": _instructions_list(recipe.get("recipeInstructions")),
        "servings": str(servings).strip(),
        "prep_minutes": iso_duration_minutes(recipe.get("prepTime")),
        "cook_minutes": iso_duration_minutes(recipe.get("cookTime")),
        "total_minutes": iso_duration_minutes(recipe.get("totalTime")),
        "source_url": url.strip(),
        "source_name": _site_name(page_html, url),
        "image_url": _recipe_image_url(recipe, url, page_html),
    }


def import_recipe():
    error = ""
    preview = None

    if request.method == "POST":
        action = request.form.get("action", "preview")

        if action == "preview":
            url = request.form.get("url", "").strip()
            try:
                preview = parse_recipe_url(url)
            except Exception as exc:
                error = str(exc)

        elif action == "save":
            title = request.form.get("title", "").strip()
            if not title:
                error = "Bitte einen Rezeptnamen eingeben."
            else:
                image_url=request.form.get("image_url","").strip()
                image=_download_recipe_image(image_url) if image_url else ""
                con = db()
                cur = con.execute("""INSERT INTO recipes
                    (title,ingredients,steps,book,created_at,image,image_source,source_url,source_name,
                     servings,prep_minutes,cook_minutes,total_minutes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (title,request.form.get("ingredients","").strip(),form_steps(),"",
                     datetime.now().isoformat(),image,"web" if image else "",
                     request.form.get("source_url","").strip(),request.form.get("source_name","").strip(),
                     request.form.get("servings","").strip(),
                     int_form("prep_minutes"),int_form("cook_minutes"),int_form("total_minutes"))
                )
                rid = cur.lastrowid
                if image:
                    add_recipe_gallery_image(con,rid,image,"web")
                for cid in request.form.getlist("cookbooks"):
                    con.execute("INSERT OR IGNORE INTO recipe_cookbooks VALUES(?,?)",(rid,int(cid)))
                for tid in request.form.getlist("tags"):
                    con.execute("INSERT OR IGNORE INTO recipe_tags VALUES(?,?)",(rid,int(tid)))
                con.commit()
                con.close()
                return redirect(f"?view=recipe&id={rid}")

    con = db()
    cookbooks = con.execute("SELECT * FROM cookbooks ORDER BY name COLLATE NOCASE").fetchall()
    tags = con.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
    con.close()
    return render_template("import.html", preview=preview, error=error, cookbooks=cookbooks, tags=tags)


def ingredient_keywords(line):
    text=re.sub(r"\*\*|#+|\[|\]"," ",str(line or "")).lower()
    text=re.sub(r"^\s*[\d\s½¼¾⅓⅔⅛⅜⅝⅞/.,-]+\s*","",text)
    # Remove common units and filler words.
    stop={
        "g","kg","mg","ml","l","cl","dl","el","tl","teelöffel","esslöffel",
        "stück","stk","scheibe","scheiben","dose","dosen","packung","päckchen",
        "bund","prise","tasse","tassen","becher","glas","gläser",
        "frisch","frische","frischer","frisches","klein","kleine","kleiner",
        "groß","große","großer","etwas","nach","geschmack","ca"
    }
    words=[w for w in re.findall(r"[a-zäöüß]{3,}",text) if w not in stop]
    # Prefer the more characteristic tail words but keep unique order.
    out=[]
    for w in words:
        stem=w
        # light German plural normalization for matching
        for suffix in ("ern","en","er","es","e","n","s"):
            if len(stem)>5 and stem.endswith(suffix):
                stem=stem[:-len(suffix)]
                break
        if len(stem)>=3 and stem not in out:
            out.append(stem)
    return out

def normalize_match_word(word):
    stem=str(word or "").lower()
    for suffix in ("ern","en","er","es","e","n","s"):
        if len(stem)>5 and stem.endswith(suffix):
            stem=stem[:-len(suffix)]
            break
    return stem

def group_keywords(title):
    text=str(title or "").lower()
    stop={"für","das","die","den","der","des","zum","zur","einen","eine","ein"}
    return [normalize_match_word(w) for w in re.findall(r"[a-zäöüß]{3,}",text) if w not in stop]

def ingredients_for_step(step, ingredient_text):
    """
    Return grouped ingredient information for one cooking step.

    - If the step explicitly mentions a group heading (e.g. "Dressing"),
      every ingredient from that group is shown.
    - Phrases such as "alle Zutaten" use the most recently/clearly mentioned
      group. If there is only one group, all ingredients from it are shown.
    - Otherwise ingredients are matched by their names.
    """
    step_l=str(step or "").lower()
    groups=ingredient_groups(ingredient_text)
    if not groups:
        return []

    # Explicit group-heading match.
    matched_groups=[]
    for group in groups:
        title=group.get("title","")
        keys=group_keywords(title)
        if keys and any(k and k in step_l for k in keys):
            matched_groups.append(group)

    all_phrase=bool(re.search(
        r"\b(alle(?:n|r|s)?\s+zutaten|sämtliche(?:n)?\s+zutaten|alles\s+(?:hinzufügen|zugeben|vermengen|mischen))\b",
        step_l
    ))

    # If a group is named, "alle Zutaten" means all ingredients of that group.
    if matched_groups:
        return [{"title":g.get("title",""),"items":list(g.get("items",[]))} for g in matched_groups]

    # With a single logical group, "alle Zutaten" is unambiguous.
    nonempty=[g for g in groups if g.get("items")]
    if all_phrase and len(nonempty)==1:
        g=nonempty[0]
        return [{"title":g.get("title",""),"items":list(g.get("items",[]))}]

    step_words={normalize_match_word(w) for w in re.findall(r"[a-zäöüß]{3,}",step_l)}
    results=[]
    for group in groups:
        hits=[]
        for line in group.get("items",[]):
            keys=ingredient_keywords(line)
            if keys and any(k in step_words or k in step_l for k in keys):
                hits.append(line)
        if hits:
            results.append({"title":group.get("title",""),"items":hits})
    return results


def detect_seconds(text):
    t=text.lower()
    m=re.search(r'(\d+)\s*(minuten|min\b)',t)
    if m:return int(m.group(1))*60
    h=re.search(r'(\d+)\s*(stunden|stunde|std\b)',t)
    return int(h.group(1))*3600 if h else 0

def cook_mode():
    rid=request.args.get("id",type=int)
    con=db()
    r=con.execute("SELECT * FROM recipes WHERE id=?",(rid,)).fetchone()
    con.close()
    if not r:
        return redirect("./")

    raw_steps=[s.strip() for s in (r["steps"] or "").splitlines() if s.strip()]
    steps=[]
    for idx,text in enumerate(raw_steps,1):
        steps.append({
            "number":idx,
            "text":text,
            "seconds":detect_seconds(text),
            "ingredient_groups":ingredients_for_step(text,r["ingredients"] or "")
        })

    return render_template("cook.html",recipe=r,steps=steps)


app.run(host="0.0.0.0",port=8099,debug=False)
