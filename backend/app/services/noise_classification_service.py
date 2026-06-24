"""
NoiseClassificationService
--------------------------
Classifies audio noise type using YAMNet (Yet Another Audio MobileNet),
a lightweight MobileNet-based model pretrained on AudioSet (521 classes).

Supported noise types (expanded):
    silence, speech, music, traffic, wind, rain, crowd, nature,
    alarm, construction, household, keyboard, fan, background_noise, unknown

Install deps:
    pip install tensorflow tensorflow-hub numpy

Optional (higher-quality resampling):
    pip install resampy

YAMNet weights (~3.7 MB) are downloaded automatically from TF Hub on first use.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    import tensorflow as tf
    import tensorflow_hub as hub
    _TF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TF_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class NoiseType(str, Enum):
    SILENCE          = "silence"
    SPEECH           = "speech"
    MUSIC            = "music"
    TRAFFIC          = "traffic"
    WIND             = "wind"
    RAIN             = "rain"           # NEW: rain / water / thunder
    CROWD            = "crowd"          # NEW: crowd / cheering / applause
    NATURE           = "nature"         # NEW: birds / insects / animals outdoors
    ALARM            = "alarm"          # NEW: alarms / sirens / beeps
    CONSTRUCTION     = "construction"   # NEW: drills / hammers / power tools
    HOUSEHOLD        = "household"      # NEW: kitchen / appliances / domestic
    KEYBOARD         = "keyboard"
    FAN              = "fan"
    BACKGROUND_NOISE = "background_noise"
    UNKNOWN          = "unknown"


@dataclass
class ClassificationResult:
    noise_type:       NoiseType
    confidence:       float            # 0.0 – 1.0
    snr_db:           float            # estimated SNR via min-statistics
    rms_db:           float            # RMS energy in dBFS
    dominant_freq_hz: float            # spectral peak frequency
    top_labels:       list[tuple[str, float]] = field(default_factory=list)
    # top_labels: up to 5 raw YAMNet labels with their scores, for debugging


# ---------------------------------------------------------------------------
# YAMNet index → NoiseType  (full 521-class map, indices from official CSV)
#
# Strategy: every index is assigned exactly one bucket.  Classification uses
# top-K *maximum* (not sum) so bucket size doesn't bias the result.
# ---------------------------------------------------------------------------

# fmt: off
_LABEL_NAMES: dict[int, str] = {
    # A compact lookup used for top_labels debug output.
    # (Only the indices we care about — full list in _IDX_TO_TYPE below.)
      0: "Speech",
      1: "Child speech",
      2: "Conversation",
      3: "Narration",
      4: "Babbling",
      5: "Speech synthesizer",
      6: "Shout",
      7: "Bellow",
      8: "Whoop",
      9: "Yell",
     10: "Children shouting",
     11: "Screaming",
     12: "Whispering",
     13: "Laughter",
     14: "Baby laughter",
     15: "Giggle",
     16: "Snicker",
     17: "Belly laugh",
     18: "Chuckle",
     19: "Crying, sobbing",
     20: "Baby cry",
     21: "Whimper",
     22: "Wail, moan",
     23: "Sigh",
     24: "Singing",
     25: "Choir",
     26: "Yodeling",
     27: "Chant",
     28: "Mantra",
     29: "Child singing",
     30: "Synthetic singing",
     31: "Rapping",
     32: "Humming",
     58: "Clapping",
     61: "Cheering",
     62: "Applause",
     63: "Chatter",
     64: "Crowd",
     65: "Hubbub / speech babble",
     66: "Children playing",
     67: "Animal",
     69: "Dog",
     76: "Cat",
    106: "Bird",
    107: "Bird call / song",
    108: "Chirp, tweet",
    121: "Insect",
    122: "Cricket",
    132: "Music",
    133: "Musical instrument",
    156: "Percussion",
    157: "Drum kit",
    277: "Wind",
    278: "Rustling leaves",
    279: "Wind noise (mic)",
    280: "Thunderstorm",
    281: "Thunder",
    282: "Water",
    283: "Rain",
    284: "Raindrop",
    285: "Rain on surface",
    286: "Stream",
    287: "Waterfall",
    288: "Ocean",
    289: "Waves, surf",
    292: "Fire",
    293: "Crackle",
    294: "Vehicle",
    300: "Motor vehicle (road)",
    301: "Car",
    302: "Car horn",
    308: "Car passing by",
    310: "Truck",
    315: "Bus",
    320: "Motorcycle",
    321: "Traffic noise",
    329: "Aircraft",
    333: "Helicopter",
    337: "Engine",
    340: "Lawn mower",
    341: "Chainsaw",
    348: "Door",
    358: "Dishes",
    361: "Frying",
    362: "Microwave oven",
    363: "Blender",
    367: "Hair dryer",
    368: "Toilet flush",
    371: "Vacuum cleaner",
    378: "Typing",
    380: "Computer keyboard",
    382: "Alarm",
    383: "Telephone",
    389: "Alarm clock",
    390: "Siren",
    393: "Smoke detector",
    394: "Fire alarm",
    406: "Mechanical fan",
    407: "Air conditioning",
    413: "Hammer",
    414: "Jackhammer",
    418: "Power tool",
    419: "Drill",
    485: "Clicking",
    486: "Clickety-clack",
    490: "Hum",
    494: "Silence",
    500: "Inside, small room",
    501: "Inside, large room",
    502: "Inside, public space",
    503: "Outside, urban",
    504: "Outside, rural/natural",
    507: "Noise",
    508: "Environmental noise",
    509: "Static",
    510: "Mains hum",
    514: "White noise",
    515: "Pink noise",
    518: "Television",
    519: "Radio",
}

_IDX_TO_TYPE: dict[int, NoiseType] = {

    # ── Silence ──────────────────────────────────────────────────────────────
    494: NoiseType.SILENCE,                    # Silence

    # ── Speech ───────────────────────────────────────────────────────────────
      0: NoiseType.SPEECH,                     # Speech
      1: NoiseType.SPEECH,                     # Child speech, kid speaking
      2: NoiseType.SPEECH,                     # Conversation
      3: NoiseType.SPEECH,                     # Narration, monologue
      4: NoiseType.SPEECH,                     # Babbling
      5: NoiseType.SPEECH,                     # Speech synthesizer
      6: NoiseType.SPEECH,                     # Shout
      7: NoiseType.SPEECH,                     # Bellow
      8: NoiseType.SPEECH,                     # Whoop
      9: NoiseType.SPEECH,                     # Yell
     10: NoiseType.SPEECH,                     # Children shouting
     11: NoiseType.SPEECH,                     # Screaming
     12: NoiseType.SPEECH,                     # Whispering
     13: NoiseType.SPEECH,                     # Laughter
     14: NoiseType.SPEECH,                     # Baby laughter
     15: NoiseType.SPEECH,                     # Giggle
     16: NoiseType.SPEECH,                     # Snicker
     17: NoiseType.SPEECH,                     # Belly laugh
     18: NoiseType.SPEECH,                     # Chuckle, chortle
     19: NoiseType.SPEECH,                     # Crying, sobbing
     20: NoiseType.SPEECH,                     # Baby cry, infant cry
     21: NoiseType.SPEECH,                     # Whimper
     22: NoiseType.SPEECH,                     # Wail, moan
     23: NoiseType.SPEECH,                     # Sigh
     31: NoiseType.SPEECH,                     # Rapping

    # ── Music ─────────────────────────────────────────────────────────────
     24: NoiseType.MUSIC,                      # Singing
     25: NoiseType.MUSIC,                      # Choir
     26: NoiseType.MUSIC,                      # Yodeling
     27: NoiseType.MUSIC,                      # Chant
     28: NoiseType.MUSIC,                      # Mantra
     29: NoiseType.MUSIC,                      # Child singing
     30: NoiseType.MUSIC,                      # Synthetic singing
     32: NoiseType.MUSIC,                      # Humming
    132: NoiseType.MUSIC,                      # Music
    133: NoiseType.MUSIC,                      # Musical instrument
    134: NoiseType.MUSIC,                      # Plucked string instrument
    135: NoiseType.MUSIC,                      # Guitar
    136: NoiseType.MUSIC,                      # Electric guitar
    137: NoiseType.MUSIC,                      # Bass guitar
    138: NoiseType.MUSIC,                      # Acoustic guitar
    139: NoiseType.MUSIC,                      # Steel guitar
    140: NoiseType.MUSIC,                      # Tapping (guitar technique)
    141: NoiseType.MUSIC,                      # Strum
    142: NoiseType.MUSIC,                      # Banjo
    143: NoiseType.MUSIC,                      # Sitar
    144: NoiseType.MUSIC,                      # Mandolin
    145: NoiseType.MUSIC,                      # Zither
    146: NoiseType.MUSIC,                      # Ukulele
    147: NoiseType.MUSIC,                      # Keyboard (musical)
    148: NoiseType.MUSIC,                      # Piano
    149: NoiseType.MUSIC,                      # Electric piano
    150: NoiseType.MUSIC,                      # Organ
    151: NoiseType.MUSIC,                      # Electronic organ
    152: NoiseType.MUSIC,                      # Hammond organ
    153: NoiseType.MUSIC,                      # Synthesizer
    154: NoiseType.MUSIC,                      # Sampler
    155: NoiseType.MUSIC,                      # Harpsichord
    156: NoiseType.MUSIC,                      # Percussion
    157: NoiseType.MUSIC,                      # Drum kit
    158: NoiseType.MUSIC,                      # Drum machine
    159: NoiseType.MUSIC,                      # Drum
    160: NoiseType.MUSIC,                      # Snare drum
    161: NoiseType.MUSIC,                      # Rimshot
    162: NoiseType.MUSIC,                      # Drum roll
    163: NoiseType.MUSIC,                      # Bass drum
    164: NoiseType.MUSIC,                      # Timpani
    165: NoiseType.MUSIC,                      # Tabla
    166: NoiseType.MUSIC,                      # Cymbal
    167: NoiseType.MUSIC,                      # Hi-hat
    168: NoiseType.MUSIC,                      # Wood block
    169: NoiseType.MUSIC,                      # Tambourine
    170: NoiseType.MUSIC,                      # Rattle (instrument)
    171: NoiseType.MUSIC,                      # Maraca
    172: NoiseType.MUSIC,                      # Gong
    173: NoiseType.MUSIC,                      # Tubular bells
    174: NoiseType.MUSIC,                      # Mallet percussion
    175: NoiseType.MUSIC,                      # Marimba, xylophone
    176: NoiseType.MUSIC,                      # Glockenspiel
    177: NoiseType.MUSIC,                      # Vibraphone
    178: NoiseType.MUSIC,                      # Steelpan
    179: NoiseType.MUSIC,                      # Orchestra
    180: NoiseType.MUSIC,                      # Brass instrument
    181: NoiseType.MUSIC,                      # French horn
    182: NoiseType.MUSIC,                      # Trumpet
    183: NoiseType.MUSIC,                      # Trombone
    184: NoiseType.MUSIC,                      # Bowed string instrument
    185: NoiseType.MUSIC,                      # String section
    186: NoiseType.MUSIC,                      # Violin, fiddle
    187: NoiseType.MUSIC,                      # Pizzicato
    188: NoiseType.MUSIC,                      # Cello
    189: NoiseType.MUSIC,                      # Double bass
    190: NoiseType.MUSIC,                      # Wind instrument, woodwind
    191: NoiseType.MUSIC,                      # Flute
    192: NoiseType.MUSIC,                      # Saxophone
    193: NoiseType.MUSIC,                      # Clarinet
    194: NoiseType.MUSIC,                      # Harp
    195: NoiseType.MUSIC,                      # Bell
    196: NoiseType.MUSIC,                      # Church bell
    197: NoiseType.MUSIC,                      # Jingle bell
    200: NoiseType.MUSIC,                      # Chime
    203: NoiseType.MUSIC,                      # Harmonica
    204: NoiseType.MUSIC,                      # Accordion
    205: NoiseType.MUSIC,                      # Bagpipes
    206: NoiseType.MUSIC,                      # Didgeridoo
    208: NoiseType.MUSIC,                      # Theremin
    210: NoiseType.MUSIC,                      # Scratching (performance)
    211: NoiseType.MUSIC,                      # Pop music
    212: NoiseType.MUSIC,                      # Hip hop music
    213: NoiseType.MUSIC,                      # Beatboxing
    214: NoiseType.MUSIC,                      # Rock music
    215: NoiseType.MUSIC,                      # Heavy metal
    216: NoiseType.MUSIC,                      # Punk rock
    217: NoiseType.MUSIC,                      # Grunge
    218: NoiseType.MUSIC,                      # Progressive rock
    219: NoiseType.MUSIC,                      # Rock and roll
    220: NoiseType.MUSIC,                      # Psychedelic rock
    221: NoiseType.MUSIC,                      # Rhythm and blues
    222: NoiseType.MUSIC,                      # Soul music
    223: NoiseType.MUSIC,                      # Reggae
    224: NoiseType.MUSIC,                      # Country
    225: NoiseType.MUSIC,                      # Swing music
    226: NoiseType.MUSIC,                      # Bluegrass
    227: NoiseType.MUSIC,                      # Funk
    228: NoiseType.MUSIC,                      # Folk music
    229: NoiseType.MUSIC,                      # Middle Eastern music
    230: NoiseType.MUSIC,                      # Jazz
    231: NoiseType.MUSIC,                      # Disco
    232: NoiseType.MUSIC,                      # Classical music
    233: NoiseType.MUSIC,                      # Opera
    234: NoiseType.MUSIC,                      # Electronic music
    235: NoiseType.MUSIC,                      # House music
    236: NoiseType.MUSIC,                      # Techno
    237: NoiseType.MUSIC,                      # Dubstep
    238: NoiseType.MUSIC,                      # Drum and bass
    239: NoiseType.MUSIC,                      # Electronica
    240: NoiseType.MUSIC,                      # Electronic dance music
    241: NoiseType.MUSIC,                      # Ambient music
    242: NoiseType.MUSIC,                      # Trance music
    243: NoiseType.MUSIC,                      # Music of Latin America
    244: NoiseType.MUSIC,                      # Salsa music
    245: NoiseType.MUSIC,                      # Flamenco
    246: NoiseType.MUSIC,                      # Blues
    247: NoiseType.MUSIC,                      # Music for children
    248: NoiseType.MUSIC,                      # New-age music
    249: NoiseType.MUSIC,                      # Vocal music
    250: NoiseType.MUSIC,                      # A capella
    251: NoiseType.MUSIC,                      # Music of Africa
    252: NoiseType.MUSIC,                      # Afrobeat
    253: NoiseType.MUSIC,                      # Christian music
    254: NoiseType.MUSIC,                      # Gospel music
    255: NoiseType.MUSIC,                      # Music of Asia
    256: NoiseType.MUSIC,                      # Carnatic music
    257: NoiseType.MUSIC,                      # Music of Bollywood
    258: NoiseType.MUSIC,                      # Ska
    259: NoiseType.MUSIC,                      # Traditional music
    260: NoiseType.MUSIC,                      # Independent music
    261: NoiseType.MUSIC,                      # Song
    262: NoiseType.MUSIC,                      # Background music
    263: NoiseType.MUSIC,                      # Theme music
    264: NoiseType.MUSIC,                      # Jingle (music)
    265: NoiseType.MUSIC,                      # Soundtrack music
    266: NoiseType.MUSIC,                      # Lullaby
    267: NoiseType.MUSIC,                      # Video game music
    268: NoiseType.MUSIC,                      # Christmas music
    269: NoiseType.MUSIC,                      # Dance music
    270: NoiseType.MUSIC,                      # Wedding music
    271: NoiseType.MUSIC,                      # Happy music
    272: NoiseType.MUSIC,                      # Sad music
    273: NoiseType.MUSIC,                      # Tender music
    274: NoiseType.MUSIC,                      # Exciting music
    275: NoiseType.MUSIC,                      # Angry music
    276: NoiseType.MUSIC,                      # Scary music
    518: NoiseType.MUSIC,                      # Television (often carries music)
    519: NoiseType.MUSIC,                      # Radio

    # ── Traffic ───────────────────────────────────────────────────────────
    294: NoiseType.TRAFFIC,                    # Vehicle
    295: NoiseType.TRAFFIC,                    # Boat, water vehicle
    298: NoiseType.TRAFFIC,                    # Motorboat, speedboat
    300: NoiseType.TRAFFIC,                    # Motor vehicle (road)
    301: NoiseType.TRAFFIC,                    # Car
    302: NoiseType.TRAFFIC,                    # Vehicle horn, car horn
    303: NoiseType.TRAFFIC,                    # Toot
    304: NoiseType.TRAFFIC,                    # Car alarm
    305: NoiseType.TRAFFIC,                    # Power windows
    306: NoiseType.TRAFFIC,                    # Skidding
    307: NoiseType.TRAFFIC,                    # Tire squeal
    308: NoiseType.TRAFFIC,                    # Car passing by
    309: NoiseType.TRAFFIC,                    # Race car, auto racing
    310: NoiseType.TRAFFIC,                    # Truck
    311: NoiseType.TRAFFIC,                    # Air brake
    312: NoiseType.TRAFFIC,                    # Air horn, truck horn
    313: NoiseType.TRAFFIC,                    # Reversing beeps
    315: NoiseType.TRAFFIC,                    # Bus
    316: NoiseType.TRAFFIC,                    # Emergency vehicle
    317: NoiseType.TRAFFIC,                    # Police car (siren)
    318: NoiseType.TRAFFIC,                    # Ambulance (siren)
    319: NoiseType.TRAFFIC,                    # Fire engine (siren)
    320: NoiseType.TRAFFIC,                    # Motorcycle
    321: NoiseType.TRAFFIC,                    # Traffic noise, roadway noise
    322: NoiseType.TRAFFIC,                    # Rail transport
    323: NoiseType.TRAFFIC,                    # Train
    324: NoiseType.TRAFFIC,                    # Train whistle
    325: NoiseType.TRAFFIC,                    # Train horn
    326: NoiseType.TRAFFIC,                    # Railroad car, train wagon
    327: NoiseType.TRAFFIC,                    # Train wheels squealing
    328: NoiseType.TRAFFIC,                    # Subway, metro, underground
    329: NoiseType.TRAFFIC,                    # Aircraft
    330: NoiseType.TRAFFIC,                    # Aircraft engine
    331: NoiseType.TRAFFIC,                    # Jet engine
    332: NoiseType.TRAFFIC,                    # Propeller, airscrew
    333: NoiseType.TRAFFIC,                    # Helicopter
    334: NoiseType.TRAFFIC,                    # Fixed-wing aircraft
    335: NoiseType.TRAFFIC,                    # Bicycle
    336: NoiseType.TRAFFIC,                    # Skateboard
    337: NoiseType.TRAFFIC,                    # Engine
    342: NoiseType.TRAFFIC,                    # Medium engine (mid frequency)
    343: NoiseType.TRAFFIC,                    # Heavy engine (low frequency)
    344: NoiseType.TRAFFIC,                    # Engine knocking
    345: NoiseType.TRAFFIC,                    # Engine starting
    346: NoiseType.TRAFFIC,                    # Idling
    347: NoiseType.TRAFFIC,                    # Accelerating, revving, vroom
    503: NoiseType.TRAFFIC,                    # Outside, urban or manmade

    # ── Wind ──────────────────────────────────────────────────────────────
    277: NoiseType.WIND,                       # Wind
    278: NoiseType.WIND,                       # Rustling leaves
    279: NoiseType.WIND,                       # Wind noise (microphone)
    201: NoiseType.WIND,                       # Wind chime
    453: NoiseType.WIND,                       # Whoosh, swoosh, swish

    # ── Rain / Water / Thunder ────────────────────────────────────────────
    280: NoiseType.RAIN,                       # Thunderstorm
    281: NoiseType.RAIN,                       # Thunder
    282: NoiseType.RAIN,                       # Water
    283: NoiseType.RAIN,                       # Rain
    284: NoiseType.RAIN,                       # Raindrop
    285: NoiseType.RAIN,                       # Rain on surface
    286: NoiseType.RAIN,                       # Stream
    287: NoiseType.RAIN,                       # Waterfall
    288: NoiseType.RAIN,                       # Ocean
    289: NoiseType.RAIN,                       # Waves, surf
    290: NoiseType.RAIN,                       # Steam
    291: NoiseType.RAIN,                       # Gurgling
    438: NoiseType.RAIN,                       # Liquid
    439: NoiseType.RAIN,                       # Splash, splatter
    440: NoiseType.RAIN,                       # Slosh
    442: NoiseType.RAIN,                       # Drip
    443: NoiseType.RAIN,                       # Pour
    444: NoiseType.RAIN,                       # Trickle, dribble
    445: NoiseType.RAIN,                       # Gush
    450: NoiseType.RAIN,                       # Boiling

    # ── Crowd ─────────────────────────────────────────────────────────────
     58: NoiseType.CROWD,                      # Clapping
     61: NoiseType.CROWD,                      # Cheering
     62: NoiseType.CROWD,                      # Applause
     63: NoiseType.CROWD,                      # Chatter
     64: NoiseType.CROWD,                      # Crowd
     65: NoiseType.CROWD,                      # Hubbub, speech noise, babble
     66: NoiseType.CROWD,                      # Children playing

    # ── Nature (animals / outdoor ambience) ───────────────────────────────
     67: NoiseType.NATURE,                     # Animal
     68: NoiseType.NATURE,                     # Domestic animals, pets
     69: NoiseType.NATURE,                     # Dog
     70: NoiseType.NATURE,                     # Bark
     71: NoiseType.NATURE,                     # Yip
     72: NoiseType.NATURE,                     # Howl
     73: NoiseType.NATURE,                     # Bow-wow
     74: NoiseType.NATURE,                     # Growling
     76: NoiseType.NATURE,                     # Cat
     77: NoiseType.NATURE,                     # Purr
     78: NoiseType.NATURE,                     # Meow
     81: NoiseType.NATURE,                     # Livestock, farm animals
     82: NoiseType.NATURE,                     # Horse
     83: NoiseType.NATURE,                     # Clip-clop
     84: NoiseType.NATURE,                     # Neigh, whinny
     85: NoiseType.NATURE,                     # Cattle, bovinae
     86: NoiseType.NATURE,                     # Moo
     88: NoiseType.NATURE,                     # Pig
     90: NoiseType.NATURE,                     # Goat
     92: NoiseType.NATURE,                     # Sheep
     93: NoiseType.NATURE,                     # Fowl
     94: NoiseType.NATURE,                     # Chicken, rooster
     97: NoiseType.NATURE,                     # Turkey
     99: NoiseType.NATURE,                     # Duck
    101: NoiseType.NATURE,                     # Goose
    103: NoiseType.NATURE,                     # Wild animals
    104: NoiseType.NATURE,                     # Roaring cats (lions, tigers)
    106: NoiseType.NATURE,                     # Bird
    107: NoiseType.NATURE,                     # Bird vocalization / call / song
    108: NoiseType.NATURE,                     # Chirp, tweet
    109: NoiseType.NATURE,                     # Squawk
    110: NoiseType.NATURE,                     # Pigeon, dove
    112: NoiseType.NATURE,                     # Crow
    114: NoiseType.NATURE,                     # Owl
    116: NoiseType.NATURE,                     # Bird flight, flapping wings
    121: NoiseType.NATURE,                     # Insect
    122: NoiseType.NATURE,                     # Cricket
    123: NoiseType.NATURE,                     # Mosquito
    124: NoiseType.NATURE,                     # Fly, housefly
    125: NoiseType.NATURE,                     # Buzz
    126: NoiseType.NATURE,                     # Bee, wasp
    127: NoiseType.NATURE,                     # Frog
    128: NoiseType.NATURE,                     # Croak
    292: NoiseType.NATURE,                     # Fire (campfire / outdoor)
    293: NoiseType.NATURE,                     # Crackle
    504: NoiseType.NATURE,                     # Outside, rural or natural
    520: NoiseType.NATURE,                     # Field recording

    # ── Alarm / siren / notification ──────────────────────────────────────
    382: NoiseType.ALARM,                      # Alarm
    383: NoiseType.ALARM,                      # Telephone
    384: NoiseType.ALARM,                      # Telephone bell ringing
    385: NoiseType.ALARM,                      # Ringtone
    386: NoiseType.ALARM,                      # Telephone dialing, DTMF
    387: NoiseType.ALARM,                      # Dial tone
    389: NoiseType.ALARM,                      # Alarm clock
    390: NoiseType.ALARM,                      # Siren
    391: NoiseType.ALARM,                      # Civil defense siren
    392: NoiseType.ALARM,                      # Buzzer
    393: NoiseType.ALARM,                      # Smoke detector, smoke alarm
    394: NoiseType.ALARM,                      # Fire alarm
    395: NoiseType.ALARM,                      # Foghorn
    396: NoiseType.ALARM,                      # Whistle
    475: NoiseType.ALARM,                      # Beep, bleep
    476: NoiseType.ALARM,                      # Ping
    477: NoiseType.ALARM,                      # Ding

    # ── Construction / heavy machinery / tools ────────────────────────────
    338: NoiseType.CONSTRUCTION,               # Light engine (high frequency)
    339: NoiseType.CONSTRUCTION,               # Dental drill
    340: NoiseType.CONSTRUCTION,               # Lawn mower
    341: NoiseType.CONSTRUCTION,               # Chainsaw
    398: NoiseType.CONSTRUCTION,               # Mechanisms
    399: NoiseType.CONSTRUCTION,               # Ratchet, pawl
    403: NoiseType.CONSTRUCTION,               # Gears
    404: NoiseType.CONSTRUCTION,               # Pulleys
    405: NoiseType.CONSTRUCTION,               # Sewing machine
    409: NoiseType.CONSTRUCTION,               # Printer
    412: NoiseType.CONSTRUCTION,               # Tools
    413: NoiseType.CONSTRUCTION,               # Hammer
    414: NoiseType.CONSTRUCTION,               # Jackhammer
    415: NoiseType.CONSTRUCTION,               # Sawing
    416: NoiseType.CONSTRUCTION,               # Filing (rasp)
    417: NoiseType.CONSTRUCTION,               # Sanding
    418: NoiseType.CONSTRUCTION,               # Power tool
    419: NoiseType.CONSTRUCTION,               # Drill
    420: NoiseType.CONSTRUCTION,               # Explosion
    430: NoiseType.CONSTRUCTION,               # Boom
    463: NoiseType.CONSTRUCTION,               # Smash, crash
    464: NoiseType.CONSTRUCTION,               # Breaking

    # ── Household / domestic / indoor ─────────────────────────────────────
    348: NoiseType.HOUSEHOLD,                  # Door
    349: NoiseType.HOUSEHOLD,                  # Doorbell
    351: NoiseType.HOUSEHOLD,                  # Sliding door
    352: NoiseType.HOUSEHOLD,                  # Slam
    353: NoiseType.HOUSEHOLD,                  # Knock
    354: NoiseType.HOUSEHOLD,                  # Tap
    355: NoiseType.HOUSEHOLD,                  # Squeak
    356: NoiseType.HOUSEHOLD,                  # Cupboard open or close
    357: NoiseType.HOUSEHOLD,                  # Drawer open or close
    358: NoiseType.HOUSEHOLD,                  # Dishes, pots, and pans
    359: NoiseType.HOUSEHOLD,                  # Cutlery, silverware
    360: NoiseType.HOUSEHOLD,                  # Chopping (food)
    361: NoiseType.HOUSEHOLD,                  # Frying (food)
    362: NoiseType.HOUSEHOLD,                  # Microwave oven
    363: NoiseType.HOUSEHOLD,                  # Blender
    364: NoiseType.HOUSEHOLD,                  # Water tap, faucet
    365: NoiseType.HOUSEHOLD,                  # Sink (filling or washing)
    366: NoiseType.HOUSEHOLD,                  # Bathtub (filling or washing)
    367: NoiseType.HOUSEHOLD,                  # Hair dryer
    368: NoiseType.HOUSEHOLD,                  # Toilet flush
    369: NoiseType.HOUSEHOLD,                  # Toothbrush
    370: NoiseType.HOUSEHOLD,                  # Electric toothbrush
    371: NoiseType.HOUSEHOLD,                  # Vacuum cleaner
    372: NoiseType.HOUSEHOLD,                  # Zipper (clothing)
    373: NoiseType.HOUSEHOLD,                  # Keys jangling
    374: NoiseType.HOUSEHOLD,                  # Coin (dropping)
    375: NoiseType.HOUSEHOLD,                  # Scissors
    376: NoiseType.HOUSEHOLD,                  # Electric shaver
    400: NoiseType.HOUSEHOLD,                  # Clock
    401: NoiseType.HOUSEHOLD,                  # Tick
    402: NoiseType.HOUSEHOLD,                  # Tick-tock
    408: NoiseType.HOUSEHOLD,                  # Cash register
    410: NoiseType.HOUSEHOLD,                  # Camera
    500: NoiseType.HOUSEHOLD,                  # Inside, small room
    501: NoiseType.HOUSEHOLD,                  # Inside, large room or hall
    502: NoiseType.HOUSEHOLD,                  # Inside, public space

    # ── Keyboard / typing / clicking ──────────────────────────────────────
    378: NoiseType.KEYBOARD,                   # Typing
    379: NoiseType.KEYBOARD,                   # Typewriter
    380: NoiseType.KEYBOARD,                   # Computer keyboard
    381: NoiseType.KEYBOARD,                   # Writing
    485: NoiseType.KEYBOARD,                   # Clicking
    486: NoiseType.KEYBOARD,                   # Clickety-clack

    # ── Fan / HVAC / steady-state noise ──────────────────────────────────
    406: NoiseType.FAN,                        # Mechanical fan
    407: NoiseType.FAN,                        # Air conditioning
    490: NoiseType.FAN,                        # Hum
    510: NoiseType.FAN,                        # Mains hum
    514: NoiseType.FAN,                        # White noise
    515: NoiseType.FAN,                        # Pink noise
    482: NoiseType.FAN,                        # Whir
    516: NoiseType.FAN,                        # Throbbing
    517: NoiseType.FAN,                        # Vibration

    # ── Generic background / noise floor ─────────────────────────────────
     79: NoiseType.BACKGROUND_NOISE,           # Hiss
    505: NoiseType.BACKGROUND_NOISE,           # Reverberation
    506: NoiseType.BACKGROUND_NOISE,           # Echo
    507: NoiseType.BACKGROUND_NOISE,           # Noise
    508: NoiseType.BACKGROUND_NOISE,           # Environmental noise
    509: NoiseType.BACKGROUND_NOISE,           # Static
    511: NoiseType.BACKGROUND_NOISE,           # Distortion
    512: NoiseType.BACKGROUND_NOISE,           # Sidetone
    513: NoiseType.BACKGROUND_NOISE,           # Cacophony
}
# fmt: on

# Duplicate-key resolution: later assignments win in dict literals, but we
# want explicit precedence for the few indices shared across buckets (e.g.
# 378/380/485 are in both KEYBOARD and HOUSEHOLD blocks above — KEYBOARD wins
# because it appears last in the literal).  Verify at import time:
assert _IDX_TO_TYPE[378] == NoiseType.KEYBOARD, "index 378 should be KEYBOARD"
assert _IDX_TO_TYPE[380] == NoiseType.KEYBOARD, "index 380 should be KEYBOARD"
assert _IDX_TO_TYPE[485] == NoiseType.KEYBOARD, "index 485 should be KEYBOARD"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class NoiseClassificationService:
    """
    Classifies the dominant noise type in an audio chunk using YAMNet.

    Classification uses a **top-K maximum score** strategy rather than summing
    bucket scores.  For each NoiseType bucket, the score is the *maximum*
    raw YAMNet probability across all classes in that bucket, scaled by
    log(bucket_size) so larger buckets get a mild boost without dominating.
    The winning bucket is compared against all others after this scaling.

    Parameters
    ----------
    sample_rate : int
        Native sample-rate of the incoming audio.  Resampled to 16 kHz
        internally (YAMNet requirement).
    silence_threshold_db : float
        RMS level below which audio is classified as silence without
        running inference.  Defaults to -60 dBFS.
    min_confidence : float
        Normalised confidence below which result is UNKNOWN.  Defaults 0.25.
    top_labels_n : int
        Number of raw YAMNet labels to include in ClassificationResult for
        debugging (0 to disable).  Defaults to 5.
    """

    YAMNET_SAMPLE_RATE: int = 16_000
    YAMNET_HUB_URL: str     = "https://tfhub.dev/google/yamnet/1"
    FRAME_SIZE: int         = 1024
    HOP_SIZE:   int         = 512

    def __init__(
        self,
        sample_rate:          int   = 48_000,
        silence_threshold_db: float = -60.0,
        min_confidence:       float = 0.25,
        top_labels_n:         int   = 5,
    ) -> None:
        if not _TF_AVAILABLE:
            raise ImportError(
                "TensorFlow dependencies not installed.\n"
                "Run: pip install tensorflow tensorflow-hub"
            )
        self.sample_rate          = sample_rate
        self.silence_threshold_db = silence_threshold_db
        self.min_confidence       = min_confidence
        self.top_labels_n         = top_labels_n

        self._model = hub.load(self.YAMNET_HUB_URL)

        # Pre-compute bucket sizes for score scaling
        self._bucket_sizes: dict[NoiseType, int] = {t: 0 for t in NoiseType}
        for nt in _IDX_TO_TYPE.values():
            self._bucket_sizes[nt] += 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, audio: np.ndarray) -> ClassificationResult:
        """
        Classify the noise type in *audio* (mono float32, shape [N]).

        Parameters
        ----------
        audio : np.ndarray
            1-D (or 2-D stereo) float32 array in [-1, 1].
        """
        if audio.ndim > 1:
            audio = audio.mean(axis=0)
        audio = audio.astype(np.float32)

        rms    = self._rms(audio)
        rms_db = float(20 * np.log10(rms + 1e-9))

        if rms_db < self.silence_threshold_db:
            return ClassificationResult(
                noise_type=NoiseType.SILENCE,
                confidence=0.95,
                snr_db=0.0,
                rms_db=round(rms_db, 2),
                dominant_freq_hz=0.0,
                top_labels=[],
            )

        spectrum, freqs = self._magnitude_spectrum(audio)
        dom_freq        = self._dominant_frequency(spectrum, freqs)
        snr_db          = self._estimate_snr(audio)

        audio_16k = self._resample(audio)
        scores, _emb, _spec = self._model(audio_16k)

        # mean across frames → (521,)
        mean_scores: np.ndarray = tf.reduce_mean(scores, axis=0).numpy()

        top_labels = self._top_labels(mean_scores)
        noise_type, confidence = self._aggregate_scores(mean_scores)

        if confidence < self.min_confidence:
            noise_type = NoiseType.UNKNOWN
            confidence = float(np.max(mean_scores))

        return ClassificationResult(
            noise_type=noise_type,
            confidence=round(float(confidence), 3),
            snr_db=round(snr_db, 2),
            rms_db=round(rms_db, 2),
            dominant_freq_hz=round(dom_freq, 1),
            top_labels=top_labels,
        )

    def classify_batch(self, chunks: list[np.ndarray]) -> list[ClassificationResult]:
        return [self.classify(c) for c in chunks]

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _aggregate_scores(
        self, scores: np.ndarray
    ) -> tuple[NoiseType, float]:
        """
        For each NoiseType bucket compute:
            bucket_score = max(raw_scores in bucket)
                         * log1p(bucket_size) / log1p(max_bucket_size)

        This rewards buckets that score confidently on their best class,
        with a mild log-size boost so a large bucket like MUSIC isn't
        penalised versus a 6-entry bucket like FAN.

        Confidence is the winning bucket's scaled score divided by the
        sum of all bucket scores.
        """
        max_size = max(self._bucket_sizes.values())

        # Step 1: max score per bucket
        bucket_max: dict[NoiseType, float] = {t: 0.0 for t in NoiseType}
        for idx, nt in _IDX_TO_TYPE.items():
            if idx < len(scores):
                v = float(scores[idx])
                if v > bucket_max[nt]:
                    bucket_max[nt] = v

        # Step 2: log-size scaling
        import math
        bucket_scaled: dict[NoiseType, float] = {}
        for nt, mx in bucket_max.items():
            if nt == NoiseType.UNKNOWN:
                continue
            size_weight = math.log1p(self._bucket_sizes[nt]) / math.log1p(max_size)
            bucket_scaled[nt] = mx * size_weight

        if not bucket_scaled or max(bucket_scaled.values()) == 0.0:
            return NoiseType.UNKNOWN, 0.0

        total      = sum(bucket_scaled.values()) + 1e-9
        best_type  = max(bucket_scaled, key=lambda k: bucket_scaled[k])
        confidence = bucket_scaled[best_type] / total

        return best_type, min(float(confidence), 1.0)

    def _top_labels(self, scores: np.ndarray) -> list[tuple[str, float]]:
        """Return the N highest-scoring raw YAMNet labels for debugging."""
        if self.top_labels_n <= 0:
            return []
        top_idx = np.argsort(scores)[::-1][: self.top_labels_n]
        return [
            (_LABEL_NAMES.get(int(i), f"class_{i}"), round(float(scores[i]), 4))
            for i in top_idx
        ]

    # ------------------------------------------------------------------
    # Resampling
    # ------------------------------------------------------------------

    def _resample(self, audio: np.ndarray) -> tf.Tensor:
        if self.sample_rate == self.YAMNET_SAMPLE_RATE:
            return tf.constant(audio, dtype=tf.float32)
        try:
            import resampy
            audio_16k = resampy.resample(
                audio, self.sample_rate, self.YAMNET_SAMPLE_RATE
            ).astype(np.float32)
            return tf.constant(audio_16k, dtype=tf.float32)
        except ImportError:
            pass
        # TF bilinear fallback
        n_out = int(len(audio) * self.YAMNET_SAMPLE_RATE / self.sample_rate)
        t = tf.constant(audio[None, :, None], dtype=tf.float32)
        t = tf.image.resize(t, [1, n_out], method="bilinear")
        return tf.squeeze(t, axis=[0, 2])

    # ------------------------------------------------------------------
    # Spectral diagnostics
    # ------------------------------------------------------------------

    def _rms(self, audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(audio ** 2)))

    def _magnitude_spectrum(self, audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        N        = min(len(audio), 8192)
        windowed = audio[:N] * np.hanning(N)
        fft      = np.abs(np.fft.rfft(windowed))
        freqs    = np.fft.rfftfreq(N, d=1.0 / self.sample_rate)
        return fft, freqs

    def _dominant_frequency(self, spectrum: np.ndarray, freqs: np.ndarray) -> float:
        return float(freqs[np.argmax(spectrum)])

    def _estimate_snr(self, audio: np.ndarray, percentile: float = 10) -> float:
        frame_rms = [
            self._rms(audio[i : i + self.FRAME_SIZE])
            for i in range(0, len(audio) - self.FRAME_SIZE, self.HOP_SIZE)
        ]
        if not frame_rms:
            return 0.0
        noise_floor = float(np.percentile(frame_rms, percentile)) + 1e-9
        signal_peak = float(np.percentile(frame_rms, 90))         + 1e-9
        return float(np.clip(20 * np.log10(signal_peak / noise_floor), -20, 60))