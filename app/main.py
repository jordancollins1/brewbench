import os, json, time, math, sqlite3, asyncio, re
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles

TOKEN = os.environ.get("API_TOKEN", "change-me")
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
NTFY = os.environ.get("NTFY_URL", "")
db = sqlite3.connect("/data/brew.db", check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""CREATE TABLE IF NOT EXISTS recipes(id INTEGER PRIMARY KEY, name TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS timers(id INTEGER PRIMARY KEY, label TEXT, end_ts REAL, notified INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS hops(id INTEGER PRIMARY KEY, name TEXT UNIQUE, alpha REAL, notes TEXT DEFAULT '');
INSERT OR IGNORE INTO hops(name,alpha,notes) VALUES
('Cascade',5.5,'Citrus, floral'),('Centennial',10.0,'Citrus, pine'),
('Citra',12.0,'Tropical, citrus'),('Mosaic',12.0,'Berry, tropical'),
('Saaz',3.5,'Spicy, herbal'),('Hallertau Mittelfruh',4.0,'Floral, delicate'),
('East Kent Goldings',5.0,'Earthy, spicy'),('Magnum',12.0,'Clean bittering');""")

def auth(x_token: str = Header("")):
    if x_token != TOKEN: raise HTTPException(401, "bad token")

app = FastAPI()

# ---------- brewing math (US units: lb, oz, gal, minutes) ----------
def calc(r: dict) -> dict:
    vol = float(r.get("batch_gal") or 5); eff = float(r.get("efficiency") or 72) / 100
    att = float(r.get("attenuation") or 75) / 100
    eq = r.get("equipment") or {}
    boil_time = float(r.get("boil_min") or 60)
    trub = float(eq.get("trub_loss") or 0.5)
    grain_absorption = float(eq.get("grain_absorption") or 0.125)
    grain_total = sum(float(g.get("lb") or 0) for g in r.get("grains", []))
    mash_water = grain_total * float(eq.get("mash_ratio") or 1.5) / 4.0
    boil_off = float(eq.get("boil_off") or 1.0) * (boil_time / 60)
    pre_boil = vol + boil_off + trub
    sparge = max(0, pre_boil - mash_water + grain_total * grain_absorption)
    kettle_capacity = float(eq.get("kettle_gal") or 8)
    carb_volumes = float(r.get("carb_volumes") or 2.4)
    beer_temp_f = float(r.get("beer_temp_f") or 68)
    sugar_factor = 1.0 if r.get("priming_sugar", "corn sugar") == "corn sugar" else .91
    priming_sugar_g = max(0, (carb_volumes - (0.85 - 0.0121 * beer_temp_f)) * vol * 3.78541 * 4.0 / sugar_factor)
    max_grain = float(eq.get("max_grain_lb") or 15)
    safe_pre_boil = kettle_capacity * float(eq.get("safe_fill") or .95)
    pts = sum(float(g.get("lb") or 0) * float(g.get("ppg") or 0) for g in r.get("grains", []))
    def additive_lb(a: dict) -> float:
        amount = float(a.get("amount") or 0)
        unit = a.get("unit", "lb")
        return {"oz": amount / 16, "g": amount / 453.592, "kg": amount * 2.20462}.get(unit, amount if unit == "lb" else 0)

    additive_pts = sum(additive_lb(a) * float(a.get("ppg") or 0)
                       for a in r.get("additives", []) if a.get("fermentable", True))
    og = 1 + (pts * eff + additive_pts) / vol / 1000
    fg = 1 + (og - 1) * (1 - att)
    abv = (og - fg) * 131.25
    big = 1.65 * 0.000125 ** (og - 1)
    def hop_oz(h: dict) -> float:
        return float(h.get("oz") or 0) if h.get("unit", "oz") == "oz" else float(h.get("amount") or 0) / 28.3495

    ibu = sum(big * (1 - math.exp(-0.04 * float(h.get("min") or 0))) / 4.15 *
              (float(h.get("alpha") or 0) / 100 * hop_oz(h) * 7490 / vol)
              for h in r.get("hops", []))
    mcu = sum(g["lb"] * g["srm"] for g in r.get("grains", [])) / vol
    srm = 1.4922 * mcu ** 0.6859 if mcu > 0 else 0
    return {"og": round(og, 3), "fg": round(fg, 3), "abv": round(abv, 1), "ibu": round(ibu), "srm": round(srm, 1),
            "mash_gal": round(mash_water, 1), "sparge_gal": round(sparge, 1), "pre_boil_gal": round(pre_boil, 1),
            "boil_off_gal": round(boil_off, 1), "kettle_capacity_gal": round(kettle_capacity, 1),
            "max_grain_lb": round(max_grain, 1), "safe_pre_boil_gal": round(safe_pre_boil, 1),
            "capacity_ok": pre_boil <= safe_pre_boil,
            "grain_capacity_ok": grain_total <= max_grain,
            "carb_volumes": round(carb_volumes, 2), "priming_sugar_g": round(priming_sugar_g, 1)}

@app.post("/api/calc", dependencies=[Depends(auth)])
def api_calc(r: dict): return calc(r)

# ---------- recipes ----------
@app.get("/api/recipes", dependencies=[Depends(auth)])
def list_recipes():
    return [{"id": x["id"], **json.loads(x["data"])} for x in db.execute("SELECT * FROM recipes ORDER BY id DESC")]

@app.post("/api/recipes", dependencies=[Depends(auth)])
def save_recipe(r: dict):
    rid = r.pop("id", None)
    if rid: db.execute("UPDATE recipes SET name=?, data=? WHERE id=?", (r["name"], json.dumps(r), rid))
    else: rid = db.execute("INSERT INTO recipes(name,data) VALUES(?,?)", (r["name"], json.dumps(r))).lastrowid
    db.commit(); return {"id": rid}

@app.delete("/api/recipes/{rid}", dependencies=[Depends(auth)])
def del_recipe(rid: int): db.execute("DELETE FROM recipes WHERE id=?", (rid,)); db.commit()

# ---------- editable hop catalog ----------
@app.get("/api/hops", dependencies=[Depends(auth)])
def list_hops(): return [dict(h) for h in db.execute("SELECT * FROM hops ORDER BY name")]

@app.post("/api/hops", dependencies=[Depends(auth)])
def save_hop(h: dict):
    if not h.get("name"): raise HTTPException(400, "hop name is required")
    try:
        hid = h.get("id")
        if hid:
            db.execute("UPDATE hops SET name=?, alpha=?, notes=? WHERE id=?", (h["name"], float(h.get("alpha") or 0), h.get("notes", ""), hid))
        else:
            db.execute("INSERT INTO hops(name,alpha,notes) VALUES(?,?,?)", (h["name"], float(h.get("alpha") or 0), h.get("notes", "")))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "a hop with that name already exists")
    db.commit(); return {"id": db.execute("SELECT id FROM hops WHERE name=?", (h["name"],)).fetchone()["id"]}

@app.delete("/api/hops/{hid}", dependencies=[Depends(auth)])
def del_hop(hid: int): db.execute("DELETE FROM hops WHERE id=?", (hid,)); db.commit()

# ---------- timers: absolute end times live on the server ----------
@app.get("/api/timers", dependencies=[Depends(auth)])
def timers(): return {"now": time.time(), "timers": [dict(t) for t in db.execute("SELECT * FROM timers ORDER BY end_ts")]}

@app.post("/api/timers", dependencies=[Depends(auth)])
def add_timer(t: dict):
    delay = float(t.get("delay_minutes") or 0)
    db.execute("INSERT INTO timers(label,end_ts) VALUES(?,?)",
               (t["label"], time.time() + delay * 60 + float(t["minutes"]) * 60)); db.commit()

@app.delete("/api/timers/{tid}", dependencies=[Depends(auth)])
def del_timer(tid: int): db.execute("DELETE FROM timers WHERE id=?", (tid,)); db.commit()

@app.on_event("startup")
async def notifier():
    async def loop():
        while True:
            for t in db.execute("SELECT * FROM timers WHERE notified=0 AND end_ts<=?", (time.time(),)).fetchall():
                db.execute("UPDATE timers SET notified=1 WHERE id=?", (t["id"],)); db.commit()
                if NTFY:
                    try: httpx.post(NTFY, content=f"Timer done: {t['label']}")
                    except Exception: pass
            await asyncio.sleep(5)
    asyncio.create_task(loop())

# ---------- AI recipe builder: LLM drafts, our math verifies ----------
SYS = """You are a complete homebrew recipe designer. Reply with ONLY valid JSON, no prose or code fences:
{"name":str,"type":"Beer|Cider|Seltzer","style":str,"icon":"🍺","batch_gal":num,"efficiency":num,"attenuation":num,"boil_min":num,
"mash_profile":"Single infusion|Brew-in-a-bag|High attenuation|Step mash",
"grains":[{"name":str,"lb":num,"ppg":num,"srm":num,"timing":"Mash"}],
"hops":[{"name":str,"oz":num,"alpha":num,"min":num,"timing":"Boil|Whirlpool|Dry hop"}],
"additives":[{"name":str,"amount":num,"unit":"oz|lb|g|tsp|tablet|each","ppg":num,"fermentable":true,"timing":"Mash|Boil|10 min|15 min|Flameout|Whirlpool|Fermentation|Bottling|Packaging"}],
"yeast":str,"primary_days":num,"secondary_days":num,"conditioning_days":num,
"carb_volumes":num,"beer_temp_f":num,"priming_sugar":"corn sugar|table sugar|keg","notes":str}.
Build the full recipe, including process additions when useful: honey, sugar, malt extract, lactose, fruit, juice, spices, yeast nutrient, Whirlfloc, finings, priming sugar, and water additions. Set fermentable false for non-fermentable process ingredients. Include fermentation temperature, duration, dry hop timing, carbonation or bottling guidance in notes.
Recommend fermentation length, whether secondary is useful, a target carbonation level based on style, and packaging guidance. Do not recommend secondary for ordinary clean beers unless there is a reason such as fruit, oak, or extended aging. Respect the user's target style, beverage type, target batch size, equipment limits, and requested OG/FG/ABV/IBU. Use ppg = extract potential points/lb/gal (base malt ~36, crystal ~34, roasted ~25), and srm = grain color in Lovibond."""

async def ask(messages):
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
            json={"model": MODEL, "max_tokens": 2000, "system": SYS, "messages": messages})
        r.raise_for_status()
        return r.json()["content"][0]["text"]

@app.post("/api/ai", dependencies=[Depends(auth)])
async def ai(req: dict):
    context = req.get("context", {})
    msgs = [{"role": "user", "content": f"""Create a complete BrewBench recipe for:
User request: {req["prompt"]}
Current recipe context: {json.dumps(context)}
Return every required recipe section, even if a section is empty. Do not omit equipment-aware process details."""}]
    for _ in range(3):
        text = await ask(msgs)
        rec = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
        stats = calc(rec)
        msgs += [{"role": "assistant", "content": text},
                 {"role": "user", "content": f"Verified by calculator: {stats}. If OG, ABV, IBU or SRM miss what the user asked for ({req['prompt']}) by more than ~5%, adjust amounts and return corrected JSON; otherwise repeat the same JSON."}]
        if text.strip() == msgs[-3]["content"].strip() if len(msgs) > 3 else False: break
    return {**rec, "stats": calc(rec)}

app.add_api_route("/api/health", lambda: {"status": "ok"}, methods=["GET"])
app.mount("/", StaticFiles(directory=str(Path(__file__).resolve().parent / "static"), html=True))
