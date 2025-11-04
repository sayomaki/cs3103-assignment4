import time, random, json

def now_ms() -> int:
    return int(time.time()*1000)

POKEMON_DB = [
    {"name":"Pikachu","stats":{"hp":35,"atk":55,"def":40,"sp_atk":50,"sp_def":50,"speed":90}},
    {"name":"Bulbasaur","stats":{"hp":45,"atk":49,"def":49,"sp_atk":65,"sp_def":65,"speed":45}},
    {"name":"Charmander","stats":{"hp":39,"atk":52,"def":43,"sp_atk":60,"sp_def":50,"speed":65}},
    {"name":"Squirtle","stats":{"hp":44,"atk":48,"def":65,"sp_atk":50,"sp_def":64,"speed":43}},
    {"name":"Gengar","stats":{"hp":60,"atk":65,"def":60,"sp_atk":130,"sp_def":75,"speed":110}},
    {"name":"Snorlax","stats":{"hp":160,"atk":110,"def":65,"sp_atk":65,"sp_def":110,"speed":30}},
]

def random_pokemon_payload(flag:int) -> bytes:
    p = random.choice(POKEMON_DB)
    payload = {
        "flag": int(flag),
        "type": "game_data",
        "ts_ms": now_ms(),
        "pokemon": {"name": p["name"], "stats": p["stats"]}
    }
    return json.dumps(payload, separators=(",", ":")).encode()