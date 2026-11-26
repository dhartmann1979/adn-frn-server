# Français (Belgique): the French guide with the Belgian menu label (🌐 BE) – the interface itself uses Belgian dates and a few Belgian words
import copy, importlib.util
from pathlib import Path
_s = importlib.util.spec_from_file_location('fr', Path(__file__).parent / 'fr.py'); _fr = importlib.util.module_from_spec(_s); _s.loader.exec_module(_fr)
UI = dict(_fr.UI)
SHARED = copy.deepcopy(_fr.SHARED)
SHARED['lang'] = (SHARED['lang'][0], SHARED['lang'][1].replace('**🌐 FR ▾**', '**🌐 BE ▾**'))
SYSTEMS = copy.deepcopy(_fr.SYSTEMS)
