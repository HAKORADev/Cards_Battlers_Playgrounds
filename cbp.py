import os
import json
import math
import random
import time
import zipfile
import re
import shutil
import hashlib
from pathlib import Path
from dataclasses import dataclass, field

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

SCENE_W, SCENE_H = 800, 600
RENDER_W, RENDER_H = 1920, 1080
W, H = SCENE_W, SCENE_H
FPS = 60
RENDER_SCALE = min(RENDER_W / SCENE_W, RENDER_H / SCENE_H)
RENDER_VIEW_W = int(SCENE_W * RENDER_SCALE)
RENDER_VIEW_H = int(SCENE_H * RENDER_SCALE)
RENDER_VIEW_X = (RENDER_W - RENDER_VIEW_W) // 2
RENDER_VIEW_Y = (RENDER_H - RENDER_VIEW_H) // 2
IMAGE_SCALE_CACHE = {}
TEXT_SCALE_CACHE = {}
FILE_IMAGE_CACHE = {}
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ASSETS = DATA / "assets"
SCHEMAS = DATA / "schemas"
SAVE = DATA / "save.json"
RUNTIME_DIR = DATA / "runtime"
RUNTIME_CHARACTERS = RUNTIME_DIR / "characters"
RUNTIME_TEAMS = RUNTIME_DIR / "teams"
RUNTIME_WORLD = RUNTIME_DIR / "world"
RUNTIME_WORLD_INDEX = RUNTIME_WORLD / "index.json"
RUNTIME_WORLD_COLLECTIONS = RUNTIME_WORLD / "collections"
def slug(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "entity"


COLORS = {
    "ink": (58, 43, 53),
    "deep": (198, 155, 91),
    "panel": (117, 83, 70),
    "panel2": (148, 108, 76),
    "line": (125, 91, 76),
    "cyan": (205, 225, 221),
    "blue": (181, 207, 214),
    "violet": (255, 248, 228),
    "gold": (235, 188, 77),
    "cream": (255, 248, 228),
    "muted": (231, 215, 177),
    "green": (167, 197, 145),
    "red": (197, 125, 112),
    "orange": (222, 151, 81),
    "black": (58, 43, 53),
    "white": (255, 255, 255)
}

DUEL_PHASES = ["DRAW", "STANDBY", "MAIN 1", "BATTLE", "MAIN 2", "END"]
DUEL_PHASE_ABBREVIATIONS = {"DRAW": "DP", "STANDBY": "SP", "MAIN 1": "M1", "BATTLE": "BP", "MAIN 2": "M2", "END": "EP"}
CHARACTER_RUNTIME_FIELDS = {"mood", "allies", "enemies", "history", "library_cards", "borrowed_cards", "rank", "relationship", "availability", "current_place", "destination", "movement_progress", "activity", "cooldown_until", "behavior_weights", "learned_cards", "learned_opponents"}
TEAM_RUNTIME_FIELDS = {"relationship", "team_effect", "rank", "history", "effect_locked"}


def ensure_dirs():
    paths = [DATA, ASSETS, SCHEMAS, DATA / "cards", DATA / "characters", DATA / "teams", DATA / "places", DATA / "decks", DATA / "logic", DATA / "animations", DATA / "audio", DATA / "menu" / "background", DATA / "menu" / "duelers" / "left", DATA / "menu" / "duelers" / "center", DATA / "menu" / "duelers" / "right", DATA / "menu" / "ui", DATA / "menu" / "audio", DATA / "exports", RUNTIME_DIR, RUNTIME_CHARACTERS, RUNTIME_TEAMS, RUNTIME_WORLD, RUNTIME_WORLD_COLLECTIONS]
    for path in paths: path.mkdir(parents=True, exist_ok=True)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def clamp(value, low, high):
    return max(low, min(high, value))


def render_factor(surface):
    return (RENDER_SCALE, RENDER_SCALE) if surface.get_size() == (RENDER_W, RENDER_H) else (1.0, 1.0)


def render_offset(surface):
    return (RENDER_VIEW_X, RENDER_VIEW_Y) if surface.get_size() == (RENDER_W, RENDER_H) else (0, 0)


def render_point(surface, point):
    scale_x, scale_y = render_factor(surface)
    offset_x, offset_y = render_offset(surface)
    return (int(offset_x + point[0] * scale_x), int(offset_y + point[1] * scale_y))


def render_rect(surface, rect):
    rect = pygame.Rect(rect)
    scale_x, scale_y = render_factor(surface)
    offset_x, offset_y = render_offset(surface)
    return pygame.Rect(int(offset_x + rect.x * scale_x), int(offset_y + rect.y * scale_y), max(1, int(rect.width * scale_x)), max(1, int(rect.height * scale_y)))


def render_size(surface, size):
    scale_x, scale_y = render_factor(surface)
    return (max(1, int(size[0] * scale_x)), max(1, int(size[1] * scale_y)))


def scaled_image(image, size):
    size = (max(1, int(size[0])), max(1, int(size[1])))
    if image is None or image.get_size() == size: return image
    key = (id(image), image.get_size(), size)
    cached = IMAGE_SCALE_CACHE.get(key)
    if cached is None:
        cached = pygame.transform.smoothscale(image, size)
        if len(IMAGE_SCALE_CACHE) >= 512: IMAGE_SCALE_CACHE.clear()
        IMAGE_SCALE_CACHE[key] = cached
    return cached


def cached_file_image(path):
    key = str(path)
    image = FILE_IMAGE_CACHE.get(key)
    if image is None:
        try: image = pygame.image.load(key).convert_alpha()
        except pygame.error: return None
        if len(FILE_IMAGE_CACHE) >= 256: FILE_IMAGE_CACHE.clear()
        FILE_IMAGE_CACHE[key] = image
    return image


def scaled_text(font, text, color, size):
    key = (id(font), str(text), tuple(color), tuple(size))
    image = TEXT_SCALE_CACHE.get(key)
    if image is None:
        image = scaled_image(font.render(str(text), True, color), size)
        if len(TEXT_SCALE_CACHE) >= 2048: TEXT_SCALE_CACHE.clear()
        TEXT_SCALE_CACHE[key] = image
    return image


def ui_surface(size, flags=0):
    return pygame.Surface((RENDER_W, RENDER_H) if tuple(size) == (SCENE_W, SCENE_H) else size, flags)


def ui_blit(surface, image, position):
    if image is None: return None
    scale_x, scale_y = render_factor(surface)
    if (scale_x, scale_y) != (1.0, 1.0) and image.get_size() != (RENDER_W, RENDER_H):
        image = scaled_image(image, render_size(surface, image.get_size()))
    if surface.get_size() == (RENDER_W, RENDER_H) and image.get_size() == (RENDER_W, RENDER_H) and tuple(position) == (0, 0): return surface.blit(image, (0, 0))
    return surface.blit(image, render_point(surface, position))


def ui_draw_rect(surface, color, rect, width=0, border_radius=0):
    scale_x, scale_y = render_factor(surface)
    factor = min(scale_x, scale_y)
    return pygame.draw.rect(surface, color, render_rect(surface, rect), max(0, int(width * factor)), border_radius=max(0, int(border_radius * factor)))


def ui_draw_line(surface, color, start, end, width=1):
    scale_x, scale_y = render_factor(surface)
    return pygame.draw.line(surface, color, render_point(surface, start), render_point(surface, end), max(1, int(width * min(scale_x, scale_y))))


def ui_draw_polygon(surface, color, points, width=0):
    scale_x, scale_y = render_factor(surface)
    return pygame.draw.polygon(surface, color, [render_point(surface, point) for point in points], max(0, int(width * min(scale_x, scale_y))))


def ui_draw_circle(surface, color, center, radius, width=0):
    scale_x, scale_y = render_factor(surface)
    factor = min(scale_x, scale_y)
    return pygame.draw.circle(surface, color, render_point(surface, center), max(1, int(radius * factor)), max(0, int(width * factor)))


def wrap(font, text, width):
    words = str(text).split()
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if font.size(candidate)[0] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_text(surface, text, position, font, color=COLORS["cream"], anchor="topleft"):
    scale_x, scale_y = render_factor(surface)
    image = scaled_text(font, text, color, render_size(surface, font.size(str(text)))) if (scale_x, scale_y) != (1.0, 1.0) else font.render(str(text), True, color)
    rect = image.get_rect()
    setattr(rect, anchor, render_point(surface, position))
    surface.blit(image, rect)
    return rect


def rounded(surface, rect, fill, outline=None, radius=8, width=1):
    ui_draw_rect(surface, fill, rect, border_radius=radius)
    if outline: ui_draw_rect(surface, outline, rect, width, border_radius=radius)


CARD_FRAME_COLORS = {
    "normal": (220, 176, 67),
    "effect": (211, 126, 54),
    "ritual": (88, 128, 190),
    "fusion": (139, 92, 159),
    "spell": (119, 181, 187),
    "field": (108, 163, 110),
    "trap": (184, 82, 123),
    "legendary": (142, 54, 58)
}


def card_frame_color(card):
    if card.legendary or card.kind == "legendary": return CARD_FRAME_COLORS["legendary"]
    return CARD_FRAME_COLORS.get(card.kind, CARD_FRAME_COLORS["normal"])


@dataclass
class DuelLayout:
    viewport: tuple = (800, 600)
    table: pygame.Rect = field(default_factory=lambda: pygame.Rect(126, 18, 624, 564))
    duel_frame: pygame.Rect = field(default_factory=lambda: pygame.Rect(170, 45, 536, 480))
    field: pygame.Rect = field(default_factory=lambda: pygame.Rect(238, 92, 400, 400))
    center_y: int = 292
    left_rail_x: int = 184
    right_rail_x: int = 656
    hand_center_x: int = 438
    phase_x: int = 118
    opponent_hand_y: int = 6
    player_hand_y: int = 486
    monster_card_size: tuple = (60, 78)
    spell_card_size: tuple = (60, 78)
    hand_card_size: tuple = (68, 100)
    slot_pitch: int = 78
    def zone_x(self, index):
        return self.field.x + 18 + index * self.slot_pitch
    def monster_rect(self, side, index):
        x = self.zone_x(index)
        y = self.field.y + 92 if side == "opponent" else self.field.y + 212
        return pygame.Rect(x, y, self.monster_card_size[0], self.monster_card_size[1])
    def spell_rect(self, side, index):
        x = self.zone_x(index)
        y = self.field.y + 10 if side == "opponent" else self.field.y + 306
        return pygame.Rect(x, y, self.spell_card_size[0], self.spell_card_size[1])
    def hand_rect(self, side, index, count, selected=False, lifted=False):
        step = min(68, 360 // max(1, count))
        total = self.hand_card_size[0] + max(0, count - 1) * step
        start = self.hand_center_x - total // 2
        y = self.opponent_hand_y if side == "opponent" else self.player_hand_y
        lift = 10 if lifted and side == "player" else 0
        height = self.hand_card_size[1] + (8 if selected else 0)
        return pygame.Rect(start + index * step, y - (8 if selected else 0) - lift, self.hand_card_size[0], height)
    def side_well_rect(self, side, kind):
        positions = {
            "opponent": {"extra": (self.right_rail_x, 164, 54, 68), "field": (self.right_rail_x, 90, 54, 68), "deck": (self.left_rail_x, 164, 54, 68), "graveyard": (self.left_rail_x, 90, 54, 68), "banished": (self.left_rail_x, 238, 54, 68)},
            "player": {"extra": (self.left_rail_x, 454, 54, 68), "field": (self.left_rail_x, 380, 54, 68), "deck": (self.right_rail_x, 454, 54, 68), "graveyard": (self.right_rail_x, 380, 54, 68), "banished": (self.right_rail_x, 528, 54, 68)}
        }
        return pygame.Rect(positions[side][kind])
    def field_slot_rect(self):
        return self.side_well_rect("player", "field").inflate(-2, -2)
    def pfp_rect(self, side):
        return pygame.Rect(12, 38 if side == "opponent" else 538, 46, 46)
    def hud_rect(self, side):
        pfp = self.pfp_rect(side)
        return pygame.Rect(8, pfp.y - 4, 172, 54)
    def phase_rect(self, index):
        return pygame.Rect(self.phase_x, 116 + index * 38, 54, 32)
    def question_rect(self):
        return pygame.Rect(314, 238, 316, 126)
    def question_action_rect(self, name):
        if name == "yes": return pygame.Rect(400, 302, 64, 30)
        if name == "no": return pygame.Rect(472, 302, 64, 30)
        return pygame.Rect(436, 302, 64, 30)
    def interaction_rect(self):
        return pygame.Rect(8, 404, 172, 116)
    def card_list_popup_rect(self):
        return pygame.Rect(126, 218, 566, 174)
    def hud_text_x(self):
        return self.field.x + 16
    def hud_bar_x(self):
        return self.field.x


def cursor_pressed(buttons):
    return bool(buttons[0])


def blit_aspect(surface, image, rect):
    rect = render_rect(surface, rect)
    ratio = min(rect.width / max(1, image.get_width()), rect.height / max(1, image.get_height()))
    size = (max(1, int(image.get_width() * ratio)), max(1, int(image.get_height() * ratio)))
    scaled = scaled_image(image, size)
    surface.blit(scaled, scaled.get_rect(center=rect.center).topleft)


def card_template_kind(card):
    if card.legendary or card.kind == "legendary": return "legendary"
    if card.kind == "field": return "spell"
    return card.kind if card.kind in ["normal", "effect", "spell", "trap", "fusion", "ritual"] else "normal"


def card_art_window(rect):
    rect = pygame.Rect(rect)
    return pygame.Rect(rect.x + int(rect.width * 29 / 247), rect.y + int(rect.height * 71 / 361), max(1, int(rect.width * 190 / 247)), max(1, int(rect.height * 188 / 361)))


def render_engine_card(surface, rect, card, assets, registry=None, known=True, face_down=False, variant=1, compact=False, defense_position=False):
    layout_rect = pygame.Rect(rect)
    rect = render_rect(surface, layout_rect)
    if face_down:
        image = assets.image("card_back")
        if image:
            if defense_position: image = pygame.transform.rotate(image, 90)
            blit_aspect(surface, image, layout_rect)
        return
    field_mode = not compact and layout_rect.width <= 100 and layout_rect.height <= 110
    template_kind = card_template_kind(card)
    template = assets.card_template(template_kind)
    if not template: return
    art_rect = card_art_window(rect)
    art_path = registry.card_art(card, variant or card.art_variant) if registry else ""
    if art_path:
        try:
            art = cached_file_image(art_path)
            if art is None: raise pygame.error("card art unavailable")
            surface.blit(scaled_image(art, art_rect.size), art_rect.topleft)
        except pygame.error:
            art_path = ""
    if not art_path:
        art = assets.image("missing_card_art", art_rect.size)
        if art: surface.blit(art, art_rect.topleft)
    surface.blit(scaled_image(template, rect.size), rect.topleft)

    title_size = 5 if field_mode else 6 if compact else 9
    row_size = 5 if field_mode else 6 if compact else 8
    body_size = 4 if field_mode else 5 if compact else 7
    title_limit = 8 if field_mode else 12 if compact else 24
    draw_text(surface, card.name[:title_limit], (layout_rect.x + int(layout_rect.width * 0.47), layout_rect.y + int(layout_rect.height * 0.105)), assets.display_font(title_size, True), COLORS["ink"], "center")
    badge_center = (rect.x + int(rect.width * 0.84), rect.y + int(rect.height * 0.145))
    badge = assets.card_badge(template_kind)
    if badge:
        badge_size = max(8, int(rect.width * 0.16))
        surface.blit(scaled_image(badge, (badge_size, badge_size)), (badge_center[0] - badge_size // 2, badge_center[1] - badge_size // 2))

    monster_kind = card.kind in ["normal", "effect", "fusion", "ritual", "legendary"]
    row_y = layout_rect.y + int(layout_rect.height * 0.195)
    if monster_kind:
        star_count = max(0, min(11, int(card.stars)))
        star_size = max(5, min(14, int(layout_rect.width * 0.12)))
        star_gap = max(1, star_size // 8)
        available_width = max(1, layout_rect.width - 8)
        while star_count and star_size > 5 and star_count * star_size + max(0, star_count - 1) * star_gap > available_width: star_size -= 1
        total_width = star_count * star_size + max(0, star_count - 1) * star_gap
        if star_count and total_width <= available_width:
            native_star_size = render_size(surface, (star_size, star_size))
            star_image = assets.image("star_level", native_star_size)
            if star_image:
                start_x = layout_rect.centerx - total_width // 2
                for star_index in range(star_count):
                    star_point = render_point(surface, (start_x + star_index * (star_size + star_gap), row_y - star_size // 2))
                    surface.blit(star_image, star_point)
            else: draw_text(surface, "★" * star_count, (layout_rect.centerx, row_y), assets.font(row_size, True), COLORS["ink"], "center")
        else: draw_text(surface, f"★{star_count}", (layout_rect.centerx, row_y), assets.font(row_size, True), COLORS["ink"], "center")
    else:
        row_label = "TRAP CARD" if card.kind == "trap" else "SPELL CARD"
        draw_text(surface, row_label, (layout_rect.centerx, row_y), assets.font(row_size, True), COLORS["ink"], "center")
    layout_art_rect = card_art_window(layout_rect)
    subtype = card.family.upper()[:16]
    draw_text(surface, subtype, (layout_rect.centerx, layout_art_rect.bottom + int(layout_rect.height * 0.075)), assets.font(body_size, True), COLORS["ink"], "center")
    if not compact and not field_mode:
        lines = wrap(assets.font(body_size), card.description, max(30, layout_rect.width - 12))[:3]
        for index, line in enumerate(lines):
            draw_text(surface, line, (layout_rect.x + 6, layout_art_rect.bottom + int(layout_rect.height * 0.12) + index * (body_size + 1)), assets.font(body_size), COLORS["ink"])
    stat = f"ATK {card.atk}  DEF {card.defense}" if monster_kind else card.kind.upper()
    if not field_mode: draw_text(surface, stat, (layout_rect.centerx, layout_rect.bottom - int(layout_rect.height * 0.075)), assets.font(body_size, True), COLORS["ink"], "center")


class AssetBank:
    def __init__(self):
        self.images = {}
        self.sounds = {}
        self.fonts = {}
        self.role_images = {}
        self.sized_images = {}
        self.menu_layers = {}
        self.cursor_cache = {}
        self.reaction_sounds = {}
        self.card_templates = {}
        self.card_badges = {}
        self.splash_names = []
        self.external_manifest = self.load_external_manifest()
        self.load_images()
        self.load_card_templates()
        self.load_sounds()

    def cursor(self, pressed=False):
        key = "cursor_click" if pressed else "cursor_normal"
        image = self.images.get(key)
        if image is None: return None, (0, 0)
        cached = self.cursor_cache.get(key)
        if cached: return cached
        ratio = min(30 / max(1, image.get_width()), 52 / max(1, image.get_height()))
        size = (max(1, int(image.get_width() * ratio)), max(1, int(image.get_height() * ratio)))
        cursor = scaled_image(image, size)
        hotspot = (int(cursor.get_width() * 0.32), int(cursor.get_height() * 0.045))
        self.cursor_cache[key] = (cursor, hotspot)
        return cursor, hotspot

    def image(self, name, size=None):
        image = self.images.get(name)
        if image is None: return None
        if size and image.get_size() != size:
            key = (name, tuple(size))
            if key not in self.sized_images: self.sized_images[key] = scaled_image(image, size)
            return self.sized_images[key]
        return image

    def load_external_manifest(self):
        manifest_name = os.environ.get("CBP_EXTERNAL_ASSET_MANIFEST", "").strip()
        if not manifest_name: return {}
        path = Path(manifest_name)
        if not path.exists(): return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def asset_roots(self):
        roots = []
        external_root = os.environ.get("CBP_EXTERNAL_ASSET_ROOT", "").strip()
        if external_root: roots.append(Path(external_root))
        roots.append(ASSETS)
        return list(dict.fromkeys(roots))

    def manifest_path(self, role):
        external_root = os.environ.get("CBP_EXTERNAL_ASSET_ROOT", "").strip()
        relative = self.external_manifest.get("roles", {}).get(role, "")
        if not external_root or not relative: return None
        path = Path(external_root) / str(relative)
        return path if path.exists() else None

    def image_candidates(self, name):
        aliases = {"duel_playmat_cycle9": "duel_playmat", "duel_field": "duel_environment", "card_back": "card_back"}
        candidates = []
        manifest = self.manifest_path(aliases.get(name, name))
        if manifest: candidates.append(manifest)
        candidates.extend(base / f"{name}.png" for base in self.asset_roots())
        return candidates

    def role_image(self, role, size=None):
        image = self.role_images.get(role)
        if image is None and role not in self.role_images:
            path = self.manifest_path(role)
            image = None
            if path and path.exists():
                try: image = pygame.image.load(str(path)).convert_alpha()
                except pygame.error: image = None
            fallback_roles = {"place_ground": "duel_field", "duel_environment": "duel_field", "table_frame": "table_frame_cycle12", "duel_frame": "duel_frame_cycle12", "field_surface": "field_surface_cycle12"}
            if image is None: image = self.images.get(fallback_roles.get(role, role))
            self.role_images[role] = image
        if image is None: return None
        if size and image.get_size() != size:
            key = (role, tuple(size))
            if key not in self.sized_images: self.sized_images[key] = scaled_image(image, size)
            return self.sized_images[key]
        return image

    def load_card_templates(self):
        kinds = ["normal", "effect", "spell", "trap", "fusion", "ritual", "legendary"]
        for kind in kinds:
            for base in self.asset_roots():
                path = base / "card_frames" / f"{kind}_card_transparent.png"
                if path.exists():
                    try:
                        self.card_templates[kind] = pygame.image.load(str(path)).convert_alpha()
                        break
                    except pygame.error:
                        pass
                badge = base / "card_frames" / "badges" / f"{kind}.png"
                if badge.exists():
                    try:
                        self.card_badges[kind] = pygame.image.load(str(badge)).convert_alpha()
                    except pygame.error:
                        pass
    def card_template(self, kind):
        return self.card_templates.get("spell" if kind == "field" else kind) or self.card_templates.get("normal")
    def card_badge(self, kind):
        return self.card_badges.get("spell" if kind == "field" else kind)

    def load_images(self):
        self.splash_names = []
        for base in self.asset_roots():
            for path in sorted(base.rglob("*.png")):
                name = path.stem
                if name in self.images: continue
                try: self.images[name] = pygame.image.load(str(path)).convert_alpha()
                except pygame.error: continue
                if name.startswith("splash"): self.splash_names.append(name)
        self.splash_names = sorted(set(self.splash_names))

    def menu_layer(self, name, size=None):
        key = (name, tuple(size) if size else None)
        if key in self.menu_layers: return self.menu_layers[key]
        candidates = [base / "menu" / f"{name}.png" for base in self.asset_roots()] + [base / f"{name}.png" for base in self.asset_roots()]
        for path in candidates:
            if path.exists():
                image = cached_file_image(path)
                if image is not None:
                    image = scaled_image(image, size) if size and image.get_size() != size else image
                    self.menu_layers[key] = image
                    return image
        self.menu_layers[key] = None
        return None

    def sound_candidates(self, name):
        candidates = []
        manifest = self.manifest_path(name)
        if manifest: candidates.append(manifest)
        candidates.extend(base / f"{name}.wav" for base in self.asset_roots())
        return candidates

    def load_sounds(self):
        for name in ["menu_music", "voice_attack", "sfx_attack", "music_duel"]:
            for path in self.sound_candidates(name):
                if path.exists():
                    try:
                        self.sounds[name] = pygame.mixer.Sound(str(path))
                        break
                    except pygame.error:
                        pass

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            family = "Noto Serif Display" if bold and size >= 20 else "DejaVu Sans"
            self.fonts[key] = pygame.font.SysFont(family, size, bold=bold)
        return self.fonts[key]

    def display_font(self, size, bold=True):
        key = ("display", size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("Noto Serif Display", size, bold=bold)
        return self.fonts[key]

    def loop_music(self, path, enabled, volume):
        if not enabled:
            pygame.mixer.music.stop()
            return False
        if not path or not path.exists(): return False
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(-1)
            return True
        except pygame.error:
            return False
    def play_music(self, enabled, volume):
        path = ASSETS / "menu_music.wav"
        if pygame.mixer.music.get_busy() and enabled: return
        self.loop_music(path, enabled, volume)
    def place_music_path(self, place_id, night=False):
        folder_candidates = sorted((DATA / "places").glob(f"*_{place_id}"))
        period = "night" if night else "day"
        for folder in folder_candidates:
            tracks = sorted((folder / "music" / period).glob("*.wav"))
            if tracks: return tracks[0]
        universal = ASSETS / "duel_music.wav"
        return universal if universal.exists() else None
    def play_duel_music(self, place_id, enabled, volume=0.35, night=False):
        return self.loop_music(self.place_music_path(place_id, night), enabled, volume)
    def play_reaction_audio(self, path, enabled=True, volume=0.8):
        if not enabled or not path or not Path(path).exists(): return False
        try:
            sound = self.reaction_sounds.get(str(path))
            if sound is None:
                sound = pygame.mixer.Sound(str(path))
                if len(self.reaction_sounds) >= 128: self.reaction_sounds.pop(next(iter(self.reaction_sounds)))
                self.reaction_sounds[str(path)] = sound
            sound.set_volume(volume)
            sound.play()
            return True
        except pygame.error: return False


@dataclass
class CardDef:
    id: str
    name: str
    kind: str
    frame: str
    stars: int
    atk: int
    defense: int
    family: str
    description: str
    effects: list = field(default_factory=list)
    art_color: tuple = (50, 90, 150)
    legendary: bool = False
    limit: int = 3
    logic_graph: str = ""
    targets: list = field(default_factory=lambda: ["none"])
    target_count: int = 0
    timing: str = "main"
    field_effect: dict = field(default_factory=dict)
    materials: list = field(default_factory=list)
    ritual_cost: int = 0
    summon_method: str = "normal"
    media_folder: str = ""
    art_folder: str = ""
    art_variant: int = 1
    frame_schema: str = "classic_card_v1"
    summon_procedure: dict = field(default_factory=dict)


@dataclass
class CharacterDef:
    id: str
    name: str
    portrait: str
    stars: int
    smartness: int
    relationship: str
    preferred_families: list
    deck_id: str
    mood: str = "neutral"
    allies: list = field(default_factory=list)
    enemies: list = field(default_factory=list)
    history: list = field(default_factory=list)
    library_cards: list = field(default_factory=list)
    gender: str = "other"
    origin: str = "human"
    best_cards: list = field(default_factory=list)
    borrowed_cards: list = field(default_factory=list)
    rank: int = 1
    media_folder: str = ""
    availability: str = "free"
    current_place: str = ""
    destination: str = ""
    movement_progress: float = 0.0
    activity: str = "idle"
    cooldown_until: float = 0.0
    behavior_weights: dict = field(default_factory=dict)
    learned_cards: dict = field(default_factory=dict)
    learned_opponents: dict = field(default_factory=dict)


@dataclass
class MenuSection:
    primary_id: str
    secondary: list = field(default_factory=list)
    selected: str = ""


@dataclass
class PlaceDef:
    id: str
    name: str
    capacity: int
    current_duels: int
    background: str
    day_night: bool
    media_folder: str = ""
    effects: list = field(default_factory=list)
    event_response_policies: dict = field(default_factory=dict)
    event_window_policies: dict = field(default_factory=dict)
    trigger_order_policies: dict = field(default_factory=dict)


@dataclass
class TeamDef:
    id: str
    name: str
    members: list
    leader: str
    preferred_places: list = field(default_factory=list)
    relationship: str = "neutral"
    team_effect: dict = field(default_factory=dict)
    effect_locked: bool = False
    rank: int = 1
    history: list = field(default_factory=list)
    media_folder: str = ""


@dataclass
class MediaCue:
    cue_id: str
    at: float
    duration: float
    image: str = ""
    audio: str = ""
    mode: str = "loop"


class MediaTimeline:
    def __init__(self, cues=None):
        self.cues = sorted(cues or [], key=lambda cue: cue.at)

    @classmethod
    def load(cls, path):
        data = read_json(path, {"cues": []})
        return cls([MediaCue(**cue) for cue in data.get("cues", [])])

    def active(self, clock):
        return [cue for cue in self.cues if cue.at <= clock < cue.at + cue.duration]

    def to_dict(self):
        return {"cues": [cue.__dict__ for cue in self.cues]}


class MediaRegistry:
    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    audio_extensions = {".wav", ".ogg", ".mp3", ".flac"}
    video_extensions = {".mp4", ".webm", ".mov"}

    def __init__(self, root):
        self.root = Path(root)
        self.catalog = {"images": [], "audio": [], "video": [], "timelines": []}
        self.scan()

    def scan(self):
        self.catalog = {"images": [], "audio": [], "video": [], "timelines": []}
        roots = [self.root / "data"] if (self.root / "data").exists() else [self.root]
        if not roots: roots = [self.root]
        for base in roots:
            for path in base.rglob("*"):
                if not path.is_file(): continue
                suffix = path.suffix.lower()
                if suffix in self.image_extensions: self.catalog["images"].append(str(path))
                elif suffix in self.audio_extensions: self.catalog["audio"].append(str(path))
                elif suffix in self.video_extensions: self.catalog["video"].append(str(path))
                elif path.name.endswith("timeline.json"): self.catalog["timelines"].append(str(path))
        for values in self.catalog.values(): values[:] = sorted(set(values))
        return self.catalog

    def entity_path(self, entity_type, entity_id):
        base = self.root / "data" / entity_type
        direct = base / entity_id
        if direct.exists(): return direct
        for folder in base.glob("*"):
            manifest = folder / "manifest.json"
            if manifest.exists():
                try:
                    if json.loads(manifest.read_text()).get("id") == entity_id: return folder
                except (OSError, ValueError): pass
        return direct

    def entity_files(self, entity_id, category):
        return [path for path in self.catalog.get(category, []) if entity_id in Path(path).parts or entity_id in Path(path).stem]

    def card_art(self, card, variant=1):
        root = self.root / "data" / (card.media_folder or card.art_folder)
        candidates = [root / "art" / "variants" / f"{int(variant)}.png", root / "art" / "variants" / f"{int(variant)}.jpg", root / "images" / f"{int(variant)}.png", root / "images" / f"{int(variant)}.jpg"]
        for candidate in candidates:
            if candidate.exists(): return str(candidate)
        return ""

    def summary(self):
        return {key: len(value) for key, value in self.catalog.items()}


@dataclass
class ReactionSelection:
    event: str
    actor_id: str
    target_id: str
    relation: str
    source: str
    variant: int
    image: str = ""
    audio: str = ""
    mode: str = "hang"
    placeholder: bool = False

    def to_dict(self):
        return self.__dict__.copy()


class ReactionResolver:
    image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    audio_extensions = {".wav", ".ogg", ".mp3", ".flac"}

    def __init__(self, registry):
        self.registry = registry

    def numbered(self, folder, extensions):
        found = {}
        if not folder.exists(): return found
        for path in folder.iterdir():
            if not path.is_file() or path.suffix.lower() not in extensions: continue
            match = re.fullmatch(r"(10|[1-9])", path.stem)
            if match: found[int(match.group(1))] = str(path)
        return found

    def roots(self, event, relation, entity_type, entity_id, place_id):
        roots = []
        if entity_type == "characters" and entity_id:
            entity_root = self.registry.entity_path("characters", entity_id)
            roots.append(entity_root / "duel" / "reactions" / relation / event)
            roots.append(entity_root / "duel" / "reactions" / "neutral" / event)
        if entity_type == "cards" and entity_id: roots.append(self.registry.entity_path("cards", entity_id) / "interactions" / event)
        if entity_type == "places" and entity_id: roots.append(self.registry.entity_path("places", entity_id) / "presentation" / event)
        if place_id: roots.append(self.registry.entity_path("places", place_id) / "presentation" / event)
        roots.append(DATA / "animations" / event)
        roots.append(DATA / "audio" / event)
        return roots

    def resolve(self, event, actor_id="", target_id="", relation="opponent", entity_type="characters", entity_id="", place_id="", mode="hang"):
        entity_id = entity_id or actor_id
        for root in self.roots(event, relation, entity_type, entity_id, place_id):
            images = self.numbered(root, self.image_extensions)
            audios = self.numbered(root, self.audio_extensions)
            variants = sorted(set(images) | set(audios))
            if not variants: continue
            paired = sorted(set(images) & set(audios))
            variant = paired[0] if paired else variants[0]
            return ReactionSelection(event, actor_id, target_id, relation, str(root), variant, images.get(variant, ""), audios.get(variant, ""), mode, False)
        return ReactionSelection(event, actor_id, target_id, relation, "placeholder", 0, "", "", mode, True)


class ReactionPlayer:
    def __init__(self):
        self.selection = None
        self.clock = 0.0
        self.duration = 0.0
        self.frame_count = 1
        self.finished = True

    def start(self, selection, duration=2.0):
        self.selection = selection
        self.clock = 0.0
        self.duration = max(0.01, float(duration))
        self.frame_count = 1
        if selection.image:
            folder = Path(selection.image).parent
            self.frame_count = max(1, len([path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in MediaRegistry.image_extensions and re.fullmatch(r"(10|[1-9])", path.stem)]))
        self.finished = False

    def update(self, dt):
        if not self.selection or self.finished: return
        self.clock += dt
        if self.selection.mode in ["once", "strict-sync"] and self.clock >= self.duration: self.finished = True

    def state(self):
        if not self.selection: return {"active": False}
        frame_index = int(self.clock / self.duration * self.frame_count) % self.frame_count
        return {"active": not self.finished, "event": self.selection.event, "variant": self.selection.variant, "image": self.selection.image, "audio": self.selection.audio, "mode": self.selection.mode, "placeholder": self.selection.placeholder, "clock": round(self.clock, 3), "frame_count": self.frame_count, "frame_index": frame_index, "sync_ratio": round(self.frame_count / self.duration, 3)}


@dataclass
class LogicNode:
    node_id: str
    kind: str
    label: str
    value: str
    level: int
    x: int
    y: int
    inputs: list = field(default_factory=list)


@dataclass
class LogicGraph:
    name: str
    nodes: list = field(default_factory=list)

    def to_dict(self):
        return {"name": self.name, "nodes": [node.__dict__ for node in self.nodes]}

    @classmethod
    def from_dict(cls, data):
        nodes = [LogicNode(**node) for node in data.get("nodes", [])]
        return cls(data.get("name", "Unnamed Logic"), nodes)


@dataclass
class EffectSpec:
    effect_id: str
    trigger: str
    window: dict = field(default_factory=dict)
    conditions: list = field(default_factory=list)
    costs: list = field(default_factory=list)
    selector: dict = field(default_factory=dict)
    targets: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    modifier: dict = field(default_factory=dict)
    once: str = ""
    priority: int = 0
    notify: dict = field(default_factory=dict)
    media: dict = field(default_factory=dict)
    target_policy: dict = field(default_factory=dict)
    speed: int = 1
    response: dict = field(default_factory=dict)
    legacy: bool = False
    optional: bool = False

    action_names = {"boost_attack", "boost_defense", "damage", "heal", "draw", "discard", "grant_normal_summon", "banish", "send_to_graveyard", "return_to_hand", "set_face_up", "set_face_down", "switch_position", "destroy", "control", "summon", "special_summon", "fusion_summon", "ritual_summon", "negate_chain", "shuffle"}
    implemented_actions = {"boost_attack", "boost_defense", "damage", "heal", "draw", "discard", "grant_normal_summon", "banish", "send_to_graveyard", "return_to_hand", "set_face_up", "set_face_down", "switch_position", "destroy", "control", "summon", "special_summon", "negate_chain", "shuffle"}
    phases = {"draw", "standby", "main", "battle", "end", "any"}
    once_policies = {"", "once", "once_per_duel", "once_per_turn", "per_turn"}

    @classmethod
    def canonical_action(cls, value):
        text = str(value or "").strip().lower().replace("-", "_")
        text = {"special summon": "special_summon", "fusion summon": "fusion_summon", "ritual summon": "ritual_summon"}.get(text, text)
        match = re.fullmatch(r"([a-z_]+)(?:\s+([-+]?\d+))?", text)
        if not match: return {"name": "", "amount": 0, "raw": text, "valid": False}
        name, amount = match.groups()
        name = {"boost": "boost_attack", "increase_attack": "boost_attack", "increase_defense": "boost_defense", "graveyard": "send_to_graveyard", "negate": "negate_chain", "negate_link": "negate_chain", "negate_chain_link": "negate_chain"}.get(name, name)
        return {"name": name, "amount": int(amount or 0), "raw": text, "valid": name in cls.action_names}

    @classmethod
    def from_dict(cls, data, fallback_id="effect"):
        raw = dict(data or {})
        legacy = any(key in raw for key in ["action", "amount", "field_effect", "target_count", "timing"]) and not raw.get("actions")
        trigger = str(raw.get("trigger", raw.get("event", "manual")))
        window = dict(raw.get("window") or {})
        if raw.get("timing") and "event" not in window: window["event"] = raw.get("timing")
        if raw.get("phase") and "phase" not in window: window["phase"] = raw.get("phase")
        if not window: window = {"phase": "any", "event": trigger}
        actions = []
        if raw.get("actions"):
            for action in raw.get("actions", []):
                if isinstance(action, str): actions.append(cls.canonical_action(action))
                else:
                    item = dict(action)
                    parsed = cls.canonical_action(item.get("name", item.get("action", "")))
                    item["name"] = parsed["name"]
                    if "amount" not in item: item["amount"] = parsed["amount"]
                    item["valid"] = parsed["valid"]
                    actions.append(item)
        elif "action" in raw or "amount" in raw:
            parsed = cls.canonical_action(raw.get("action", ""))
            actions.append({"name": parsed["name"], "amount": raw.get("amount", parsed["amount"]), "target": raw.get("target", "source"), "valid": parsed["valid"]})
        selector = dict(raw.get("select") or raw.get("selector") or {})
        if raw.get("targets") and not selector:
            selector = {"target_groups": list(raw.get("targets", [])), "count": raw.get("target_count", 0)}
        targets = list(raw.get("targets") or [])
        if raw.get("target_count") and not targets: selector["count"] = raw.get("target_count")
        target_policy = dict(raw.get("target_policy") or raw.get("target_resolution") or {})
        if "revalidate" not in target_policy: target_policy["revalidate"] = not legacy
        response = dict(raw.get("response") or raw.get("chain") or {})
        speed = max(1, int(raw.get("speed", response.get("speed", 1)) or 1))
        modifier = dict(raw.get("modifier") or raw.get("field_effect") or {})
        if raw.get("field_effect") and not modifier.get("scope"): modifier["scope"] = "field"
        if raw.get("field_effect") and modifier.get("atk") is not None:
            modifier["stat"], modifier["operation"], modifier["amount"] = "attack", "add", modifier.pop("atk")
        return cls(str(raw.get("id", raw.get("effect_id", fallback_id))), trigger, window, list(raw.get("when", raw.get("conditions", [])) or []), list(raw.get("cost", raw.get("costs", [])) or []), selector, targets, actions, modifier, str(raw.get("once", "")), int(raw.get("priority", 0) or 0), dict(raw.get("notify") or {}), dict(raw.get("media") or {}), target_policy, speed, response, legacy, bool(raw.get("optional", raw.get("may_skip", False))))

    def capability_report(self):
        actions = []
        for action in self.actions:
            name = action.get("name", "")
            actions.append({"name": name, "status": "implemented" if name in self.implemented_actions else "declared_unsupported" if name in self.action_names else "unknown"})
        return {"effect_id": self.effect_id, "trigger": self.trigger, "actions": actions, "notifications": self.notify.get("kind", self.notify.get("type", "info")) if self.notify else "", "continuous": bool(self.modifier.get("continuous")) if self.modifier else False, "replacement": bool(self.modifier.get("replacement")) if self.modifier else False}

    def validate(self):
        errors = []
        if not self.effect_id: errors.append("effect id is required")
        if not self.trigger: errors.append(f"{self.effect_id}: trigger is required")
        phases = self.window.get("phase", "any")
        phases = phases if isinstance(phases, list) else [phases]
        if any(str(phase) not in self.phases for phase in phases): errors.append(f"{self.effect_id}: unsupported phase window")
        if not self.actions and not self.modifier: errors.append(f"{self.effect_id}: action or modifier is required")
        if self.once not in self.once_policies: errors.append(f"{self.effect_id}: unsupported once policy {self.once}")
        if self.speed not in [1, 2, 3]: errors.append(f"{self.effect_id}: unsupported speed {self.speed}")
        if not isinstance(self.optional, bool): errors.append(f"{self.effect_id}: optional must be boolean")
        if self.modifier:
            try: layer = int(self.modifier.get("layer", 4))
            except (TypeError, ValueError): layer = 4
            if layer < 0: errors.append(f"{self.effect_id}: modifier layer must be non-negative")
            replacement = self.modifier.get("replacement") or {}
            if replacement and str(replacement.get("operation", "reduce")).lower() not in ["reduce", "set", "replace", "multiply", "scale", "increase", "add", "prevent", "negate", "cancel", "cap", "maximum"]: errors.append(f"{self.effect_id}: unsupported replacement operation")
        for action in self.actions:
            name = action.get("name")
            if name not in self.action_names: errors.append(f"{self.effect_id}: unknown action {name}")
            elif name not in self.implemented_actions: errors.append(f"{self.effect_id}: action {name} is declared but not implemented")
        if self.notify:
            kind = self.notify.get("kind", self.notify.get("type", "info"))
            if kind not in {"ok", "yes_no", "choose_target", "choose_cards", "choose_trigger_order", "chain_response", "info"}: errors.append(f"{self.effect_id}: unsupported notification {kind}")
        return list(dict.fromkeys(errors))

    def to_dict(self):
        return {"id": self.effect_id, "trigger": self.trigger, "window": self.window, "when": self.conditions, "cost": self.costs, "select": self.selector, "targets": self.targets, "actions": self.actions, "modifier": self.modifier, "optional": self.optional, "once": self.once, "priority": self.priority, "notify": self.notify, "media": self.media, "target_policy": self.target_policy, "speed": self.speed, "response": self.response}


@dataclass
class ProcedureSpec:
    kind: str
    material_selector: dict = field(default_factory=dict)
    required_card_ids: list = field(default_factory=list)
    min_stars: int = 0
    locations: list = field(default_factory=lambda: ["hand", "monster"])
    exact: bool = False
    material_destination: str = "graveyard"
    source_selector: dict = field(default_factory=dict)
    source_method: str = ""
    required_count: int = 0
    costs: list = field(default_factory=list)
    special: bool = False

    @classmethod
    def normal_tribute(cls, card, rules=None):
        stars = int(card.card.stars)
        policy = dict((rules or {}).get("summoning", {}).get("normal_tribute", {}) or {})
        selected = None
        for tier in policy.get("tiers", []):
            if int(tier.get("min_stars", 0)) <= stars <= int(tier.get("max_stars", 99)):
                selected = tier
                break
        selected = selected or {"required_count": 0 if stars <= 4 else 1 if stars <= 6 else 2}
        special = bool(selected.get("special", False))
        count = int(selected.get("required_count", 0) or 0)
        return cls("tribute", {}, [], 0, ["monster"], False, "graveyard", {"zone": "hand"}, "normal", count, [], special)

    @classmethod
    def from_card(cls, card):
        raw = dict(getattr(card.card, "summon_procedure", {}) or {})
        method = str(getattr(card.card, "summon_method", "normal") or "normal")
        kind = str(raw.get("kind", method) or method)
        required = list(raw.get("required_card_ids", raw.get("materials", getattr(card.card, "materials", []))) or [])
        selector = dict(raw.get("material_selector", raw.get("selector", {})) or {})
        minimum = int(raw.get("min_stars", raw.get("ritual_cost", getattr(card.card, "ritual_cost", 0))) or 0)
        locations = list(raw.get("locations", ["hand", "monster"]) or ["hand", "monster"])
        exact = bool(raw.get("exact", kind == "fusion" and bool(required)))
        destination = str(raw.get("material_destination", "graveyard") or "graveyard")
        default_source = {"zone": "extra"} if kind == "fusion" else {"zone": "hand"}
        source_selector = dict(raw.get("source_selector", default_source) or default_source)
        source_method = str(raw.get("source_method", kind) or kind)
        derived_count = 0 if int(getattr(card.card, "stars", 0)) <= 4 else 1 if int(getattr(card.card, "stars", 0)) <= 6 else 2
        required_count = int(raw.get("required_count", raw.get("count", derived_count if kind == "tribute" else 0)) or 0)
        costs = raw.get("costs", raw.get("cost", [])) or []
        if isinstance(costs, dict): costs = [costs]
        return cls(kind, selector, required, minimum, locations, exact, destination, source_selector, source_method, required_count, list(costs), bool(raw.get("special", False)))


class LogicRuntime:
    action_names = {"boost_attack", "boost_defense", "damage", "heal", "draw", "banish", "send_to_graveyard", "return_to_hand"}
    node_kinds = {"trigger", "condition", "action"}

    def __init__(self, graphs):
        self.graphs = graphs

    @classmethod
    def normalize_action(cls, value):
        return EffectSpec.canonical_action(value)

    @classmethod
    def validate_graph(cls, graph):
        errors = []
        seen = set()
        for node in graph.nodes:
            if node.node_id in seen: errors.append(f"duplicate node id: {node.node_id}")
            seen.add(node.node_id)
            if node.kind not in cls.node_kinds: errors.append(f"unsupported node kind: {node.kind}")
            if node.kind == "action" and not cls.normalize_action(node.value)["valid"]: errors.append(f"unsupported action: {node.value}")
            if node.level < 1: errors.append(f"invalid level: {node.node_id}")
        for node in graph.nodes:
            for parent in node.inputs:
                if parent not in seen: errors.append(f"missing input {parent} for {node.node_id}")
        visiting, visited = set(), set()
        by_id = {node.node_id: node for node in graph.nodes}
        def visit(node_id):
            if node_id in visiting: return True
            if node_id in visited: return False
            visiting.add(node_id)
            cycle = any(visit(parent) for parent in by_id[node_id].inputs if parent in by_id)
            visiting.remove(node_id)
            visited.add(node_id)
            return cycle
        if any(visit(node.node_id) for node in graph.nodes): errors.append("logic graph contains a cycle")
        return list(dict.fromkeys(errors))

    def run(self, trigger, context):
        outcomes = []
        card = context.get("card")
        for graph_key, graph in self.graphs.items():
            if card and getattr(card.card, "logic_graph", "") != graph_key: continue
            if self.validate_graph(graph): continue
            nodes = sorted(graph.nodes, key=lambda node: (node.level, node.node_id))
            active = set()
            for node in nodes:
                if not all(parent in active for parent in node.inputs): continue
                if node.kind == "trigger" and node.value == trigger: active.add(node.node_id)
                elif node.kind == "condition" and self.condition(node.value, context): active.add(node.node_id)
                elif node.kind == "action":
                    active.add(node.node_id)
                    action = self.normalize_action(node.value)
                    outcomes.append({"graph": graph.name, "node": node.node_id, "value": node.value, "action": action["name"], "amount": action["amount"]})
        return outcomes

    def condition(self, expression, context):
        expression = str(expression or "").strip().lower()
        card = context.get("card")
        if expression in ("always", "true", "any"): return True
        match = re.fullmatch(r"card\.(family|kind|name)\s*==\s*(.+)", expression)
        if match and card:
            key, expected = match.groups()
            return str(getattr(card.card, key, "")).lower() == expected.strip().strip("\"'")
        match = re.fullmatch(r"card\.(stars|atk|defense)\s*(>=|<=|==|>|<)\s*(\d+)", expression)
        if match and card:
            key, operator, expected = match.groups()
            actual = int(getattr(card, key, getattr(card.card, key, 0)))
            expected = int(expected)
            return {">=": actual >= expected, "<=": actual <= expected, "==": actual == expected, ">": actual > expected, "<": actual < expected}[operator]
        match = re.fullmatch(r"(actor|target)\.hp\s*(>=|<=|==|>|<)\s*(\d+)", expression)
        if match:
            subject, operator, expected = match.groups()
            entity = context.get(subject)
            if not entity: return False
            actual, expected = int(entity.hp), int(expected)
            return {">=": actual >= expected, "<=": actual <= expected, "==": actual == expected, ">": actual > expected, "<": actual < expected}[operator]
        return False


class WorldClock:
    def now(self):
        current = time.localtime()
        return {"year": current.tm_year, "month": current.tm_mon, "day": current.tm_mday, "hour": current.tm_hour, "minute": current.tm_min}

    def period(self):
        hour = time.localtime().tm_hour
        return "night" if hour < 6 or hour >= 18 else "day"

    def label(self):
        return time.strftime("%Y-%m-%d %H:%M")


class ContentStore:
    def __init__(self):
        ensure_dirs()
        self.cards = {}
        self.characters = {}
        self.decks = {}
        self.places = {}
        self.teams = {}
        self.logic = {}
        stored_profile = read_json(SAVE, {})
        profile_defaults = {"active_user_id": "", "active_user_folder": "", "fullscreen": False, "resolution": "1280x720", "music": True, "sfx": True, "vocals": True, "difficulty": "normal", "setup_complete": False}
        self.save_data = {key: stored_profile.get(key, default) for key, default in profile_defaults.items()}
        self.media = MediaRegistry(ROOT)
        self.clock = WorldClock()
        self.dirty_domains = set()
        self.world_tick_active = False
        self.world_checkpoint_elapsed = 0.0
        self.world_checkpoint_interval = 15.0
        self.world_sessions = {}
        self.rules = read_json(DATA / "rules.json", {})
        self.world = read_json(DATA / "world.json", {"requests": [], "orders": [], "championships": [], "trades": [], "borrows": [], "achievements": [], "ranks": {}, "simulation_time": 0.0, "active_battles": [], "simulation_events": [], "place_occupancy": {}})
        for key, default in [("requests", []), ("orders", []), ("championships", []), ("trades", []), ("borrows", []), ("achievements", []), ("ranks", {}), ("simulation_time", 0.0), ("active_battles", []), ("simulation_events", []), ("last_ai_request_time", 0.0), ("place_occupancy", {})]: self.world.setdefault(key, default)
        self.load()

    def role_config(self):
        roles = self.world.get("roles", {}) if isinstance(self.world, dict) else {}
        character_ids = sorted(self.characters)
        active_user_id = self.save_data.get("active_user_id", "")
        player_id = active_user_id if active_user_id in self.characters else roles.get("player_character") if roles.get("player_character") in self.characters else (character_ids[0] if character_ids else "")
        opponent_id = roles.get("default_opponent_character") if roles.get("default_opponent_character") in self.characters else next((item for item in character_ids if item != player_id), player_id)
        team_ids = sorted(self.teams)
        player_team_id = roles.get("default_player_team") if roles.get("default_player_team") in self.teams else next((item.id for item in self.teams.values() if player_id in item.members), team_ids[0] if team_ids else "")
        opponent_team_id = roles.get("default_opponent_team") if roles.get("default_opponent_team") in self.teams else next((item for item in team_ids if item != player_team_id), player_team_id)
        place_ids = sorted(self.places)
        place_id = roles.get("default_place") if roles.get("default_place") in self.places else (place_ids[0] if place_ids else "")
        return {"player_character": player_id, "default_opponent_character": opponent_id, "default_player_team": player_team_id, "default_opponent_team": opponent_team_id, "default_place": place_id}

    def runtime_path(self, category, entity_id):
        root = RUNTIME_CHARACTERS if category == "characters" else RUNTIME_TEAMS
        return root / f"{entity_id}.json"

    def migrate_runtime_state(self, entries, category, fields):
        for entry in entries:
            entity_id = entry.get("id", "")
            if not entity_id: continue
            path = self.runtime_path(category, entity_id)
            if path.exists(): continue
            state = {key: entry[key] for key in fields if key in entry}
            write_json(path, {"schema": 1, "id": entity_id, "category": category, "state": state})

    def overlay_runtime_state(self, entry, category, fields):
        result = dict(entry)
        path = self.runtime_path(category, entry.get("id", ""))
        stored = read_json(path, {}) if path.exists() else {}
        state = stored.get("state", stored) if isinstance(stored, dict) else {}
        for key in fields:
            if key in state: result[key] = state[key]
        return result

    def migrate_world_state(self, legacy):
        stored = read_json(RUNTIME_WORLD_INDEX, {}) if RUNTIME_WORLD_INDEX.exists() else {}
        state = stored.get("state", stored) if isinstance(stored, dict) else {}
        state = dict(state) if isinstance(state, dict) else {}
        for key in ["requests", "orders", "championships", "trades", "borrows", "achievements", "ranks", "simulation_time", "active_battles", "simulation_events", "last_ai_request_time"]:
            path = RUNTIME_WORLD_COLLECTIONS / f"{key}.json"
            if not path.exists(): continue
            payload = read_json(path, {})
            value = payload.get("value", payload.get("state", payload)) if isinstance(payload, dict) else payload
            state[key] = value
        merged = dict(legacy)
        merged.update(state)
        authored_roles = legacy.get("roles", {}) if isinstance(legacy.get("roles", {}), dict) else {}
        runtime_roles = state.get("roles", {}) if isinstance(state.get("roles", {}), dict) else {}
        merged["roles"] = {**runtime_roles, **authored_roles}
        return merged

    def authored_entry(self, entity, runtime_fields):
        return {key: value for key, value in entity.__dict__.items() if key not in runtime_fields}

    def runtime_entry(self, entity, runtime_fields):
        return {key: getattr(entity, key) for key in runtime_fields if hasattr(entity, key)}

    def place_from_entry(self, entry):
        values = dict(entry)
        current_duels = int(values.pop("current_duels", 0) or 0)
        return PlaceDef(current_duels=current_duels, **values)

    def sync_place_runtime(self):
        self.world["place_occupancy"] = {place.id: int(place.current_duels) for place in self.places.values()}

    def load(self):
        cards_data = read_json(DATA / "cards.json", [])
        character_data = read_json(DATA / "characters.json", [])
        team_data = read_json(DATA / "teams.json", [])
        self.migrate_runtime_state(character_data, "characters", CHARACTER_RUNTIME_FIELDS)
        self.migrate_runtime_state(team_data, "teams", TEAM_RUNTIME_FIELDS)
        self.cards = {entry["id"]: CardDef(**entry) for entry in cards_data}
        self.characters = {entry["id"]: CharacterDef(**self.overlay_runtime_state(entry, "characters", CHARACTER_RUNTIME_FIELDS)) for entry in character_data}
        self.decks = read_json(DATA / "decks.json", {})
        for character in self.characters.values():
            if not character.library_cards: character.library_cards = list(self.decks.get(character.deck_id, {}).get("cards", []))[:6]
        for deck in self.decks.values(): deck["cards"] = DeckRules.normalized(deck.get("cards", []), self.cards)
        self.places = {entry["id"]: self.place_from_entry(entry) for entry in read_json(DATA / "places.json", [])}
        self.teams = {entry["id"]: TeamDef(**self.overlay_runtime_state(entry, "teams", TEAM_RUNTIME_FIELDS)) for entry in team_data}
        legacy_world = read_json(DATA / "world.json", {"requests": [], "orders": [], "championships": [], "trades": [], "borrows": [], "achievements": [], "ranks": {}, "simulation_time": 0.0, "active_battles": [], "simulation_events": [], "place_occupancy": {}})
        self.world = self.migrate_world_state(legacy_world)
        for key, default in [("requests", []), ("orders", []), ("championships", []), ("trades", []), ("borrows", []), ("achievements", []), ("ranks", {}), ("simulation_time", 0.0), ("active_battles", []), ("simulation_events", []), ("last_ai_request_time", 0.0), ("place_occupancy", {})]: self.world.setdefault(key, default)
        occupancy = self.world.get("place_occupancy", {}) if isinstance(self.world, dict) else {}
        for place in self.places.values(): place.current_duels = int(occupancy.get(place.id, place.current_duels) or 0)
        self.sync_place_runtime()
        if not isinstance(self.world.get("last_ai_request_time"), (int, float)): self.world["last_ai_request_time"] = 0.0
        self.rules = read_json(DATA / "rules.json", self.rules if isinstance(self.rules, dict) else {})
        self.logic = {}
        for path in (DATA / "logic").glob("*.json"):
            self.logic[path.stem] = LogicGraph.from_dict(read_json(path, {}))
        self.ensure_behavior_weights()
        self.ensure_entity_scaffolds()
        self.media.scan()
        self.world_sessions = {}
        self.dirty_domains.clear()
        self.world_checkpoint_elapsed = 0.0

    def ensure_behavior_weights(self):
        defaults = {"risk_tolerance": 3.0, "learning_value": 5.0, "rematch_desire": 4.0, "reward_value": 5.0, "place_preference": 5.0, "ally_bias": 4.0, "enemy_bias": 6.0, "adaptation": 1.0}
        for character in self.characters.values():
            for key, value in defaults.items(): character.behavior_weights.setdefault(key, value)
            family_weights = character.behavior_weights.setdefault("family_weights", {})
            for family in [card.family for card in self.cards.values()]: family_weights.setdefault(family, 2.0 if family in character.preferred_families else 0.0)
            character.behavior_weights.setdefault("state_weights", {"stranger": 1.0, "ally": 0.5, "enemy": 2.0, "opponent": 1.0})
            character.behavior_weights.setdefault("phase_weights", {"MAIN 1": 1.0, "MAIN 2": 1.0, "BATTLE": 1.0})
            character.behavior_weights.setdefault("duel", {"summon_bias": 1.0, "set_bias": 1.0, "activation_bias": 1.0, "removal_bias": 1.0, "defense_bias": 1.0, "attack_bias": 1.0, "trap_threshold": 0.0})
            character.learned_cards = {str(key): int(value) for key, value in character.learned_cards.items()}
            character.learned_opponents = {str(key): int(value) for key, value in character.learned_opponents.items()}

    def relationship_for(self, character_id, other_id):
        character = self.characters.get(character_id)
        if not character or character_id == other_id: return "stranger"
        if other_id in character.enemies: return "enemy"
        if other_id in character.allies: return "ally"
        return "stranger"

    def _relationship_score(self, character, other):
        relation = self.relationship_for(character.id, other.id)
        if relation == "enemy": return float(character.behavior_weights.get("enemy_bias", 6.0))
        if relation == "ally": return float(character.behavior_weights.get("ally_bias", 4.0))
        return 5.0

    def choose_ai_opponent(self, character_id):
        character = self.characters.get(character_id)
        player_id = self.role_config()["player_character"]
        candidates = [other for other in self.characters.values() if other.id != character_id and other.id != player_id and other.availability == "free" and float(other.cooldown_until) <= float(self.world.get("simulation_time", 0.0))]
        if not character or not candidates: return None
        def score(other):
            history = [event for event in character.history if event.get("opponent") == other.id]
            losses = sum(1 for event in history if event.get("result") == "loss")
            wins = sum(1 for event in history if event.get("result") == "win")
            known = float(character.learned_opponents.get(other.id, 0))
            challenge = abs(int(other.stars) - int(character.stars)) * float(character.behavior_weights.get("learning_value", 5.0))
            rematch = losses * float(character.behavior_weights.get("rematch_desire", 4.0)) - wins
            return self._relationship_score(character, other) + challenge + rematch - known * float(character.behavior_weights.get("adaptation", 1.0))
        return max(candidates, key=lambda other: (score(other), other.id))

    def schedule_ai_request(self, character_id):
        character = self.characters.get(character_id)
        target = self.choose_ai_opponent(character_id)
        if not character or not target or character.availability != "free": return None
        if any(entry.get("status") in ["open", "queued", "active"] and entry.get("from") == character_id for entry in self.world.setdefault("requests", [])): return None
        reason = "rematch study" if character.learned_opponents.get(target.id, 0) else "study duel"
        return self.add_request(character_id, target.id, reason, kind="learning", format_name="1v1", preferred_place=self.role_config()["default_place"], relationship_intent="stranger", expires_in=10800)

    def _ai_request_tick(self):
        if float(self.world.get("simulation_time", 0.0)) < float(self.world.get("last_ai_request_time", 0.0)) + 10.0: return
        self.world["last_ai_request_time"] = float(self.world.get("simulation_time", 0.0))
        for character in sorted(self.characters.values(), key=lambda item: item.id):
            if character.id != self.role_config()["player_character"] and character.availability == "free": self.schedule_ai_request(character.id)


    def save(self, domains=None):
        all_domains = {"authored", "runtime_characters", "runtime_teams", "runtime_world", "profile", "logic"}
        default_domains = {"runtime_characters", "runtime_teams", "runtime_world"} if self.world_tick_active else set(self.dirty_domains or all_domains)
        requested = set(domains) if domains is not None else default_domains
        if self.world_tick_active:
            self.dirty_domains.update(requested)
            return False
        if "authored" in requested:
            write_json(DATA / "cards.json", [card.__dict__ for card in self.cards.values()])
            write_json(DATA / "characters.json", [self.authored_entry(char, CHARACTER_RUNTIME_FIELDS) for char in self.characters.values()])
            write_json(DATA / "decks.json", self.decks)
            write_json(DATA / "places.json", [self.authored_entry(place, {"current_duels"}) for place in self.places.values()])
            write_json(DATA / "teams.json", [self.authored_entry(team, TEAM_RUNTIME_FIELDS) for team in self.teams.values()])
        if "runtime_characters" in requested:
            for char in self.characters.values(): write_json(self.runtime_path("characters", char.id), {"schema": 2, "id": char.id, "category": "characters", "state": self.runtime_entry(char, CHARACTER_RUNTIME_FIELDS)})
        if "runtime_teams" in requested:
            for team in self.teams.values(): write_json(self.runtime_path("teams", team.id), {"schema": 2, "id": team.id, "category": "teams", "state": self.runtime_entry(team, TEAM_RUNTIME_FIELDS)})
        if "runtime_world" in requested:
            self.sync_place_runtime()
            world_keys = ["requests", "orders", "championships", "trades", "borrows", "achievements", "ranks", "simulation_time", "active_battles", "simulation_events", "last_ai_request_time"]
            defaults = {"requests": [], "orders": [], "championships": [], "trades": [], "borrows": [], "achievements": [], "ranks": {}, "simulation_time": 0.0, "active_battles": [], "simulation_events": [], "last_ai_request_time": 0.0}
            for key in world_keys: write_json(RUNTIME_WORLD_COLLECTIONS / f"{key}.json", {"schema": 2, "category": "world_collection", "id": key, "value": self.world.get(key, defaults[key])})
            write_json(RUNTIME_WORLD_INDEX, {"schema": 2, "category": "world_index", "roles": self.world.get("roles", {}), "place_occupancy": self.world.get("place_occupancy", {}), "collections": world_keys})
        if "profile" in requested: write_json(SAVE, self.save_data)
        if "logic" in requested:
            for key, graph in self.logic.items(): write_json(DATA / "logic" / f"{key}.json", graph.to_dict())
        self.dirty_domains.difference_update(requested)
        return True

    def reserve_place(self, place_id):
        place = self.places.get(place_id)
        if not place or place.current_duels >= place.capacity: return False
        place.current_duels += 1
        self.sync_place_runtime()
        self.save()
        return True

    def release_place(self, place_id):
        place = self.places.get(place_id)
        if place:
            place.current_duels = max(0, place.current_duels - 1)
            self.sync_place_runtime()
            self.save()

    def world_context(self):
        return {"clock": self.clock.now(), "period": self.clock.period(), "label": self.clock.label(), "simulation_time": float(self.world.get("simulation_time", 0.0)), "places": {place.id: {"current": place.current_duels, "capacity": place.capacity} for place in self.places.values()}, "characters": {character.id: {"availability": character.availability, "place": character.current_place, "destination": character.destination, "progress": character.movement_progress, "activity": character.activity} for character in self.characters.values()}, "active_battles": len([battle for battle in self.world.setdefault("active_battles", []) if battle.get("status") == "active"])}

    def add_request(self, from_id, to_id, reason, kind="duel", format_name="1v1", preferred_place=None, relationship_intent="stranger", deck_id="", reward_policy="random_card", expires_in=10800):
        preferred_place = preferred_place or self.role_config()["default_place"]
        request_id = "request_" + str(int(time.time() * 1000))
        now = float(self.world.get("simulation_time", 0.0))
        request = {"id": request_id, "title": f"{from_id} requests a {reason}", "from": from_id, "to": to_id, "kind": kind, "reason": reason, "relationship_intent": relationship_intent, "format": format_name, "preferred_place": preferred_place, "deck_id": deck_id, "reward_policy": reward_policy, "status": "open", "created_sim_time": now, "expires_sim_time": now + max(1, float(expires_in)), "events": [{"status": "open", "actor": from_id, "sim_time": now}]}
        self.world.setdefault("requests", []).append(request)
        self.save()
        return request_id

    def request_by_id(self, request_id):
        return next((request for request in self.world.setdefault("requests", []) if request.get("id") == request_id), None)

    def respond_request(self, request_id, actor_id, decision):
        request = self.request_by_id(request_id)
        allowed = {"accept": "queued", "deny": "denied", "ignore": "ignored", "cancel": "canceled"}
        if not request or request.get("status") != "open" or actor_id not in [request.get("from"), request.get("to")] or decision not in allowed: return False
        status = allowed[decision]
        request["status"] = status
        request.setdefault("events", []).append({"status": status, "actor": actor_id, "sim_time": float(self.world.get("simulation_time", 0.0))})
        if status == "queued":
            request["queued_sim_time"] = float(self.world.get("simulation_time", 0.0))
            request["accepted_by"] = actor_id
            request["house_player"] = actor_id
            request["guest_player"] = request.get("to") if actor_id == request.get("from") else request.get("from")
        self.save()
        return True

    def move_character(self, character_id, destination, duration=5.0):
        character = self.characters.get(character_id)
        if not character or destination not in self.places or character.availability == "active": return False
        character.destination = destination
        character.movement_progress = 0.0
        character.activity = "moving"
        character.availability = "traveling"
        self.world.setdefault("simulation_events", []).append({"type": "movement_started", "character": character_id, "destination": destination, "sim_time": float(self.world.get("simulation_time", 0.0)), "duration": max(1.0, float(duration))})
        character.behavior_weights.setdefault("movement_duration", max(1.0, float(duration)))
        self.save()
        return True

    def _advance_movement(self, seconds):
        for character in self.characters.values():
            if character.activity != "moving" or not character.destination: continue
            duration = max(1.0, float(character.behavior_weights.get("movement_duration", 5.0)))
            character.movement_progress = min(1.0, character.movement_progress + seconds / duration)
            if character.movement_progress >= 1.0:
                character.current_place = character.destination
                character.destination = ""
                character.activity = "idle"
                character.availability = "free"
                self.world.setdefault("simulation_events", []).append({"type": "movement_arrived", "character": character.id, "place": character.current_place, "sim_time": float(self.world.get("simulation_time", 0.0))})

    def _request_ready_for_queue(self, request):
        if request.get("status") != "queued" or float(self.world.get("simulation_time", 0.0)) >= float(request.get("expires_sim_time", 0.0)): return False
        sender = self.characters.get(request.get("from"))
        recipient = self.characters.get(request.get("to"))
        if not sender or not recipient or sender.availability not in ["free", "traveling"] or recipient.availability not in ["free", "traveling"]: return False
        place_id = request.get("preferred_place") or self.role_config()["default_place"]
        place = self.places.get(place_id)
        return bool(place and place.current_duels < place.capacity and sender.activity != "moving" and recipient.activity != "moving")

    def _activate_queued_requests(self):
        for request in self.world.setdefault("requests", []):
            if not self._request_ready_for_queue(request): continue
            place_id = request.get("preferred_place") or self.role_config()["default_place"]
            if not self.reserve_place(place_id): continue
            request["status"] = "active"
            request.setdefault("events", []).append({"status": "active", "actor": "world", "sim_time": float(self.world.get("simulation_time", 0.0))})
            for character_id in [request.get("from"), request.get("to")]:
                character = self.characters.get(character_id)
                if character:
                    character.availability = "active"
                    character.activity = "dueling"
            house_id = request.get("house_player") or request.get("accepted_by") or request.get("to") or request.get("from")
            guest_id = request.get("guest_player") or (request.get("to") if house_id == request.get("from") else request.get("from"))
            engine = DuelEngine(self, house_id, guest_id, place_id, True)
            engine.match_recorded = True
            battle_id = "sim_battle_" + str(int(time.time() * 1000))
            battle = {"id": battle_id, "request_id": request["id"], "from": request["from"], "to": request["to"], "house": house_id, "guest": guest_id, "accepted_by": request.get("accepted_by", house_id), "format": request.get("format", "1v1"), "place": place_id, "status": "active", "phase": "pre_duel", "elapsed": 0.0, "next_action": 3.0, "turn": engine.turn, "actions": [], "hp": {house_id: engine.player.hp, guest_id: engine.opponent.hp}, "started_sim_time": float(self.world.get("simulation_time", 0.0)), "result": "", "engine_checkpoint": engine.state_checkpoint()}
            self.world_sessions[battle_id] = engine
            self.world.setdefault("active_battles", []).append(battle)
            self.world.setdefault("simulation_events", []).append({"type": "battle_activated", "battle": battle["id"], "request": request["id"], "sim_time": float(self.world.get("simulation_time", 0.0))})

    def _world_session(self, battle):
        session = self.world_sessions.get(battle["id"])
        if session: return session
        house_id = battle.get("house") or battle.get("accepted_by") or battle.get("to") or battle.get("from")
        guest_id = battle.get("guest") or (battle.get("to") if house_id == battle.get("from") else battle.get("from"))
        battle["house"], battle["guest"] = house_id, guest_id
        session = DuelEngine(self, house_id, guest_id, battle["place"], True)
        session.match_recorded = True
        checkpoint = battle.get("engine_checkpoint")
        if checkpoint and not session.restore_state_checkpoint(checkpoint): return None
        self.world_sessions[battle["id"]] = session
        return session

    def _complete_world_battle(self, battle, session):
        winner_id = session.winner.character.id if session.winner else ""
        loser_id = session.other(session.winner).character.id if session.winner else ""
        battle["status"] = "completed"
        battle["phase"] = "post_duel"
        battle["result"] = winner_id
        battle["turn"] = session.turn
        battle["hp"] = {battle["from"]: session.player.hp, battle["to"]: session.opponent.hp}
        request = self.request_by_id(battle["request_id"])
        if request:
            request["status"] = "completed"
            request.setdefault("events", []).append({"status": "completed", "actor": winner_id or "world", "sim_time": float(self.world.get("simulation_time", 0.0))})
        self.record_duel(winner_id, loser_id, session.turn, "engine_simulation")
        self.release_place(battle["place"])
        for character_id in [battle["from"], battle["to"]]:
            character = self.characters.get(character_id)
            if character:
                character.availability = "free"
                character.activity = "idle"
                character.cooldown_until = float(self.world.get("simulation_time", 0.0)) + 5.0
        self.world_sessions.pop(battle["id"], None)
        self.world.setdefault("simulation_events", []).append({"type": "battle_completed", "battle": battle["id"], "winner": winner_id or "draw", "loser": loser_id, "sim_time": float(self.world.get("simulation_time", 0.0))})

    def _simulation_action(self, battle):
        session = self._world_session(battle)
        if not session: return
        active_before = session.autonomous_actor()
        result = session.autonomous_step(active_before)
        battle["turn"] = session.turn
        battle["phase"] = "post_duel" if session.finished else session.phase.lower()
        battle["hp"] = {battle["from"]: session.player.hp, battle["to"]: session.opponent.hp}
        battle["engine_checkpoint"] = session.state_checkpoint()
        battle["actions"].append({"turn": session.turn, "actor": active_before.character.id, "phase": session.phase, "result": str(result[1] if isinstance(result, tuple) and len(result) > 1 else result), "sim_time": float(self.world.get("simulation_time", 0.0))})
        self.world.setdefault("simulation_events", []).append({"type": "battle_engine_step", "battle": battle["id"], "actor": active_before.character.id, "phase": session.phase, "sim_time": float(self.world.get("simulation_time", 0.0))})
        if session.finished: self._complete_world_battle(battle, session)

    def _advance_battles(self, seconds):
        for battle in list(self.world.setdefault("active_battles", [])):
            if battle.get("status") != "active": continue
            battle["elapsed"] = float(battle.get("elapsed", 0.0)) + seconds
            if battle["phase"] == "pre_duel" and battle["elapsed"] >= 3.0: battle["phase"] = "duel"
            actions = 0
            while battle["elapsed"] >= battle.get("next_action", 3.0) and actions < 3 and battle.get("status") == "active":
                self._simulation_action(battle)
                battle["next_action"] = float(battle.get("next_action", 3.0)) + 2.0
                actions += 1

    def advance_world(self, seconds):
        seconds = max(0.0, min(30.0, float(seconds)))
        checkpoint = False
        self.world_tick_active = True
        try:
            self.world["simulation_time"] = float(self.world.get("simulation_time", 0.0)) + seconds
            self._advance_movement(seconds)
            for request in self.world.setdefault("requests", []):
                if request.get("status") in ["open", "queued"] and self.world["simulation_time"] >= float(request.get("expires_sim_time", 0.0)):
                    request["status"] = "expired"
                    request.setdefault("events", []).append({"status": "expired", "actor": "world", "sim_time": self.world["simulation_time"]})
            self._advance_battles(seconds)
            self._activate_queued_requests()
            self._ai_request_tick()
            self.world["simulation_events"] = self.world.setdefault("simulation_events", [])[-200:]
            self.dirty_domains.update({"runtime_characters", "runtime_teams", "runtime_world"})
            self.world_checkpoint_elapsed += seconds
            checkpoint = self.world_checkpoint_elapsed >= self.world_checkpoint_interval
        finally:
            self.world_tick_active = False
        if checkpoint:
            self.world_checkpoint_elapsed = 0.0
            self.save({"runtime_characters", "runtime_teams", "runtime_world"})
        return self.world_context()

    def place_order(self, placer, taker, give):
        order_id = "order_" + str(int(time.time() * 1000))
        self.world.setdefault("orders", []).append({"id": order_id, "title": f"Order by {placer}: {give}", "placer": placer, "taker": taker, "give": give, "status": "open"})
        self.save()
        return order_id

    def close_world_entry(self, collection, entry_id):
        for entry in self.world.setdefault(collection, []):
            if entry.get("id") == entry_id:
                entry["status"] = "accepted"
                self.save()
                return entry
        return None

    def trade_list(self):
        trades = self.world.setdefault("trades", [])
        now = time.time()
        for trade in trades:
            if trade.get("state") in ["open", "countered"] and now >= trade.get("expires", 0): trade["state"] = "expired"
        self.save()
        return trades

    def card_names(self, card_ids):
        return ", ".join(self.cards[card_id].name for card_id in card_ids if card_id in self.cards) or "none"

    def owned_counts(self, character_id):
        character = self.characters.get(character_id)
        counts = {}
        if character:
            for card_id in character.library_cards: counts[card_id] = counts.get(card_id, 0) + 1
        return counts

    def create_trade(self, creator_id, recipient_id, offered_cards, requested_cards=None, requested_family=""):
        if creator_id not in self.characters or recipient_id not in self.characters or creator_id == recipient_id: return None
        offered_cards = list(offered_cards)[:3]
        counts = self.owned_counts(creator_id)
        if not offered_cards or any(counts.get(card_id, 0) < offered_cards.count(card_id) for card_id in set(offered_cards)): return None
        requested_cards = list(requested_cards or [])[:3]
        trade_id = "trade_" + str(int(time.time() * 1000))
        trade = {"id": trade_id, "creator": creator_id, "recipient": recipient_id, "offered_cards": offered_cards, "requested_cards": requested_cards, "requested_family": requested_family, "state": "open", "parent_id": "", "created": time.time(), "expires": time.time() + 10800, "history": [{"actor": creator_id, "action": "opened", "time": time.time()}], "ownership_transferred": False}
        self.world.setdefault("trades", []).append(trade)
        self.save()
        return trade

    def get_trade(self, trade_id):
        return next((trade for trade in self.world.setdefault("trades", []) if trade.get("id") == trade_id), None)

    def requested_cards_for(self, trade, character_id):
        counts = self.owned_counts(character_id)
        if trade.get("requested_cards"):
            requested = list(trade["requested_cards"])
            if any(counts.get(card_id, 0) < requested.count(card_id) for card_id in set(requested)): return []
            return requested
        family = trade.get("requested_family", "")
        return next(([card_id] for card_id in self.characters[character_id].library_cards if card_id in self.cards and self.cards[card_id].family == family), [])

    def trade_available(self, trade):
        if not trade or trade.get("state") not in ["open", "countered"] or time.time() >= trade.get("expires", 0): return False
        creator_counts = self.owned_counts(trade["creator"])
        return all(creator_counts.get(card_id, 0) >= trade["offered_cards"].count(card_id) for card_id in set(trade["offered_cards"])) and bool(self.requested_cards_for(trade, trade["recipient"]))

    def counter_trade(self, trade_id, actor_id, offered_cards, requested_cards=None, requested_family=""):
        parent = self.get_trade(trade_id)
        if not parent or parent.get("state") not in ["open", "countered"] or parent.get("recipient") != actor_id: return None
        counter = self.create_trade(actor_id, parent["creator"], offered_cards, requested_cards, requested_family)
        if counter:
            counter["state"] = "countered"
            counter["parent_id"] = parent["id"]
            counter["history"] = list(parent.get("history", [])) + [{"actor": actor_id, "action": "countered", "parent_id": parent["id"], "time": time.time()}]
            parent["state"] = "countered"
            parent["history"].append({"actor": actor_id, "action": "answered_with_counter", "child_id": counter["id"], "time": time.time()})
            self.save()
        return counter

    def accept_trade(self, trade_id, actor_id):
        trade = self.get_trade(trade_id)
        if not trade or trade.get("recipient") != actor_id or not self.trade_available(trade): return False
        requested = self.requested_cards_for(trade, actor_id)
        creator = self.characters[trade["creator"]]
        recipient = self.characters[trade["recipient"]]
        for card_id in trade["offered_cards"]: creator.library_cards.remove(card_id); recipient.library_cards.append(card_id)
        for card_id in requested: recipient.library_cards.remove(card_id); creator.library_cards.append(card_id)
        trade["requested_cards"] = requested
        trade["state"] = "accepted"
        trade["ownership_transferred"] = True
        trade["history"].append({"actor": actor_id, "action": "accepted", "time": time.time()})
        creator.history.append({"event": "trade", "trade_id": trade["id"], "with": recipient.id, "received": requested, "gave": trade["offered_cards"], "time": time.time()})
        recipient.history.append({"event": "trade", "trade_id": trade["id"], "with": creator.id, "received": trade["offered_cards"], "gave": requested, "time": time.time()})
        self.save()
        return True

    def cancel_trade(self, trade_id, actor_id):
        trade = self.get_trade(trade_id)
        if not trade or actor_id not in [trade.get("creator"), trade.get("recipient")] or trade.get("state") in ["accepted", "canceled", "expired", "duel_accepted"]: return False
        trade["state"] = "canceled"
        trade["history"].append({"actor": actor_id, "action": "canceled", "time": time.time()})
        self.save()
        return True

    def escalate_trade(self, trade_id, actor_id):
        trade = self.get_trade(trade_id)
        if not trade or actor_id not in [trade.get("creator"), trade.get("recipient")] or trade.get("state") not in ["open", "countered"]: return None
        trade["state"] = "escalated"
        request_id = self.add_request(actor_id, trade["creator"] if actor_id == trade["recipient"] else trade["recipient"], "high-stakes trade duel")
        trade["duel_request_id"] = request_id
        trade["history"].append({"actor": actor_id, "action": "escalated", "request_id": request_id, "time": time.time()})
        self.save()
        return request_id

    def borrow_card(self, lender_id, borrower_id, card_id, duels=1):
        if lender_id not in self.characters or borrower_id not in self.characters or lender_id == borrower_id or card_id not in self.cards: return None
        if self.owned_counts(lender_id).get(card_id, 0) < 1: return None
        borrow_id = "borrow_" + str(int(time.time() * 1000))
        record = {"id": borrow_id, "lender": lender_id, "borrower": borrower_id, "card_id": card_id, "remaining_duels": max(1, min(5, int(duels))), "state": "active", "created": time.time()}
        self.world.setdefault("borrows", []).append(record)
        self.characters[borrower_id].borrowed_cards.append(card_id)
        self.characters[borrower_id].history.append({"event": "borrow_started", "borrow_id": borrow_id, "card": card_id, "from": lender_id, "time": time.time()})
        self.save()
        return record

    def advance_borrows(self, character_id):
        changed = False
        for record in self.world.setdefault("borrows", []):
            if record.get("state") == "active" and record.get("borrower") == character_id:
                record["remaining_duels"] -= 1
                changed = True
                if record["remaining_duels"] <= 0:
                    record["state"] = "returned"
                    borrower = self.characters.get(character_id)
                    if borrower and record["card_id"] in borrower.borrowed_cards: borrower.borrowed_cards.remove(record["card_id"])
        if changed: self.save()

    def calculate_rank(self, entity_id):
        if entity_id in self.characters:
            character = self.characters[entity_id]
            wins = sum(1 for item in character.history if item.get("result") == "win")
            losses = sum(1 for item in character.history if item.get("result") == "loss")
            rank = clamp(1 + wins // 2 - losses // 3 + max(0, character.stars - 4) // 3, 1, 10)
        elif entity_id in self.teams:
            members = self.teams[entity_id].members
            rank = clamp(round(sum(self.calculate_rank(member) for member in members) / max(1, len(members))), 1, 10)
        else: rank = 1
        self.world.setdefault("ranks", {})[entity_id] = rank
        if entity_id in self.characters: self.characters[entity_id].rank = rank
        self.save()
        return rank

    def add_achievement(self, character_id, title, detail):
        achievement = {"id": "achievement_" + str(int(time.time() * 1000)), "character": character_id, "title": title, "detail": detail, "time": time.time()}
        self.world.setdefault("achievements", []).append(achievement)
        self.characters[character_id].history.append({"event": "achievement", "title": title, "detail": detail, "time": time.time()})
        self.save()
        return achievement

    def record_duel(self, winner_id, loser_id, turns, reason):
        winner = self.characters.get(winner_id) if winner_id else None
        loser = self.characters.get(loser_id) if loser_id else None
        transferred = ""
        if winner and loser:
            if loser.library_cards:
                transferred = loser.library_cards.pop(0)
                winner.library_cards.append(transferred)
            loser.smartness = clamp(loser.smartness + 1, 1, 10)
            winner.history.append({"opponent": loser.id, "result": "win", "turns": turns, "reason": reason, "cards_seen": list(self.decks.get(loser.deck_id, {}).get("cards", []))[:5], "traded_card": transferred, "time": time.time()})
            loser.history.append({"opponent": winner.id, "result": "loss", "turns": turns, "reason": reason, "cards_seen": list(self.decks.get(winner.deck_id, {}).get("cards", []))[:5], "traded_card": transferred, "time": time.time()})
            winner.history = winner.history[-20:]
            loser.history = loser.history[-20:]
            winner.learned_opponents[loser.id] = winner.learned_opponents.get(loser.id, 0) + 1
            loser.learned_opponents[winner.id] = loser.learned_opponents.get(winner.id, 0) + 1
            for card_id in list(self.decks.get(loser.deck_id, {}).get("cards", []))[:5]: winner.learned_cards[card_id] = winner.learned_cards.get(card_id, 0) + 1
            for card_id in list(self.decks.get(winner.deck_id, {}).get("cards", []))[:5]: loser.learned_cards[card_id] = loser.learned_cards.get(card_id, 0) + 1
            difficulty = self.save_data.get("difficulty", "normal")
            learning_delta = {"normal": 1, "hard": 2, "extreme": 3}.get(difficulty, 1)
            winner.behavior_weights["adaptation"] = min(10.0, float(winner.behavior_weights.get("adaptation", 1.0)) + learning_delta * 0.25)
            loser.behavior_weights["adaptation"] = min(10.0, float(loser.behavior_weights.get("adaptation", 1.0)) + learning_delta * 0.5)
            self.advance_borrows(winner.id)
            self.advance_borrows(loser.id)
            self.calculate_rank(winner.id)
            self.calculate_rank(loser.id)
            if loser.stars >= winner.stars + 2: self.add_achievement(winner.id, "Historic upset", f"Defeated {loser.name} despite the star gap.")
            self.save()
        return transferred

    def validate_effects(self, effects):
        errors = []
        seen = set()
        for index, raw in enumerate(effects or []):
            spec = EffectSpec.from_dict(raw, "effect_" + str(index))
            if spec.effect_id in seen: errors.append(f"duplicate effect id: {spec.effect_id}")
            seen.add(spec.effect_id)
            errors.extend(spec.validate())
            if spec.capability_report()["actions"]:
                for capability in spec.capability_report()["actions"]:
                    if capability["status"] != "implemented" and capability["status"] != "declared_unsupported": errors.append(f"{spec.effect_id}: capability report marks {capability['name']} as {capability['status']}")
        return list(dict.fromkeys(errors))

    def validate_card_definition(self, kind, stars, atk, defense, family, description, targets=None, target_count=0, timing="main", materials=None, ritual_cost=0, summon_method="normal", effects=None):
        errors = []
        monster_kinds = {"normal", "effect", "fusion", "ritual", "legendary"}
        if not str(family or "").strip(): errors.append("family is required")
        if not str(description or "").strip(): errors.append("description is required")
        if kind in monster_kinds and int(stars) < 1: errors.append("monster cards require at least one star")
        if kind not in monster_kinds and (int(stars) != 0 or int(atk) != 0 or int(defense) != 0): errors.append("non-monster cards cannot carry monster stats")
        if kind == "fusion" and (summon_method != "fusion" or not materials): errors.append("fusion cards require fusion summon mode and materials")
        if kind == "ritual" and (summon_method != "ritual" or int(ritual_cost) < 1): errors.append("ritual cards require ritual summon mode and a ritual cost")
        if kind not in ["fusion", "ritual"] and summon_method not in ["normal", ""]: errors.append("only fusion and ritual cards may use special summon modes")
        if int(target_count) > 0 and (not targets or targets == ["none"]): errors.append("target count requires a target type")
        if timing not in ["main", "opponent_attack", "any"]: errors.append("unsupported timing")
        errors.extend(self.validate_effects(effects or []))
        return list(dict.fromkeys(errors))

    def create_card(self, name, kind, stars, atk, defense, family, description, logic_graph="", targets=None, target_count=0, timing="main", field_effect=None, materials=None, ritual_cost=0, summon_method="normal", art_path="", effects=None):
        card_id = "card_" + str(int(time.time() * 1000))
        frame = "yellow" if kind == "normal" else "orange" if kind == "effect" else "sky" if kind in ["spell", "field"] else "pink" if kind == "trap" else "violet" if kind == "fusion" else "blue" if kind == "ritual" else "red"
        resolved_method = summon_method if summon_method != "normal" else kind if kind in ["fusion", "ritual"] else "normal"
        card = CardDef(card_id, name or "Unnamed Card", kind, frame, stars, atk, defense, family or "other", description or "A community-created card.", list(effects or []), (90, 120, 200), kind == "legendary", 1 if kind == "legendary" else 3, logic_graph, list(targets or ["none"]), int(target_count), timing, dict(field_effect or {}), list(materials or []), int(ritual_cost), resolved_method)
        card.media_folder = self.scaffold_entity("cards", card_id, name or "Unnamed Card", ["images", "interactions", "logic", "animations", "audio"])
        card.art_folder = card.media_folder
        source = Path(str(art_path)).expanduser() if art_path else None
        if source and source.exists() and source.is_file() and source.suffix.lower() in MediaRegistry.image_extensions:
            target = DATA / card.media_folder / "art" / "variants" / ("1" + source.suffix.lower())
            shutil.copy2(source, target)
            manifest_path = DATA / card.media_folder / "manifest.json"
            manifest = read_json(manifest_path, {})
            manifest["art"] = {"owner": "user", "variants": [1], "source_name": source.name}
            write_json(manifest_path, manifest)
        self.cards[card_id] = card
        self.save()
        return card

    def craft_team_effect(self, team_id, sacrifices):
        team = self.teams.get(team_id)
        if not team or team.effect_locked or len(sacrifices) != 3 or len(set(sacrifices)) != 3: return None
        owners = []
        for card_id in sacrifices:
            owner = next((character for character in self.characters.values() if card_id in character.library_cards and character.id in team.members), None)
            if not owner: return None
            owners.append(owner)
        for owner, card_id in zip(owners, sacrifices): owner.library_cards.remove(card_id)
        families = [self.cards[card_id].family for card_id in sacrifices if card_id in self.cards]
        family = max(set(families), key=families.count) if families else "any"
        team.team_effect = {"candidates": [{"kind": "family_boost", "family": family, "atk": 300}, {"kind": "team_heal", "amount": 500}, {"kind": "team_draw", "amount": 1}], "selected": None, "sacrifices": list(sacrifices), "created": time.time()}
        team.history.append({"event": "effect_candidates_created", "sacrifices": list(sacrifices), "time": time.time()})
        self.save()
        return team.team_effect

    def choose_team_effect(self, team_id, index):
        team = self.teams.get(team_id)
        if not team or team.effect_locked or not team.team_effect.get("candidates") or index not in range(3): return False
        team.team_effect["selected"] = team.team_effect["candidates"][index]
        team.effect_locked = True
        team.history.append({"event": "team_effect_locked", "effect": team.team_effect["selected"], "time": time.time()})
        self.save()
        return True

    def create_championship(self, level, team_ids):
        level = clamp(int(level), 1, 5)
        eligible = [team_id for team_id in team_ids if team_id in self.teams and len(self.teams[team_id].members) == 3]
        required = 2 ** (level + 1)
        if len(eligible) < required: return None
        eligible = eligible[:required]
        rounds = []
        current = eligible
        while len(current) > 1:
            pairs = [[current[index], current[index + 1]] for index in range(0, len(current), 2)]
            rounds.append({"pairs": pairs, "results": []})
            current = [pair[0] for pair in pairs]
        championship = {"id": "championship_" + str(int(time.time() * 1000)), "level": level, "teams": eligible, "rounds": rounds, "state": "open", "host": self.role_config()["player_character"], "created": time.time(), "history": []}
        self.world.setdefault("championships", []).append(championship)
        self.save()
        return championship

    def resolve_championship_match(self, championship_id, round_index, pair_index, winner_id):
        championship = next((item for item in self.world.setdefault("championships", []) if item.get("id") == championship_id), None)
        if not championship or round_index not in range(len(championship["rounds"])): return False
        round_data = championship["rounds"][round_index]
        if pair_index not in range(len(round_data["pairs"])) or winner_id not in round_data["pairs"][pair_index]: return False
        round_data["results"].append({"pair": round_data["pairs"][pair_index], "winner": winner_id, "time": time.time()})
        championship["history"].append({"event": "match_resolved", "round": round_index, "pair": pair_index, "winner": winner_id, "time": time.time()})
        if len(round_data["results"]) == len(round_data["pairs"]):
            winners = [item["winner"] for item in round_data["results"]]
            next_round = round_index + 1
            if next_round < len(championship["rounds"]): championship["rounds"][next_round]["pairs"] = [[winners[index], winners[index + 1]] for index in range(0, len(winners), 2)]
            else: championship["state"] = "complete"; championship["winner"] = winners[0]
        self.save()
        return True

    def entity_tree(self, category):
        trees = {
            "cards": ["logic", "art", "art/variants", "art/metadata", "animations/idle", "animations/summon", "animations/special_summon", "animations/set", "animations/flip", "animations/attack", "animations/damage", "animations/destroy", "audio/idle", "audio/summon", "audio/special_summon", "audio/set", "audio/flip", "audio/attack", "audio/damage", "audio/destroy", "interactions/summon/animations", "interactions/summon/audio", "interactions/set/animations", "interactions/set/audio", "interactions/flip/animations", "interactions/flip/audio", "interactions/activate/animations", "interactions/activate/audio", "characters"],
            "characters": ["logic", "weights", "pfp/variants", "animations/idle", "animations/about", "animations/pre-duel", "animations/win", "animations/lose", "animations/draw", "animations/shocked", "animations/happy", "animations/sad", "audio/idle", "audio/about", "audio/pre-duel", "audio/win", "audio/lose", "audio/draw", "audio/shocked", "audio/happy", "audio/sad", "duel/reactions/stranger", "duel/reactions/ally", "duel/reactions/enemy", "duel/reactions/opponent", "duel/interactions", "cards"],
            "teams": ["logic", "effects", "members/1", "members/2", "members/3", "animations/idle", "animations/pre-duel", "animations/win", "animations/lose", "animations/draw", "audio/idle", "audio/pre-duel", "audio/win", "audio/lose", "audio/draw", "members/1/animations", "members/2/animations", "members/3/animations"],
            "places": ["logic", "background/day", "background/night", "animations/pre-duel", "animations/spin-dice", "animations/in-duel", "animations/win", "animations/lose", "animations/draw", "audio/pre-duel", "audio/spin-dice", "audio/in-duel", "audio/near-win", "audio/near-lose", "audio/win", "audio/lose", "audio/draw", "music"],
            "decks": ["logic", "cards", "experience"]
        }
        return trees.get(category, ["logic", "animations", "audio"])

    def scaffold_entity(self, category, entity_id, display_name, folders=None, created=None, folder_name=""):
        folder_name = folder_name or f"{slug(display_name)}_{int((created or time.time()) * 1000)}_{slug(entity_id)}"
        root = DATA / category / folder_name
        paths = sorted(set(self.entity_tree(category) + list(folders or [])))
        for folder in paths: (root / folder).mkdir(parents=True, exist_ok=True)
        manifest = {"schema": 3, "id": entity_id, "name": display_name, "category": category, "created": created or time.time(), "folders": paths, "asset_contract": "gdd_nested_v1"}
        if category == "cards": manifest["frame_contract"] = "engine_owned"; manifest["art_contract"] = "user_owned_optional"
        write_json(root / "manifest.json", manifest)
        return str(root.relative_to(DATA))

    def ensure_entity_scaffolds(self):
        changed = False
        registries = [("cards", self.cards), ("characters", self.characters), ("teams", self.teams), ("places", self.places)]
        for category, registry in registries:
            for entity in registry.values():
                folder = getattr(entity, "media_folder", "")
                root = DATA / folder if folder else None
                if not root or not root.exists():
                    folder = self.scaffold_entity(category, entity.id, entity.name)
                    entity.media_folder = folder
                    changed = True
                else:
                    paths = self.entity_tree(category)
                    for item in paths: (root / item).mkdir(parents=True, exist_ok=True)
                    manifest = read_json(root / "manifest.json", {})
                    manifest.update({"schema": 3, "id": entity.id, "name": entity.name, "category": category, "folders": sorted(set(manifest.get("folders", []) + paths)), "asset_contract": "gdd_nested_v1"})
                    if category == "cards": manifest.update({"frame_contract": "engine_owned", "art_contract": "user_owned_optional"})
                    if category == "cards" and not getattr(entity, "art_folder", ""):
                        entity.art_folder = entity.media_folder
                        changed = True
                    write_json(root / "manifest.json", manifest)
        if changed:
            self.save()

    def create_place(self, name, capacity=3, background="", day_night=True):
        place_id = "place_" + str(int(time.time() * 1000))
        display_name = name or "New Place"
        folder = self.scaffold_entity("places", place_id, display_name, ["background", "background/day", "background/night", "background/animation", "music/day", "music/night", "music/pre_duel", "music/duel", "music/near_win", "music/near_lose", "music/post_duel/win", "music/post_duel/lose", "animations/pre_duel", "animations/dice", "animations/win", "animations/lose", "animations/draw"])
        place = PlaceDef(place_id, display_name, clamp(int(capacity), 1, 10), 0, background.strip(), bool(day_night), folder)
        self.places[place_id] = place
        self.save()
        return place

    def create_team(self, name, members, preferred_place):
        team_id = "team_" + str(int(time.time() * 1000))
        display_name = name or "New Team"
        selected = [member for member in dict.fromkeys(members) if member in self.characters and member != self.role_config()["player_character"]][:3]
        if not selected: return None
        leader = selected[0]
        folder = self.scaffold_entity("teams", team_id, display_name)
        team = TeamDef(team_id, display_name, selected, leader, [preferred_place] if preferred_place in self.places else [], "community", {}, False, 1, [], folder)
        self.teams[team_id] = team
        self.save()
        return team

    def update_character(self, character_id, values):
        character = self.characters.get(character_id)
        if not character: return None
        allowed = {"name", "portrait", "stars", "smartness", "relationship", "preferred_families", "deck_id", "gender", "origin", "best_cards"}
        for key, value in values.items():
            if key not in allowed: continue
            if key in ["stars", "smartness"]: value = clamp(int(value), 1, 10)
            if key == "preferred_families": value = list(dict.fromkeys(value))[:5] or ["warrior"]
            setattr(character, key, value)
        self.save()
        return character

    def update_team(self, team_id, values):
        team = self.teams.get(team_id)
        if not team: return None
        if "members" in values:
            members = [member for member in dict.fromkeys(values["members"]) if member in self.characters][:3]
            if members: team.members = members
            if team.leader not in team.members: team.leader = team.members[0]
        if "name" in values and values["name"]: team.name = str(values["name"])
        if "leader" in values and values["leader"] in team.members: team.leader = values["leader"]
        if "preferred_places" in values: team.preferred_places = [place for place in dict.fromkeys(values["preferred_places"]) if place in self.places]
        self.save()
        return team

    def update_place(self, place_id, values):
        place = self.places.get(place_id)
        if not place: return None
        if "name" in values and values["name"]: place.name = str(values["name"])
        if "capacity" in values: place.capacity = clamp(int(values["capacity"]), 1, 10)
        if "background" in values and values["background"]: place.background = str(values["background"])
        if "day_night" in values: place.day_night = bool(values["day_night"])
        if "event_response_policies" in values and isinstance(values["event_response_policies"], dict): place.event_response_policies = dict(values["event_response_policies"])
        if "event_window_policies" in values and isinstance(values["event_window_policies"], dict): place.event_window_policies = dict(values["event_window_policies"])
        if "trigger_order_policies" in values and isinstance(values["trigger_order_policies"], dict): place.trigger_order_policies = dict(values["trigger_order_policies"])
        self.save()
        return place

    def update_card(self, card_id, values):
        card = self.cards.get(card_id)
        if not card: return None
        allowed = {"name", "kind", "stars", "atk", "defense", "family", "description", "logic_graph", "targets", "target_count", "timing", "field_effect", "materials", "ritual_cost", "summon_method", "effects"}
        merged = {key: getattr(card, key) for key in allowed}
        merged.update({key: value for key, value in values.items() if key in allowed})
        errors = self.validate_card_definition(merged["kind"], int(merged["stars"]), int(merged["atk"]), int(merged["defense"]), merged["family"], merged["description"], merged["targets"], int(merged["target_count"]), merged["timing"], merged["materials"], int(merged["ritual_cost"]), merged["summon_method"], merged["effects"])
        if errors: return None
        for key, value in merged.items(): setattr(card, key, value)
        card.frame = "yellow" if card.kind == "normal" else "orange" if card.kind == "effect" else "sky" if card.kind in ["spell", "field"] else "pink" if card.kind == "trap" else "violet" if card.kind == "fusion" else "blue" if card.kind == "ritual" else "red"
        card.legendary = card.kind == "legendary"
        card.limit = 1 if card.legendary else 3
        self.save()
        return card

    def create_character(self, name, stars, smartness, family, portrait="pfp_placeholder", gender="other", origin="community", deck_id=""):
        char_id = "character_" + str(int(time.time() * 1000))
        display_name = name or "New Character"
        if deck_id not in self.decks:
            deck_id = "deck_" + str(int(time.time() * 1000))
            self.decks[deck_id] = {"name": display_name + " Deck", "cards": list(self.cards)[:10], "media_folder": self.scaffold_entity("decks", deck_id, display_name + " Deck")}
        folder = self.scaffold_entity("characters", char_id, display_name)
        char = CharacterDef(char_id, display_name, portrait or "pfp_placeholder", clamp(int(stars), 1, 10), clamp(int(smartness), 1, 10), "stranger", [family or "warrior"], deck_id, "neutral", [], [], [], [], gender or "other", origin or "community", [], [], 1, folder)
        self.characters[char_id] = char
        self.save()
        return char

    def register_user(self, name, portrait="pfp_placeholder", gender="other"):
        timestamp = int(time.time() * 1000)
        user_id = "user_" + str(timestamp)
        display_name = str(name or "New User").strip() or "New User"
        deck_id = user_id + "_deck"
        card_ids = list(self.cards)[:10]
        deck_folder = self.scaffold_entity("decks", deck_id, display_name + " Deck", folder_name=deck_id + "_deck")
        self.decks[deck_id] = {"name": display_name + " Deck", "cards": card_ids, "media_folder": deck_folder}
        character_folder = self.scaffold_entity("characters", user_id, display_name, folder_name=user_id)
        character = CharacterDef(user_id, display_name, portrait or "pfp_placeholder", 5, 5, "stranger", ["warrior"], deck_id, "neutral", [], [], [], list(card_ids), gender or "other", "user", [], [], 1, character_folder)
        self.characters[user_id] = character
        self.save_data.update({"active_user_id": user_id, "active_user_folder": character_folder, "setup_complete": True})
        self.world.setdefault("roles", {})["player_character"] = user_id
        self.save()
        return character

    def export_cbp(self, kind, entity_id):
        filename = DATA / "exports" / f"{entity_id}.cbp"
        includes = {"cards": list(self.cards), "characters": list(self.characters), "decks": list(self.decks), "places": list(self.places), "teams": list(self.teams), "world": True, "logic": list(self.logic), "entity_media": []}
        for category, registry in [("cards", self.cards), ("characters", self.characters), ("teams", self.teams), ("places", self.places)]:
            for entity in registry.values():
                root = DATA / getattr(entity, "media_folder", "")
                if root.exists():
                    includes["entity_media"].append({"category": category, "id": entity.id, "path": str(root.relative_to(DATA))})
        manifest = {"schema": 3, "kind": kind, "entity_id": entity_id, "created": time.time(), "asset_contract": "gdd_nested_v1", "font_contract": "Noto Serif Display headings + DejaVu Sans UI", "includes": includes}
        with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            for path in [DATA / "cards.json", DATA / "characters.json", DATA / "decks.json", DATA / "places.json", DATA / "teams.json", DATA / "world.json"]:
                if path.exists(): archive.write(path, path.name)
            for path in (DATA / "logic").glob("*.json"):
                archive.write(path, "logic/" + path.name)
            for item in includes["entity_media"]:
                root = DATA / item["path"]
                for path in root.rglob("*"):
                    if path.is_file(): archive.write(path, "data/" + str(path.relative_to(DATA)))
        return filename

    def inspect_cbp(self, path):
        with zipfile.ZipFile(path) as archive:
            return json.loads(archive.read("manifest.json").decode("utf-8"))

    def import_cbp(self, path, include=None):
        include = set(include or ["cards", "characters", "decks", "places", "teams", "world", "logic"])
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "cards" in include and "cards.json" in names:
                self.cards.update({entry["id"]: CardDef(**entry) for entry in json.loads(archive.read("cards.json"))})
            if "characters" in include and "characters.json" in names:
                self.characters.update({entry["id"]: CharacterDef(**entry) for entry in json.loads(archive.read("characters.json"))})
            if "decks" in include and "decks.json" in names: self.decks.update(json.loads(archive.read("decks.json")))
            if "places" in include and "places.json" in names:
                self.places.update({entry["id"]: self.place_from_entry(entry) for entry in json.loads(archive.read("places.json"))})
                self.sync_place_runtime()
            if "teams" in include and "teams.json" in names: self.teams.update({entry["id"]: TeamDef(**entry) for entry in json.loads(archive.read("teams.json"))})
            if "world" in include and "world.json" in names:
                incoming = json.loads(archive.read("world.json"))
                for key, values in incoming.items():
                    if isinstance(values, list):
                        current = self.world.setdefault(key, [])
                        current.extend(item for item in values if item.get("id") not in {entry.get("id") for entry in current})
                    elif isinstance(values, dict): self.world[key] = {**self.world.get(key, {}), **values}
            if "logic" in include:
                for name in names:
                    if name.startswith("logic/") and name.endswith(".json"):
                        graph = LogicGraph.from_dict(json.loads(archive.read(name)))
                        self.logic[Path(name).stem] = graph
            if "cards" in include or "characters" in include or "teams" in include or "places" in include:
                for name in names:
                    if not name.startswith("data/") or name.endswith("/"): continue
                    relative = Path(name[5:])
                    if any(part in ["", ".", ".."] for part in relative.parts): continue
                    category = relative.parts[0] if relative.parts else ""
                    if category not in include or category not in ["cards", "characters", "teams", "places"]: continue
                    target = DATA / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
        self.ensure_entity_scaffolds()
        self.save()
        return {"imported": sorted(include), "source": str(path), "nested_media": True}


def query_entities(values, query="", sort_mode="name"):
    query = (query or "").strip().lower()
    items = [value for value in values if not query or query in value.name.lower()]
    if sort_mode == "rank": items.sort(key=lambda value: (-int(getattr(value, "rank", 1)), value.name.lower()))
    else: items.sort(key=lambda value: value.name.lower())
    return items


class DeckRules:
    minimum = 40
    maximum = 80
    copies = 3

    @classmethod
    def partition(cls, card_ids, available):
        main = []
        extra = []
        for card_id in card_ids:
            card = available.get(card_id)
            if not card: continue
            if card.kind == "fusion": extra.append(card_id)
            else: main.append(card_id)
        return main, extra

    @classmethod
    def normalized(cls, card_ids, available):
        result = []
        counts = {}
        main_count = 0
        for card_id in card_ids:
            card = available.get(card_id)
            if not card: continue
            limit = 1 if card.legendary else cls.copies
            if counts.get(card_id, 0) >= limit: continue
            if card.kind != "fusion" and main_count >= cls.maximum: continue
            result.append(card_id)
            counts[card_id] = counts.get(card_id, 0) + 1
            if card.kind != "fusion": main_count += 1
        return result

    @classmethod
    def validate(cls, card_ids, available):
        errors = []
        main, extra = cls.partition(card_ids, available)
        if len(main) < cls.minimum: errors.append(f"minimum {cls.minimum} main-deck cards")
        if len(main) > cls.maximum: errors.append(f"maximum {cls.maximum} main-deck cards")
        counts = {}
        for card_id in card_ids:
            card = available.get(card_id)
            if not card:
                errors.append(f"unknown card {card_id}")
                continue
            counts[card_id] = counts.get(card_id, 0) + 1
            if counts[card_id] > (1 if card.legendary else cls.copies): errors.append(f"{card.name} exceeds its copy limit")
        return list(dict.fromkeys(errors))

    @classmethod
    def summary(cls, card_ids, available):
        errors = cls.validate(card_ids, available)
        return "VALID" if not errors else "INVALID: " + ", ".join(dict.fromkeys(errors))


class CardInstance:
    def __init__(self, card, owner):
        self.card = card
        self.owner = owner
        self.variant = int(getattr(card, "art_variant", 1) or 1)
        self.position = "hand"
        self.last_zone = "hand"
        self.face_up = True
        self.battle_position = "attack"
        self.summon_method = ""
        self.summon_source_zone = ""
        self.summon_source_card_id = ""
        self.summon_source_card_name = ""
        self.summon_source_effect_id = ""
        self.summon_history = []
        self.attack_bonus = 0
        self.defense_bonus = 0
        self.attacked = False

    @property
    def atk(self):
        return self.card.atk + self.attack_bonus

    @property
    def defense(self):
        return self.card.defense + self.defense_bonus


@dataclass
class RuleContext:
    context_id: str
    trigger: str
    phase: str
    turn: int
    actor_id: str
    source_card_id: str
    source_zone: str
    target_ids: list = field(default_factory=list)
    window: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class EffectEvent:
    sequence: int
    action: str
    amount: int
    actor: object
    source: object
    target: object = None
    trigger: str = ""
    status: str = "queued"
    result: dict = field(default_factory=dict)
    source_zone: str = ""
    source_actor: str = ""
    policy: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)


@dataclass
class ChainLink:
    link_id: str
    index: int
    source: object
    actor: object
    target: object
    trigger: str
    effect_id: str
    speed: int = 1
    status: str = "pending"
    negated: bool = False
    context: dict = field(default_factory=dict)


@dataclass
class Notification:
    notification_id: int
    kind: str
    message: str
    options: list
    payload: dict = field(default_factory=dict)
    status: str = "pending"
    answer: str = ""


class Duelist:
    def __init__(self, character, store):
        self.character = character
        self.name = character.name
        self.hp = 8000
        self.deck = []
        self.hand = []
        self.monsters = [None] * 5
        self.spells = [None] * 5
        self.graveyard = []
        self.banished = []
        self.extra = []
        deck_ids = DeckRules.normalized(store.decks.get(character.deck_id, {}).get("cards", []), store.cards)
        for card_id in deck_ids:
            instance = CardInstance(store.cards[card_id], self.name)
            if instance.card.kind == "fusion":
                instance.position = "extra"
                instance.last_zone = "extra"
                self.extra.append(instance)
            else:
                instance.position = "deck"
                instance.last_zone = "deck"
                self.deck.append(instance)
        random.shuffle(self.deck)

    def draw(self, count=1):
        result = []
        for _ in range(count):
            if self.deck:
                card = self.deck.pop(0)
                card.position = "hand"
                self.hand.append(card)
                result.append(card)
        return result

    def remove(self, card):
        if card in self.hand: self.hand.remove(card)
        if card in self.graveyard: self.graveyard.remove(card)
        if card in self.banished: self.banished.remove(card)
        if card in self.extra: self.extra.remove(card)
        for index, item in enumerate(self.monsters):
            if item is card: self.monsters[index] = None
        for index, item in enumerate(self.spells):
            if item is card: self.spells[index] = None


class SelectorRuntime:
    zones = {"monster", "spell_trap", "field", "deck", "hand", "graveyard", "banished", "extra", "any"}

    def __init__(self, engine, actor, source=None):
        self.engine = engine
        self.actor = actor
        self.source = source

    def sides(self, value):
        side = str(value or "any").lower()
        if side in ["self", "player", "actor"]: return [self.actor]
        if side in ["opponent", "enemy"]: return [self.engine.other(self.actor)]
        if side in ["both", "any"]: return [self.actor, self.engine.other(self.actor)]
        return [self.actor, self.engine.other(self.actor)]

    def zone_items(self, duelist, zone):
        if zone == "monster": return [item for item in duelist.monsters if item]
        if zone == "spell_trap": return [item for item in duelist.spells if item]
        if zone == "deck": return list(duelist.deck)
        if zone == "hand": return list(duelist.hand)
        if zone == "graveyard": return list(duelist.graveyard)
        if zone == "banished": return list(duelist.banished)
        if zone == "extra": return list(getattr(duelist, "extra", []))
        if zone == "field":
            return [self.engine.field_card] if self.engine.field_card and getattr(self.engine, "field_card_owner", self.actor) is duelist else []
        if zone == "any":
            return self.zone_items(duelist, "deck") + self.zone_items(duelist, "hand") + self.zone_items(duelist, "monster") + self.zone_items(duelist, "spell_trap") + self.zone_items(duelist, "graveyard") + self.zone_items(duelist, "banished") + self.zone_items(duelist, "extra") + self.zone_items(duelist, "field")
        return []

    @staticmethod
    def compare(actual, operator, expected):
        try: actual, expected = float(actual), float(expected)
        except (TypeError, ValueError): return False
        return {"equals": actual == expected, "==": actual == expected, "not_equals": actual != expected, "!=": actual != expected, "less_than": actual < expected, "<": actual < expected, "less_or_equal": actual <= expected, "<=": actual <= expected, "greater_than": actual > expected, ">": actual > expected, "greater_or_equal": actual >= expected, ">=": actual >= expected}.get(operator, False)

    def matches(self, candidate, selector):
        if isinstance(candidate, Duelist): return not any(key in selector for key in ["card_kind", "family", "origin", "face_up", "position", "stat"])
        card = candidate.card
        kinds = selector.get("card_kind", selector.get("card_type", selector.get("kind", [])))
        if kinds and card.kind not in (kinds if isinstance(kinds, list) else [kinds]): return False
        family_value = selector.get("family", selector.get("monster_type", selector.get("type")))
        for key in ["card_id", "family", "origin", "name"]:
            actual = getattr(card, "id", "") if key == "card_id" else getattr(card, key, "")
            expected = family_value if key == "family" else selector.get(key)
            if expected is not None:
                values = expected if isinstance(expected, list) else [expected]
                if str(actual).lower() not in [str(value).lower() for value in values]: return False
        if selector.get("gender") is not None:
            owner = self.engine.player if candidate in self.engine.player.hand + self.engine.player.graveyard + self.engine.player.banished else self.engine.opponent
            if owner.character.gender.lower() != str(selector["gender"]).lower(): return False
        if selector.get("face_up") is not None and bool(candidate.face_up) is not bool(selector["face_up"]): return False
        if selector.get("position"):
            expected_position = str(selector["position"]).lower()
            actual_position = str(candidate.battle_position if expected_position in ["attack", "defense"] else candidate.position).lower()
            if expected_position not in ["any", actual_position]: return False
        stat = selector.get("stat")
        if stat:
            field_name = stat.get("field", "attack")
            actual = candidate.atk if field_name in ["attack", "atk"] else candidate.defense
            if not self.compare(actual, stat.get("operator", "equals"), stat.get("value", 0)): return False
        return True

    def proximity(self, candidates, selector):
        scope = selector.get("scope", "field")
        if scope not in ["nearest", "adjacent", "aura"] or not isinstance(self.source, CardInstance): return candidates
        owner = self.engine.owner_of(self.source)
        if not owner: return candidates
        slots = owner.monsters if self.source in owner.monsters else owner.spells
        origin = next((index for index, item in enumerate(slots) if item is self.source), None)
        if origin is None: return candidates
        radius = int(selector.get("radius", 1) or 1)
        ranked = sorted([(abs(index - origin), item) for index, item in enumerate(slots) if item in candidates], key=lambda value: value[0])
        limit = radius if scope in ["nearest", "adjacent"] else len(ranked)
        return [item for _, item in ranked if _ <= radius][:limit]

    def select(self, selector):
        selector = dict(selector or {})
        zones = selector.get("zone", "any")
        zones = zones if isinstance(zones, list) else [zones]
        candidates = []
        selector_keys = set(selector) - {"side", "zone", "count", "include_duelist"}
        if selector.get("include_duelist") and not selector_keys:
            candidates = self.sides(selector.get("side", "any"))
        else:
            for duelist in self.sides(selector.get("side", "any")):
                for zone in zones:
                    candidates.extend(self.zone_items(duelist, zone if zone in self.zones else "any"))
            if selector.get("include_duelist"):
                candidates.extend(self.sides(selector.get("side", "any")))
        candidates = list(dict.fromkeys(item for item in candidates if self.matches(item, selector)))
        candidates = self.proximity(candidates, selector)
        count = selector.get("count")
        if count == "all" or count is None: return candidates
        try: return candidates[:max(0, int(count))]
        except (TypeError, ValueError): return candidates


class DuelEngine:
    phases = DUEL_PHASES

    def __init__(self, store, player_id=None, opponent_id=None, place_id=None, cpu=False, team_effect=None, opponent_team_effect=None):
        self.store = store
        roles = store.role_config()
        player_id = player_id or roles["player_character"]
        opponent_id = opponent_id or roles["default_opponent_character"]
        place_id = place_id or roles["default_place"]
        self.player = Duelist(store.characters[player_id], store)
        self.opponent = Duelist(store.characters[opponent_id], store)
        self.place = store.places[place_id]
        self.active = self.player if not cpu else self.opponent
        self.phase_index = 0
        self.turn = 1
        self.events = []
        self.effect_queue = []
        self.resolution_history = []
        self.effect_sequence = 0
        self.notifications = []
        self.notification_history = []
        self.notification_sequence = 0
        self.observation_sequence = 0
        self.observation_log = []
        self.observation_guard = False
        self.knowledge = {"player": {"card_ids": [], "effect_ids": [], "effect_facts": {}}, "opponent": {"card_ids": [], "effect_ids": [], "effect_facts": {}}}
        self.rule_event_sequence = 0
        self.event_history = []
        self.trigger_group_sequence = 0
        self.trigger_groups = []
        self.pending_trigger_order = None
        self.active_rule_context = None
        self.event_dispatch_stack = []
        self.chain_links = []
        self.chain_history = []
        self.chain_sequence = 0
        self.chain_priority = None
        self.chain_passes = []
        self.chain_window = None
        self.active_chain_link_id = ""
        self.pending_response = None
        self.logic_runtime = LogicRuntime(store.logic)
        self.reaction_resolver = ReactionResolver(store.media)
        self.reaction_events = []
        self.selected_hand = None
        self.selected_monster = None
        self.finished = False
        self.winner = None
        self.reason = ""
        self.transferred_card = ""
        self.match_recorded = False
        self.pending_discard = None
        self.pending_target = None
        self.pending_summon = None
        self.pending_trap = None
        self.pending_cost = None
        self.pending_procedure = None
        self.pending_effect = None
        self.effect_usage = {}
        self.continuous_effects = []
        self.continuous_sequence = 0
        self.summon_permissions = {"player": {"base": 1, "used": 0, "grants": []}, "opponent": {"base": 1, "used": 0, "grants": []}}
        self.field_card = None
        self.field_card_owner = None
        self.cpu = cpu
        self.team_effect = team_effect or {}
        self.opponent_team_effect = opponent_team_effect or {}
        self.prepared = False
        self.player.draw(5)
        self.opponent.draw(5)
        self.apply_team_start_effect(self.player, self.team_effect)
        self.apply_team_start_effect(self.opponent, self.opponent_team_effect)
        self.log("The duel begins. The accepting side enters first.")

    def side_key(self, side):
        return "player" if side is self.player else "opponent"

    def effect_usage_key(self, card, spec):
        return (id(card), spec.effect_id)

    def effect_used(self, card, spec):
        usage = self.effect_usage.get(self.effect_usage_key(card, spec))
        if not usage: return False
        if spec.once in ["once_per_turn", "per_turn"] and usage.get("turn") != self.turn: return False
        return True

    def mark_effect_used(self, card, spec):
        if spec.once: self.effect_usage[self.effect_usage_key(card, spec)] = {"turn": self.turn, "phase": self.phase}

    def reset_summon_permissions(self, side):
        state = self.summon_permissions[self.side_key(side)]
        state["used"] = 0
        for grant in state["grants"]: grant["remaining"] = grant.get("per_turn", grant.get("remaining", 0))

    def normal_summon_remaining(self, side):
        state = self.summon_permissions[self.side_key(side)]
        return max(0, int(state.get("base", 1)) - int(state.get("used", 0))) + sum(max(0, int(grant.get("remaining", 0))) for grant in state.get("grants", []))

    def grant_normal_summon(self, side, count=1, cost=None, per_turn=False, source=None):
        amount = max(1, int(count or 1))
        state = self.summon_permissions[self.side_key(side)]
        grant = {"remaining": amount, "per_turn": amount if per_turn else 0, "cost": dict(cost or {}), "source": source or "effect"}
        state["grants"].append(grant)
        self.log(f"{side.name} gains {amount} additional normal summon permission(s).")
        return grant

    def consume_normal_summon(self, side):
        state = self.summon_permissions[self.side_key(side)]
        if state.get("used", 0) < state.get("base", 1):
            state["used"] += 1
            return True, ""
        grant = next((item for item in state.get("grants", []) if item.get("remaining", 0) > 0), None)
        if not grant: return False, "No normal summon permission remains this turn."
        cost = grant.get("cost") or {}
        if cost.get("kind") == "pay_hp":
            amount = max(0, int(cost.get("amount", 0) or 0))
            if side.hp < amount: return False, "The extra normal summon cost cannot be paid."
            side.hp -= amount
            self.check_end()
        grant["remaining"] -= 1
        return True, ""

    @property
    def phase(self):
        return self.phases[self.phase_index]

    def other(self, side):
        return self.opponent if side is self.player else self.player

    def notify(self, kind, message, options=("ok",), payload=None):
        payload = dict(payload or {})
        for notification in reversed(self.notifications):
            if notification.status == "pending" and notification.kind == kind and notification.message == message and notification.payload == payload: return notification
        self.notification_sequence += 1
        notification = Notification(self.notification_sequence, kind, message, list(options), payload)
        self.notifications.append(notification)
        self.record_observation("notification_created", {"id": notification.notification_id, "kind": kind, "options": list(options), "payload": payload})
        self.notifications = self.notifications[-32:]
        return notification

    def answer_notification(self, notification_id, answer):
        notification = next((item for item in self.notifications if item.notification_id == notification_id and item.status == "pending"), None)
        if not notification or answer not in notification.options: return False
        notification.answer = answer
        notification.status = "resolved"
        self.notification_history.append({"id": notification.notification_id, "kind": notification.kind, "answer": answer, "payload": notification.payload, "time": time.time()})
        self.record_observation("notification_answered", {"id": notification.notification_id, "kind": notification.kind, "answer": answer, "payload": notification.payload})
        self.notification_history = self.notification_history[-64:]
        return True

    def respond_notification(self, notification_id, answer="ok", selection=None):
        notification = next((item for item in self.notifications if item.notification_id == notification_id and item.status == "pending"), None)
        if not notification or answer not in notification.options: return False, "That response is not available."
        if notification.kind == "yes_no":
            success, message = self.answer_pending_effect(answer)
            return success, message
        if notification.kind == "chain_response":
            if answer == "card":
                candidates = self.response_candidates(self.chain_priority, self.chain_window.get("trigger", "") if self.chain_window else "")
                selected = selection if isinstance(selection, CardInstance) else next((item["card"] for item in candidates if item["card"].card.id == str(selection)), None)
                candidate = next((item for item in candidates if item["card"] is selected), None)
                if not candidate: return False, "That response card is not legal in this window."
                return self.begin_response_card(selected, candidate["spec"].effect_id, self.chain_priority)
            if answer != "pass" or not notification.payload.get("allow_pass", True): return False, "Passing is not available in this response window."
            notification.status, notification.answer = "resolved", answer
            self.notification_history.append({"id": notification.notification_id, "kind": notification.kind, "answer": answer, "payload": notification.payload, "time": time.time()})
            return self.pass_chain_priority(self.chain_priority)
        if notification.kind == "choose_trigger_order":
            if answer != "ok": return False, "Confirm the selected trigger order."
            return self.resolve_trigger_order(selection)
        if notification.kind == "choose_target":
            selected = selection if isinstance(selection, list) else [selection]
            if self.pending_response: return self.resolve_pending_response(selected)
            if self.pending_summon: return self.resolve_pending_summon(selected)
            if not selected or not self.pending_target: return False, "Choose the required target(s)."
            result = (True, "")
            for item in selected:
                result = self.select_target(item)
                if not result[0]: return result
            return result
        if notification.kind == "choose_cards":
            if self.pending_cost: return self.resolve_pending_cost(selection)
            if self.pending_procedure: return self.resolve_pending_procedure(selection)
            if selection is None: return False, "Choose the required card(s)."
            return False, "No card selection is pending."
        if self.answer_notification(notification_id, answer): return True, ""
        return False, "The notification could not be resolved."

    def pending_notification(self, kind=None):
        return next((item for item in reversed(self.notifications) if item.status == "pending" and (kind is None or item.kind == kind)), None)

    def log(self, message):
        self.events.append(message)
        self.events = self.events[-8:]

    def interact(self, action):
        actor = self.player.character
        target = self.opponent.character
        changes = {"thank": ("grateful", "ally"), "taunt": ("heated", "enemy"), "beg": ("uneasy", "opponent"), "flirt": ("curious", "ally"), "insult": ("angry", "enemy"), "apologize": ("calm", "opponent")}
        mood, relation = changes.get(action, ("neutral", "opponent"))
        target.mood = mood
        if relation == "ally" and target.id not in actor.allies: actor.allies.append(target.id)
        if relation == "enemy" and target.id not in actor.enemies: actor.enemies.append(target.id)
        actor.history.append({"type": "interaction", "action": action, "target": target.id, "time": time.time()})
        target.history.append({"type": "interaction_received", "action": action, "actor": actor.id, "time": time.time()})
        self.log(f"{actor.name} {action}s with {target.name}; mood becomes {target.mood}.")
        self.react("pfp_" + action, actor.id, target.id, "opponent")
        self.store.save()

    def react(self, event, actor_id, target_id="", relation="stranger", entity_type="characters", entity_id="", mode="hang"):
        if relation == "opponent": relation = self.store.relationship_for(actor_id, target_id)
        selection = self.reaction_resolver.resolve(event, actor_id, target_id, relation, entity_type, entity_id, self.place.id, mode)
        record = {"event": event, "actor": actor_id, "target": target_id, "relation": relation, "selection": selection.to_dict(), "time": time.time()}
        self.reaction_events.append(record)
        self.reaction_events = self.reaction_events[-20:]
        self.log(f"MEDIA {event}: {selection.source} variant {selection.variant or 'placeholder'}")
        return selection

    def advance(self):
        if self.finished or self.pending_discard: return
        self.cleanup_continuous_effects("phase_end")
        self.phase_index += 1
        if self.phase_index >= len(self.phases):
            self.phase_index = 0
            ending = self.active
            self.emit_event("turn_end", ending, metadata={"turn": self.turn, "ending_side": self.side_key(ending)})
            self.cleanup_continuous_effects("turn_end")
            self.cleanup_continuous_effects("phase_end")
            self.active, _ = self.other(self.active), self.active
            self.turn += 1
            self.reset_summon_permissions(self.active)
            self.emit_event("turn_start", self.active, metadata={"turn": self.turn, "starting_side": self.side_key(self.active)})
            for card in self.active.monsters:
                if card: card.attacked = False
            drawn = self.active.draw(1)
            if not drawn:
                self.finish(self.other(self.active), "deck-out")
                return
            self.log(f"{self.active.name} draws {drawn[0].card.name}.")
            self.emit_event("draw", self.active, source=drawn[0], target=self.active, metadata={"count": len(drawn), "card_ids": [item.card.id for item in drawn]})
            self.react("draw", self.active.character.id, self.other(self.active).character.id, "opponent")
            if len(self.active.hand) > 6:
                self.pending_discard = self.active
                self.notify("discard", f"{self.active.name} must discard one card.", ["ok"], {"owner": self.active.name})
                self.log(f"{self.active.name} must discard one card.")
                return
        else:
            self.log(f"{self.active.name} enters {self.phase}.")
        self.emit_event("phase_enter", self.active, metadata={"phase": self.phase})
        if self.phase == "DRAW" and self.turn == 1:
            self.advance()

    def discard(self, card):
        if self.pending_discard is None or card not in self.pending_discard.hand:
            return False, "No discard is currently required."
        owner = self.pending_discard
        owner.hand.remove(card)
        card.position = "graveyard"
        owner.graveyard.append(card)
        self.pending_discard = None
        notification = self.pending_notification("discard")
        if notification: notification.status, notification.answer = "resolved", "ok"
        self.log(f"{owner.name} discards {card.card.name}.")
        return True, ""

    def legal_targets(self, card, actor=None, selector=None):
        actor = actor or self.player
        selector = selector or self.legacy_selector(card, actor)
        if not selector: return []
        candidate_selector = dict(selector)
        candidate_selector.pop("count", None)
        return SelectorRuntime(self, actor, card).select(candidate_selector)

    def revalidate_pending_targets(self, pending):
        if not pending.get("target_policy", {}).get("revalidate", True): return True, ""
        current = self.legal_targets(pending["card"], pending["actor"], pending.get("selector"))
        invalid = [item for item in pending.get("selected", []) if item not in current]
        if invalid: return False, "A selected target is no longer legal."
        return True, ""

    def select_target(self, target):
        if not self.pending_target: return False, "No target is currently pending."
        pending = self.pending_target
        card = pending["card"]
        actor = pending["actor"]
        candidates = self.legal_targets(card, actor, pending.get("selector")) if pending.get("target_policy", {}).get("revalidate", True) else pending.get("candidates", [])
        if target not in candidates: return False, "That target is not legal."
        selected = pending.setdefault("selected", [])
        if target in selected: return False, "That target is already selected."
        selected.append(target)
        required = max(1, int(pending.get("required", card.card.target_count or 1)))
        if len(selected) < required:
            self.log(f"{len(selected)}/{required} targets selected for {card.card.name}.")
            return True, ""
        valid, reason = self.revalidate_pending_targets(pending)
        if not valid: return False, reason
        trigger = pending["trigger"]
        resolved_target = selected[0] if required == 1 else selected
        actor.hand.remove(card)
        card.position = "graveyard"
        actor.graveyard.append(card)
        self.pending_target = None
        notification = self.pending_notification("choose_target") or self.pending_notification("target")
        if notification: notification.status, notification.answer = "resolved", "ok"
        self.emit_event("activate", actor, source=card, target=resolved_target, metadata={"zone": card.position, "target_ids": [self.entity_id(item) for item in (resolved_target if isinstance(resolved_target, list) else [resolved_target])]}, include_source=False)
        target_name = target.name if hasattr(target, "name") else target.card.name
        self.log(f"{card.card.name} targets {target_name}.")
        effect_specs = [EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index)) for index, raw in enumerate(card.card.effects)]
        spec = next((item for item in effect_specs if item.effect_id == pending.get("effect_id")), None) or next((item for item in effect_specs if item.trigger == trigger), None)
        if self.chain_enabled(spec):
            self.add_chain_link(card, spec, actor, resolved_target, trigger, {"target_snapshot": [getattr(getattr(item, "card", item), "id", getattr(item, "name", "")) for item in (resolved_target if isinstance(resolved_target, list) else [resolved_target])]})
        else:
            self.resolve(card, trigger, resolved_target, actor)
            self.run_logic(card, trigger, actor, self.other(actor))
        return True, ""

    def activate_trap(self, trap, actor=None):
        actor = actor or self.player
        if not self.pending_trap or trap is not self.pending_trap["trap"] or trap not in actor.spells: return False, "No trap is waiting for this timing window."
        attacker = self.pending_trap.get("attacker") or self.other(actor)
        actor.spells[actor.spells.index(trap)] = None
        trap.position = "graveyard"
        trap.face_up = True
        actor.graveyard.append(trap)
        self.pending_trap = None
        self.log(f"{actor.name} activates {trap.card.name} in the opponent attack window.")
        self.emit_event("activate", actor, source=trap, target=attacker, metadata={"zone": "spell_trap", "trap_window": True})
        attacker_owner = self.owner_of(attacker)
        self.react("trap", actor.character.id, attacker_owner.character.id if attacker_owner else "", "opponent", "cards", trap.card.id)
        self.resolve(trap, "battle", attacker, actor)
        return True, ""

    def activate_set_spell(self, card):
        if self.finished or self.active is not self.player or self.phase not in ["MAIN 1", "MAIN 2"]: return False, "A set spell can only activate during your main phase."
        if card not in self.player.spells or card.face_up or card.card.kind not in ["spell", "field"]: return False, "Select a set spell."
        card.face_up = True
        self.player.spells[self.player.spells.index(card)] = None
        if card.card.kind == "field":
            self.field_card = card
            self.field_card_owner = self.player
            card.position = "field"
            self.log(f"{self.player.name} activates set field card {card.card.name}.")
        else:
            card.position = "graveyard"
            self.player.graveyard.append(card)
            self.log(f"{self.player.name} activates set spell {card.card.name}.")
        self.emit_event("activate", self.player, source=card, target=self.opponent, metadata={"zone": "field" if card.card.kind == "field" else "graveyard", "set_activation": True}, include_source=False)
        self.react("activate", self.player.character.id, self.opponent.character.id, "opponent", "cards", card.card.id)
        self.resolve(card, "activate", actor=self.player)
        self.run_logic(card, "activate", self.player, self.opponent)
        return True, ""

    def apply_team_start_effect(self, side, effect):
        if not effect: return
        kind = effect.get("kind")
        if kind == "team_heal":
            amount = int(effect.get("amount", 0))
            side.hp = min(8000, side.hp + amount)
            self.log(f"{side.name}'s team effect restores {amount} health.")
        elif kind == "team_draw":
            amount = max(1, int(effect.get("amount", 1)))
            drawn = side.draw(amount)
            self.log(f"{side.name}'s team effect draws {len(drawn)} card(s).")

    def normalize_continuous_duration(self, modifier):
        duration = modifier.get("duration", modifier.get("expires", "permanent"))
        duration = str(duration or "permanent").lower().replace("-", "_").replace(" ", "_")
        aliases = {"turn": "until_end_of_turn", "phase": "until_end_of_phase", "source": "while_source_on_field", "while_source_faceup": "while_source_face_up"}
        return aliases.get(duration, duration)

    def register_continuous_effect(self, card, spec, actor):
        modifier = dict(spec.modifier or {})
        if not modifier or not (modifier.get("continuous") or modifier.get("duration") or modifier.get("replacement")): return None
        if modifier.get("continuous") and any(item.get("status") == "active" and item.get("source") is card and item.get("source_effect_id") == spec.effect_id for item in self.continuous_effects): return next(item for item in self.continuous_effects if item.get("status") == "active" and item.get("source") is card and item.get("source_effect_id") == spec.effect_id)
        self.continuous_sequence += 1
        record = {"id": "continuous_" + str(self.continuous_sequence), "source": card, "source_card_id": getattr(getattr(card, "card", card), "id", ""), "source_effect_id": spec.effect_id, "actor": actor, "actor_id": self.side_key(actor), "modifier": modifier, "duration": self.normalize_continuous_duration(modifier), "created_turn": self.turn, "created_phase": self.phase, "created_phase_index": self.phase_index, "layer": int(modifier.get("layer", 4) or 4), "status": "active"}
        self.continuous_effects.append(record)
        self.continuous_effects = self.continuous_effects[-128:]
        self.log(f"{record['source_card_id']} establishes {record['duration']} continuous effect.")
        return record

    def continuous_effect_active(self, record):
        if record.get("status") != "active": return False
        duration = record.get("duration", "permanent")
        source = record.get("source")
        if duration == "while_source_on_field":
            return bool(source and source.position == "field" and self.owner_of(source) is not None)
        if duration == "while_source_face_up":
            return bool(source and source.position == "field" and source.face_up and self.owner_of(source) is not None)
        return True

    def cleanup_continuous_effects(self, reason=""):
        changed = False
        for record in self.continuous_effects:
            duration = record.get("duration", "permanent")
            expires = duration == "until_end_of_phase" and (reason == "phase_end" or self.phase_index != record.get("created_phase_index"))
            expires = expires or duration in ["until_end_of_turn", "this_turn"] and (reason == "turn_end" or self.turn > record.get("created_turn", self.turn))
            expires = expires or not self.continuous_effect_active(record)
            if expires and record.get("status") == "active":
                record["status"] = "expired"
                changed = True
        if changed: self.continuous_effects = [item for item in self.continuous_effects if item.get("status") == "active"]

    def modifier_records(self):
        records = []
        if self.field_card:
            legacy = dict(self.field_card.card.field_effect or {})
            if legacy: records.append({"source": self.field_card, "modifier": EffectSpec.from_dict({"id": "field_" + self.field_card.card.id, "field_effect": legacy}).modifier})
            for effect in self.field_card.card.effects:
                spec = EffectSpec.from_dict(effect, "field_" + self.field_card.card.id)
                if spec.modifier: records.append({"source": self.field_card, "modifier": spec.modifier})
        for record in self.continuous_effects:
            if self.continuous_effect_active(record):
                modifier = dict(record.get("modifier") or {})
                modifier.setdefault("layer", record.get("layer", 4))
                records.append({"source": record.get("source"), "modifier": modifier, "continuous": record})
        for effect in getattr(self.place, "effects", []) or []:
            spec = EffectSpec.from_dict(effect, "place_" + self.place.id)
            modifier = spec.modifier or (effect if isinstance(effect, dict) and effect.get("stat") else {})
            if modifier: records.append({"source": self.place, "modifier": modifier})
        for side, effect in [(self.player, self.team_effect), (self.opponent, self.opponent_team_effect)]:
            selected = effect.get("selected", effect) if isinstance(effect, dict) else {}
            if selected.get("kind") == "family_boost":
                records.append({"source": side.character, "modifier": {"scope": "field", "selector": {"side": "self", "zone": "monster", "family": selected.get("family")}, "stat": "attack", "operation": "add", "amount": selected.get("atk", 0), "owner": side.name}})
            elif isinstance(selected, dict) and selected.get("modifier"):
                modifier = dict(selected["modifier"])
                modifier.setdefault("owner", side.name)
                records.append({"source": side.character, "modifier": modifier})
        return sorted(records, key=lambda item: (int(item["modifier"].get("layer", 4) or 4), str(getattr(getattr(item.get("source"), "card", item.get("source")), "id", "")), str(item["modifier"].get("stat", "attack"))))

    def replace_event_value(self, event, value, actor, targets):
        result = int(value)
        self.last_replacement_records = []
        target_items = targets if isinstance(targets, list) else [targets] if targets is not None else []
        records = sorted(self.continuous_effects, key=lambda item: (int(((item.get("modifier") or {}).get("replacement") or {}).get("priority", ((item.get("modifier") or {}).get("layer", 4))) or 4), item.get("id", "")))
        for record in records:
            if not self.continuous_effect_active(record): continue
            replacement = dict((record.get("modifier") or {}).get("replacement") or {})
            if str(replacement.get("event", "")).lower() != event: continue
            selector = dict(replacement.get("selector") or {})
            if selector and not any(isinstance(item, CardInstance) and self.modifier_matches({"selector": selector}, item, self.owner_of(item) or actor) for item in target_items): continue
            operation = str(replacement.get("operation", "reduce")).lower()
            amount = self.modifier_amount(replacement)
            before = result
            if operation in ["set", "replace"]: result = amount
            elif operation in ["multiply", "scale"]: result = int(result * amount)
            elif operation in ["increase", "add"]: result += amount
            elif operation in ["prevent", "negate", "cancel"]: result = 0
            elif operation in ["cap", "maximum"]: result = min(result, amount)
            else: result = max(0, result - amount)
            self.last_replacement_records.append({"id": record.get("id", ""), "operation": operation, "before": before, "after": result, "amount": amount})
            if replacement.get("once"):
                record["status"] = "consumed"
            if result <= 0: break
        self.continuous_effects = [item for item in self.continuous_effects if item.get("status") == "active"]
        return max(0, result)

    def modifier_matches(self, modifier, card, side):
        selector = dict(modifier.get("selector") or {})
        if modifier.get("family") is not None: selector.setdefault("family", modifier["family"])
        if modifier.get("card_kind") is not None: selector.setdefault("card_kind", modifier["card_kind"])
        selector.setdefault("zone", "monster")
        owner = modifier.get("owner")
        if owner: return owner == side.name and SelectorRuntime(self, side).matches(card, selector)
        if selector.get("side") == "self": selector["side"] = "self"
        return SelectorRuntime(self, side, self.field_card).matches(card, selector)

    def modifier_amount(self, modifier):
        value = modifier.get("amount", 0)
        if isinstance(value, dict): value = value.get("value", 0)
        try: return int(value)
        except (TypeError, ValueError): return 0

    def effective_stat(self, card, side, stat):
        base = card.atk if stat == "attack" else card.defense
        for record in self.modifier_records():
            modifier = record["modifier"]
            if modifier.get("stat", "attack") != stat: continue
            if not self.modifier_matches(modifier, card, side): continue
            amount = self.modifier_amount(modifier)
            if modifier.get("operation", "add") == "set": base = amount
            elif modifier.get("operation", "add") == "multiply": base = int(base * amount)
            else: base += amount
        return base

    def effective_atk(self, card, side):
        return self.effective_stat(card, side, "attack")

    def effective_defense(self, card, side):
        return self.effective_stat(card, side, "defense")

    def record_summon(self, card, actor, method, source_zone, source_card=None, source_effect_id=""):
        card.summon_method = method
        card.summon_source_zone = source_zone
        source_definition = getattr(source_card, "card", source_card) if source_card else None
        card.summon_source_card_id = getattr(source_definition, "id", "") if source_definition else ""
        card.summon_source_card_name = getattr(source_definition, "name", "") if source_definition else ""
        card.summon_source_effect_id = source_effect_id
        card.summon_history.append({"method": method, "source_zone": source_zone, "source_card_id": card.summon_source_card_id, "source_card_name": card.summon_source_card_name, "source_effect_id": source_effect_id, "actor": actor.character.id, "turn": self.turn, "phase": self.phase})
        self.emit_event("summon", actor, source=card, target=card, metadata={"method": method, "source_zone": source_zone, "source_card_id": card.summon_source_card_id, "source_card_name": card.summon_source_card_name, "source_effect_id": source_effect_id})

    def special_summon(self, selector, actor=None, method="special", source_card=None, source_effect_id="", count=None, selected=None):
        actor = actor or self.player
        if self.finished: return False, "The duel is already finished."
        zone_count = sum(1 for item in actor.monsters if item is None)
        candidate_selector = dict(selector or {})
        candidate_selector["count"] = "all"
        candidates = list(selected or SelectorRuntime(self, actor, source_card).select(candidate_selector))
        candidates = [item for item in candidates if isinstance(item, CardInstance) and item.card.kind in ["normal", "effect", "fusion", "ritual", "legendary"]]
        requested = max(1, int(count or selector.get("count", 1) or 1))
        if not candidates: return False, "No legal monster matches the special-summon selector."
        if zone_count < min(requested, len(candidates)): return False, "There are not enough empty monster zones."
        if selected is None and len(candidates) > requested:
            self.pending_summon = {"selector": dict(selector or {}), "actor": actor, "method": method, "source_card": source_card, "source_effect_id": source_effect_id, "candidates": candidates, "required": requested}
            self.notify("choose_target", f"Choose {requested} monster(s) to special summon.", ["ok"], {"kind": "special_summon", "required": requested, "candidates": [item.card.id for item in candidates]})
            return False, "pending"
        summoned = []
        for summoned_card in candidates[:requested]:
            source_owner = self.owner_of(summoned_card)
            source_zone = summoned_card.position
            if source_owner: source_owner.remove(summoned_card)
            empty_zone = next(index for index, item in enumerate(actor.monsters) if item is None)
            summoned_card.last_zone = source_zone
            summoned_card.position = "field"
            summoned_card.face_up = True
            summoned_card.battle_position = "attack"
            summoned_card.owner = actor.name
            actor.monsters[empty_zone] = summoned_card
            self.record_summon(summoned_card, actor, method, source_zone, source_card, source_effect_id)
            summoned.append(summoned_card)
        self.log(f"{actor.name} special summons {len(summoned)} card(s).")
        self.resolution_history.append({"sequence": self.effect_sequence, "action": "special_summon", "amount": len(summoned), "source": getattr(getattr(source_card, "card", source_card), "name", "Effect"), "source_zone": getattr(source_card, "last_zone", ""), "source_actor": actor.character.id, "trigger": "special_summon", "policy": {"method": method}, "status": "resolved", "result": {"cards": [item.card.id for item in summoned], "method": method, "source_zone": [item.summon_source_zone for item in summoned]}})
        return True, summoned

    def resolve_pending_summon(self, cards):
        pending = self.pending_summon
        if not pending: return False, "No special summon choice is pending."
        selected = list(cards if isinstance(cards, list) else [cards])
        if len(selected) != pending["required"] or len(set(selected)) != len(selected) or any(item not in pending["candidates"] for item in selected): return False, "Those cards are not legal special-summon choices."
        self.pending_summon = None
        notification = self.pending_notification("choose_target")
        if notification: self.answer_notification(notification.notification_id, "ok")
        return self.special_summon(pending["selector"], pending["actor"], pending["method"], pending["source_card"], pending["source_effect_id"], pending["required"], selected)

    def procedure_material_candidates(self, card, actor, procedure=None):
        procedure = procedure or ProcedureSpec.from_card(card)
        candidates = []
        selector = dict(procedure.material_selector or {})
        if procedure.kind in ["fusion", "ritual"]: selector.setdefault("card_kind", ["normal", "effect", "fusion", "ritual", "legendary"])
        for zone in procedure.locations:
            for item in SelectorRuntime(self, actor, card).zone_items(actor, zone):
                if item is card or item in candidates: continue
                if not SelectorRuntime(self, actor, card).matches(item, selector): continue
                candidates.append(item)
        return candidates

    def validate_procedure_materials(self, card, materials, actor, procedure=None):
        procedure = procedure or ProcedureSpec.from_card(card)
        selected = list(materials or [])
        candidates = self.procedure_material_candidates(card, actor, procedure)
        if len(selected) != len(set(selected)): return False, "A procedure material cannot be selected twice."
        if any(item not in candidates for item in selected): return False, "Every procedure material must be in an allowed source zone and match its selector."
        if procedure.kind == "fusion":
            selected_ids = sorted(item.card.id for item in selected)
            required_ids = sorted(procedure.required_card_ids)
            if procedure.exact and selected_ids != required_ids: return False, "The exact fusion material set is not available."
            if not procedure.exact and not selected: return False, "Fusion requires at least one material."
        if procedure.kind == "ritual" and sum(item.card.stars for item in selected) < procedure.min_stars:
            return False, f"Ritual summoning requires {procedure.min_stars} material stars."
        if procedure.kind == "tribute" and len(selected) != procedure.required_count:
            return False, f"This normal summon requires exactly {procedure.required_count} tribute(s)."
        return True, ""

    def pay_procedure_materials(self, materials, actor, destination="graveyard"):
        if destination not in ["graveyard", "banished"]: return False, "This procedure material destination is not implemented."
        if any(not self.move_card(item, destination, actor) for item in materials): return False, f"A procedure material could not be moved to {destination}."
        return True, ""

    def place_procedure_summon(self, card, actor, method, source_zone, source_card=None, source_effect_id=""):
        zone = next((index for index, value in enumerate(actor.monsters) if value is None), None)
        if zone is None: return False, "All five monster zones are occupied."
        if card in actor.hand: actor.hand.remove(card)
        if card in actor.extra: actor.extra.remove(card)
        card.last_zone = source_zone
        card.position = "field"
        card.face_up = True
        card.battle_position = "attack"
        card.owner = actor.name
        actor.monsters[zone] = card
        self.record_summon(card, actor, method, source_zone, source_card, source_effect_id)
        return True, ""

    def capture_procedure_transaction(self):
        state = {"sides": {}, "cards": {}, "field_card": self.field_card, "field_card_owner": self.field_card_owner, "summon_permissions": {key: {"base": value.get("base", 1), "used": value.get("used", 0), "grants": [dict(grant) for grant in value.get("grants", [])]} for key, value in self.summon_permissions.items()}}
        for side in [self.player, self.opponent]:
            state["sides"][id(side)] = {"side": side, "hp": side.hp, "deck": list(side.deck), "hand": list(side.hand), "monsters": list(side.monsters), "spells": list(side.spells), "graveyard": list(side.graveyard), "banished": list(side.banished), "extra": list(side.extra)}
            cards = side.deck + side.hand + [item for item in side.monsters + side.spells if item] + side.graveyard + side.banished + side.extra
            for card in cards: state["cards"][id(card)] = {"card": card, "position": card.position, "last_zone": card.last_zone, "face_up": card.face_up}
        if self.field_card: state["cards"][id(self.field_card)] = {"card": self.field_card, "position": self.field_card.position, "last_zone": self.field_card.last_zone, "face_up": self.field_card.face_up}
        return state

    def rollback_procedure_transaction(self, transaction):
        if not transaction: return
        for saved in transaction["sides"].values():
            side = saved["side"]
            side.hp = saved["hp"]
            side.deck = list(saved["deck"])
            side.hand = list(saved["hand"])
            side.monsters = list(saved["monsters"])
            side.spells = list(saved["spells"])
            side.graveyard = list(saved["graveyard"])
            side.banished = list(saved["banished"])
            side.extra = list(saved["extra"])
        for saved in transaction["cards"].values():
            card = saved["card"]
            card.position = saved["position"]
            card.last_zone = saved["last_zone"]
            card.face_up = saved["face_up"]
        self.field_card = transaction["field_card"]
        self.field_card_owner = transaction["field_card_owner"]
        self.summon_permissions = {key: {"base": value.get("base", 1), "used": value.get("used", 0), "grants": [dict(grant) for grant in value.get("grants", [])]} for key, value in transaction["summon_permissions"].items()}

    def abort_procedure(self, reason):
        pending = self.pending_procedure
        if pending: self.rollback_procedure_transaction(pending.get("transaction"))
        self.pending_procedure = None
        self.pending_cost = None
        notification = self.pending_notification("choose_cards")
        if notification: notification.status, notification.answer = "resolved", "cancel"
        return False, reason

    def prompt_summon_procedure(self):
        pending = self.pending_procedure
        if not pending: return False, "No summon procedure is pending."
        card, actor, procedure = pending["card"], pending["actor"], pending["procedure"]
        candidates = self.procedure_material_candidates(card, actor, procedure)
        required = len(procedure.required_card_ids) if procedure.kind == "fusion" and procedure.exact else procedure.required_count
        if procedure.kind == "fusion" and len(candidates) < required: return self.abort_procedure("There are not enough legal fusion materials.")
        if procedure.kind == "ritual" and sum(item.card.stars for item in candidates) < procedure.min_stars: return self.abort_procedure("There are not enough legal ritual material stars.")
        if procedure.kind == "tribute" and len(candidates) < procedure.required_count: return self.abort_procedure("There are not enough legal tribute candidates.")
        pending.update({"candidates": candidates, "selected": [], "required": required, "snapshot": [self.entity_id(item) for item in candidates]})
        payload = {"kind": "procedure_materials", "procedure": procedure.kind, "card": card.card.id, "candidate_ids": [self.entity_id(item) for item in candidates], "required": required, "min_stars": procedure.min_stars, "locations": list(procedure.locations), "exact": procedure.exact, "material_destination": procedure.material_destination, "selected_ids": [], "selected_stars": 0}
        self.notify("choose_cards", f"Choose materials for {card.card.name}.", ["ok"], payload)
        return True, "pending_procedure"

    def begin_summon_procedure(self, card, actor, procedure=None):
        procedure = procedure or ProcedureSpec.from_card(card)
        source_zone = "extra" if procedure.kind == "fusion" else "hand"
        source_cards = actor.extra if procedure.kind == "fusion" else actor.hand
        if card not in source_cards: return False, "Select a summon card from its legal source zone."
        if procedure.source_selector and not SelectorRuntime(self, actor, card).matches(card, procedure.source_selector): return False, "The summon card is not in its allowed source state."
        if procedure.source_selector.get("zone") and str(procedure.source_selector.get("zone")) not in [str(card.position), "hand"]: return False, "The summon card is not in its allowed source zone."
        if procedure.kind not in ["fusion", "ritual", "tribute"]: return False, "This summon procedure is not implemented."
        if procedure.special: return False, "This monster requires an authored special summon procedure."
        if procedure.kind == "tribute" and self.normal_summon_remaining(actor) <= 0: return False, "No normal summon permission remains this turn."
        if not any(value is None for value in actor.monsters): return False, "All five monster zones are occupied."
        if procedure.costs:
            cost_spec = EffectSpec.from_dict({"id": card.card.id + "_procedure_cost", "trigger": "summon", "cost": procedure.costs}, card.card.id + "_procedure_cost")
            valid, result = self.preflight_costs(cost_spec, card, actor)
            if not valid: return False, result.get("reason", "The summon procedure cost cannot be paid.")
        self.pending_procedure = {"card": card, "actor": actor, "procedure": procedure, "candidates": [], "selected": [], "required": 0, "snapshot": [], "costs_paid": False, "transaction": self.capture_procedure_transaction()}
        if procedure.costs:
            paid, result = self.pay_costs(cost_spec, card, actor, 0, "procedure_cost")
            if not paid:
                if result.get("status") == "pending":
                    if self.pending_cost: self.pending_cost.update({"kind": "procedure_cost", "procedure": procedure})
                    notification = self.pending_notification("choose_cards")
                    if notification: notification.payload.update({"kind": "procedure_cost", "procedure": procedure.kind, "card": card.card.id})
                    return True, "pending_cost"
                return self.abort_procedure(result.get("reason", "The summon procedure cost could not be paid."))
            self.pending_procedure["costs_paid"] = True
        return self.prompt_summon_procedure()

    def toggle_procedure_material(self, material):
        pending = self.pending_procedure
        if not pending: return False, "No summon procedure is pending."
        if material not in pending["candidates"]: return False, "That card is not a legal procedure material."
        selected = pending["selected"]
        if material in selected:
            selected.remove(material)
        else:
            if pending["procedure"].kind in ["fusion", "tribute"] and pending["required"] and len(selected) >= pending["required"]:
                return False, "The required number of fusion materials is already selected."
            selected.append(material)
        notification = self.pending_notification("choose_cards")
        if notification:
            notification.payload["selected_ids"] = [self.entity_id(item) for item in selected]
            notification.payload["selected_stars"] = sum(item.card.stars for item in selected)
        return True, ""

    def cancel_pending_procedure(self):
        if not self.pending_procedure: return False
        self.rollback_procedure_transaction(self.pending_procedure.get("transaction"))
        self.pending_cost = None
        self.pending_procedure = None
        notification = self.pending_notification("choose_cards")
        if notification:
            notification.status, notification.answer = "resolved", "cancel"
        return True

    def procedure_selection_summary(self):
        pending = self.pending_procedure
        if not pending: return ""
        selected = pending["selected"]
        stars = sum(item.card.stars for item in selected)
        if pending["procedure"].kind == "ritual": return f"{len(selected)} material(s), {stars}/{pending['procedure'].min_stars} stars"
        return f"{len(selected)}/{pending['required']} material(s)"

    def resolve_pending_procedure(self, materials=None):
        pending = self.pending_procedure
        if not pending: return False, "No summon procedure is pending."
        if materials is None: materials = pending["selected"]
        selected = list(materials if isinstance(materials, list) else [materials])
        valid, reason = self.validate_procedure_materials(pending["card"], selected, pending["actor"], pending["procedure"])
        if not valid: return False, reason
        card, actor, procedure = pending["card"], pending["actor"], pending["procedure"]
        paid, reason = self.pay_procedure_materials(selected, actor, procedure.material_destination)
        if not paid: return self.abort_procedure(reason)
        if procedure.kind == "tribute":
            permission, reason = self.consume_normal_summon(actor)
            if not permission: return self.abort_procedure(reason)
        source_zone = card.position
        placed, reason = self.place_procedure_summon(card, actor, procedure.source_method or procedure.kind, source_zone, None, procedure.kind + "_procedure")
        if not placed: return self.abort_procedure(reason)
        self.pending_procedure = None
        notification = self.pending_notification("choose_cards")
        if notification: notification.status, notification.answer = "resolved", "ok"
        self.log(f"{actor.name} {procedure.kind} summons {card.card.name}.")
        self.react(procedure.kind + "_summon", actor.character.id, self.other(actor).character.id, "opponent", "cards", card.card.id)
        self.run_logic(card, "summon", actor, self.other(actor))
        return True, ""

    def _manual_procedure_summon(self, card, actor, kind, materials):
        procedure = ProcedureSpec.from_card(card)
        if procedure.kind != kind: return False, "The card does not declare the requested summon procedure."
        started = self.begin_summon_procedure(card, actor, procedure)
        if not started[0]: return started
        if self.pending_cost: return True, "pending_cost"
        return self.resolve_pending_procedure(materials)

    def fusion_summon(self, card, materials=None):
        if self.finished or self.active is not self.player or self.phase not in ["MAIN 1", "MAIN 2"]: return False, "Fusion summoning is only available during your main phase."
        if card.card.summon_method != "fusion" or card not in self.player.extra: return False, "Select a Fusion monster from the Extra Deck."
        procedure = ProcedureSpec.from_card(card)
        return self.begin_summon_procedure(card, self.player, procedure) if materials is None else self._manual_procedure_summon(card, self.player, "fusion", materials)

    def ritual_summon(self, card, tributes=None):
        if self.finished or self.active is not self.player or self.phase not in ["MAIN 1", "MAIN 2"]: return False, "Ritual summoning is only available during your main phase."
        if card.card.summon_method != "ritual" or card not in self.player.hand: return False, "Select a Ritual monster from your hand."
        procedure = ProcedureSpec.from_card(card)
        return self.begin_summon_procedure(card, self.player, procedure) if tributes is None else self._manual_procedure_summon(card, self.player, "ritual", tributes)

    def summon(self, card, actor=None):
        actor = actor or self.player
        if self.finished or self.active is not actor or self.phase not in ["MAIN 1", "MAIN 2"]:
            return False, "Summoning is only available during your main phase."
        if card not in actor.hand or card.card.kind not in ["normal", "effect", "legendary"]:
            return False, "Select a monster from your hand."
        if self.normal_summon_remaining(actor) <= 0: return False, "No normal summon permission remains this turn."
        zone = next((index for index, value in enumerate(actor.monsters) if value is None), None)
        if zone is None: return False, "All five monster zones are occupied."
        procedure = ProcedureSpec.normal_tribute(card, self.store.rules)
        if procedure.special: return False, "This monster requires its authored special summon procedure."
        if procedure.required_count: return self.begin_summon_procedure(card, actor, procedure)
        permission, reason = self.consume_normal_summon(actor)
        if not permission: return False, reason
        source_zone = card.position
        actor.hand.remove(card)
        card.last_zone = source_zone
        card.position = "field"
        card.face_up = True
        card.battle_position = "attack"
        actor.monsters[zone] = card
        self.log(f"{actor.name} summons {card.card.name}.")
        self.react("summon", actor.character.id, self.other(actor).character.id, "opponent", "cards", card.card.id)
        self.record_summon(card, actor, "normal", source_zone)
        self.run_logic(card, "summon", actor, self.other(actor))
        return True, ""

    def set_card(self, card, actor=None):
        actor = actor or self.player
        if self.finished or self.active is not actor or self.phase not in ["MAIN 1", "MAIN 2"]:
            return False, "Setting is only available during your main phase."
        if card not in actor.hand: return False, "Select a card in the acting side's hand."
        is_monster = card.card.kind in ["normal", "effect", "legendary"]
        target = actor.monsters if is_monster else actor.spells
        zone = next((index for index, value in enumerate(target) if value is None), None)
        if zone is None: return False, "That zone is full."
        if is_monster and self.normal_summon_remaining(actor) <= 0: return False, "No normal summon or set permission remains this turn."
        if is_monster:
            permission, reason = self.consume_normal_summon(actor)
            if not permission: return False, reason
        actor.hand.remove(card)
        card.position = "set"
        card.face_up = False
        if is_monster: card.battle_position = "defense"
        target[zone] = card
        self.log(f"{actor.name} sets a card.")
        self.emit_event("set", actor, source=card, target=card, metadata={"zone": "monster" if is_monster else "spell_trap", "face_up": False})
        self.react("set", actor.character.id, self.other(actor).character.id, "opponent", "cards", card.card.id)
        return True, ""

    def activate(self, card, actor=None):
        actor = actor or self.player
        if self.finished or self.active is not actor or self.phase not in ["MAIN 1", "MAIN 2"]:
            return False, "Activation is only available during the acting side's main phase."
        if card not in actor.hand or card.card.kind not in ["spell", "field"]: return False, "Select a spell or field card in the acting side's hand."
        if card.card.timing not in ["main", "any"]: return False, "This card is waiting for a different timing window."
        effect_specs = [EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index)) for index, raw in enumerate(card.card.effects)]
        activate_spec = next((spec for spec in effect_specs if spec.trigger == "activate"), None)
        selector = activate_spec.selector if activate_spec and activate_spec.selector else self.legacy_selector(card, actor)
        raw_required = selector.get("count", card.card.target_count or 0) if selector else 0
        try: required = 0 if raw_required == "all" else int(raw_required or 0)
        except (TypeError, ValueError): required = 0
        if selector and required:
            candidates = self.legal_targets(card, actor, selector)
            if not candidates: return False, "This card has no legal target in the current field state."
            if required > len(candidates): return False, "This card requires more legal targets than are currently available."
            self.pending_target = {"card": card, "trigger": "activate", "actor": actor, "selected": [], "candidates": candidates, "selector": selector, "required": required, "target_policy": activate_spec.target_policy if activate_spec else {"revalidate": False}, "snapshot": [self.entity_id(item) for item in candidates]}
            self.notify("choose_target", f"Select {required} legal target(s) for {card.card.name}.", ["ok"], {"card": card.card.id, "count": required})
            self.log(f"Select {required} legal target(s) for {card.card.name}.")
            return True, ""
        actor.hand.remove(card)
        if card.card.kind == "field":
            if self.field_card:
                old = self.field_card
                owner = self.field_card_owner or self.other(actor)
                old.position = "graveyard"
                owner.graveyard.append(old)
            self.field_card = card
            self.field_card_owner = actor
            card.position = "field"
            self.log(f"{actor.name} activates field card {card.card.name}.")
        else:
            card.position = "graveyard"
            actor.graveyard.append(card)
            self.log(f"{actor.name} activates {card.card.name}.")
        self.emit_event("activate", actor, source=card, target=self.other(actor), metadata={"zone": "field" if card.card.kind == "field" else "graveyard"}, include_source=False)
        self.react("activate", actor.character.id, self.other(actor).character.id, "opponent", "cards", card.card.id)
        if self.chain_enabled(activate_spec):
            self.add_chain_link(card, activate_spec, actor, self.other(actor), "activate", {"target_snapshot": [self.other(actor).character.id]})
        else:
            self.resolve(card, "activate", actor=actor, target=self.other(actor))
            self.run_logic(card, "activate", actor, self.other(actor))
        return True, ""

    def owner_of(self, card):
        for duelist in [self.player, self.opponent]:
            if card in duelist.deck or card in duelist.hand or card in duelist.graveyard or card in duelist.banished or card in duelist.extra or card in duelist.monsters or card in duelist.spells: return duelist
        if card is self.field_card: return self.field_card_owner
        return None

    def move_card(self, card, destination, owner=None):
        owner = owner or self.owner_of(card)
        if not owner or not card or destination not in ["graveyard", "banished", "hand", "deck", "extra"]: return False
        if card is self.field_card:
            self.field_card = None
            self.field_card_owner = None
        card.last_zone = card.position
        owner.remove(card)
        card.position = destination
        if destination == "graveyard":
            card.face_up = True
            owner.graveyard.append(card)
        elif destination == "banished":
            card.face_up = True
            owner.banished.append(card)
        elif destination == "hand":
            card.face_up = True
            owner.hand.append(card)
        elif destination == "deck":
            card.face_up = False
            card.position = "deck"
            owner.deck.append(card)
        elif destination == "extra":
            card.face_up = False
            card.position = "extra"
            owner.extra.append(card)
        else:
            return False
        self.emit_event("movement", owner, source=card, target=card, metadata={"from_zone": card.last_zone, "to_zone": destination, "owner": owner.character.id})
        return True

    def normalize_event_window(self, trigger, actor=None, source=None, target=None, metadata=None):
        legacy = dict(getattr(self.place, "event_response_policies", {}).get(trigger, {}) or {})
        authored_registry = getattr(self.place, "event_window_policies", {})
        authored = dict(authored_registry.get(trigger, authored_registry.get("*", {})) or {})
        policy = {**legacy, **authored}
        phases = policy.get("phases", policy.get("phase", []))
        phases = phases if isinstance(phases, list) else [phases] if phases else []
        normalized_phases = [str(item).lower().replace(" ", "_") for item in phases]
        events = policy.get("events", policy.get("triggers", [trigger]))
        events = events if isinstance(events, list) else [events]
        normalized = dict(policy)
        normalized.update({"event": trigger, "events": [str(item) for item in events], "phases": normalized_phases, "actor": self.side_key(actor) if actor else "", "source": self.entity_id(source), "target": [self.entity_id(item) for item in (target if isinstance(target, list) else [target] if target is not None else [])]})
        if normalized_phases and self.phase.lower().replace(" ", "_") not in normalized_phases and self.phase.lower() not in normalized_phases: normalized["enabled"] = False
        if events and trigger not in events and "any" not in events: normalized["enabled"] = False
        return normalized

    def normalize_event_response_policy(self, policy=None):
        raw = dict(policy or {})
        phases = raw.get("phases", raw.get("phase", []))
        phases = [str(item).lower() for item in (phases if isinstance(phases, list) else [phases])] if phases else []
        source_kinds = raw.get("source_kinds", raw.get("source_kind", []))
        source_kinds = [str(item).lower() for item in (source_kinds if isinstance(source_kinds, list) else [source_kinds])] if source_kinds else []
        target_zones = raw.get("target_zones", raw.get("target_zone", []))
        target_zones = [str(item).lower() for item in (target_zones if isinstance(target_zones, list) else [target_zones])] if target_zones else []
        try: min_speed = max(1, min(3, int(raw.get("min_speed", 1))))
        except (TypeError, ValueError): min_speed = 1
        try: max_speed = max(min_speed, min(3, int(raw.get("max_speed", 3))))
        except (TypeError, ValueError): max_speed = 3
        return {"enabled": bool(raw.get("enabled", False)), "mandatory": bool(raw.get("mandatory", False)), "allow_pass": bool(raw.get("allow_pass", not raw.get("mandatory", False))), "priority": str(raw.get("priority", "opposite")).lower(), "response_trigger": str(raw.get("response_trigger", "") or ""), "min_speed": min_speed, "max_speed": max_speed, "phases": phases, "source_kinds": source_kinds, "target_zones": target_zones}

    def open_event_response_window(self, trigger, actor, source=None, target=None, metadata=None):
        if self.chain_window or actor is None: return None
        policy = self.normalize_event_response_policy((metadata or {}).get("response_policy", {}))
        priority_key = policy["priority"]
        priority = self.player if priority_key == "player" else self.opponent if priority_key == "opponent" else self.other(actor)
        response_trigger = policy["response_trigger"] or trigger
        candidates = self.response_candidates(priority, response_trigger, policy, source, target)
        if not candidates: return None
        context = dict(metadata or {})
        context.update({"event_window": True, "event_trigger": trigger, "response_trigger": response_trigger, "response_policy": policy, "mandatory": policy["mandatory"], "allow_pass": policy["allow_pass"], "event_actor": self.side_key(actor), "event_source": self.entity_id(source), "event_target": [self.entity_id(item) for item in (target if isinstance(target, list) else [target] if target is not None else [])]})
        return self.open_chain_window(priority, response_trigger, source, target, context)

    def open_chain_window(self, actor, trigger, source=None, target=None, context=None):
        if self.chain_window: return self.chain_window
        self.chain_sequence += 1
        chain_context = dict(context or {})
        chain_context.setdefault("mandatory", False)
        chain_context.setdefault("allow_pass", not chain_context.get("mandatory", False))
        self.chain_window = {"chain_id": "chain_" + str(self.chain_sequence), "trigger": trigger, "source": source, "target": target, "opened_by": self.side_key(actor), "priority": actor, "passes": [], "context": chain_context}
        self.chain_priority = actor
        self.chain_passes = []
        payload = self.chain_prompt_payload()
        self.notify("chain_response", "Chain response window is open.", ["pass", "card"] if payload["allow_pass"] else ["card"], payload)
        return self.chain_window

    def response_candidates(self, side=None, trigger=None, policy=None, event_source=None, event_target=None):
        if not self.chain_window and not trigger: return []
        side = side or self.chain_priority
        trigger = trigger or self.chain_window.get("trigger", "")
        policy = self.normalize_event_response_policy(policy or (self.chain_window.get("context", {}).get("response_policy", {}) if self.chain_window else {}))
        if policy.get("phases") and self.phase.lower() not in policy["phases"]: return []
        event_source = event_source if event_source is not None else (self.chain_window.get("source") if self.chain_window else None)
        event_target = event_target if event_target is not None else (self.chain_window.get("target") if self.chain_window else None)
        if policy.get("source_kinds") and (not isinstance(event_source, CardInstance) or event_source.card.kind.lower() not in policy["source_kinds"]): return []
        event_targets = event_target if isinstance(event_target, list) else [event_target] if event_target is not None else []
        if policy.get("target_zones") and any(str(getattr(item, "position", "")).lower() not in policy["target_zones"] for item in event_targets if isinstance(item, CardInstance)): return []
        if side is None: return []
        candidates = []
        for zone, cards in [("hand", list(side.hand)), ("spell_trap", [item for item in side.spells if item])]:
            for card in cards:
                if card.card.kind not in ["spell", "field", "trap"]: continue
                for index, raw_effect in enumerate(card.card.effects):
                    spec = EffectSpec.from_dict(raw_effect, card.card.id + "_effect_" + str(index))
                    if spec.validate(): continue
                    response_events = spec.response.get("triggers", spec.response.get("events", [trigger]))
                    response_events = response_events if isinstance(response_events, list) else [response_events]
                    if not spec.response.get("enabled", False) and spec.trigger not in ["respond", "chain_response"]: continue
                    if trigger not in response_events and "any" not in response_events: continue
                    if spec.speed < max(2, policy["min_speed"]) or spec.speed > policy["max_speed"] or not self.chain_speed_allowed(spec.speed, side): continue
                    if self.effect_used(card, spec): continue
                    if not self.condition_matches(spec.conditions, card, side, self.other(side)): continue
                    selector = spec.selector or self.legacy_selector(card, side)
                    required = int(selector.get("count", card.card.target_count or 0) or 0) if selector else 0
                    legal = self.legal_targets(card, side, selector) if selector and required else []
                    if required and len(legal) < required: continue
                    candidates.append({"card": card, "spec": spec, "zone": zone, "selector": selector, "targets": legal})
        return candidates

    def response_card_ids(self, side=None, trigger=None):
        return [item["card"].card.id for item in self.response_candidates(side, trigger)]

    def chain_prompt_payload(self):
        context = self.chain_window.get("context", {})
        candidates = self.response_card_ids(self.chain_priority, self.chain_window.get("trigger", ""))
        mandatory = bool(context.get("mandatory", False))
        allow_pass = bool(context.get("allow_pass", True)) or not mandatory or not candidates
        return {"chain_id": self.chain_window["chain_id"], "priority": self.side_key(self.chain_priority), "candidates": candidates, "mandatory": mandatory, "allow_pass": allow_pass}

    def declarative_effect_score(self, card, spec, actor, target=None):
        score = 0
        target = target or self.other(actor)
        for action in spec.actions:
            name = action.get("name", "")
            amount = action.get("amount", 0)
            if isinstance(amount, dict): amount = amount.get("value", 0)
            try: amount = int(amount or 0)
            except (TypeError, ValueError): amount = 0
            if name == "damage": score += amount * 3
            elif name == "heal": score += amount * 2 if actor.hp < 6000 else amount // 4
            elif name == "draw": score += max(1, amount) * 180
            elif name == "discard": score += max(1, amount) * 45
            elif name == "destroy": score += 500
            elif name in ["banish", "send_to_graveyard", "return_to_hand"]: score += 360
            elif name in ["boost_attack", "boost_defense"]: score += amount
            elif name == "special_summon": score += 700
            elif name == "grant_normal_summon": score += 350
            elif name == "negate_chain": score += 5000
            elif name == "shuffle": score += 80
        selector = spec.selector or self.legacy_selector(card, actor)
        if selector:
            legal = self.legal_targets(card, actor, selector)
            required = int(selector.get("count", 1) or 1) if selector.get("count") != "all" else 1
            if len(legal) < required: return -100000
            score += min(5, len(legal)) * 25
            if any(isinstance(item, CardInstance) and item.owner != actor.name for item in legal): score += 40
        return score

    def ai_response_score(self, candidate, actor=None):
        actor = actor or self.opponent
        enemy = self.other(actor)
        spec = candidate["spec"]
        score = int(spec.speed) * 100 + self.declarative_effect_score(candidate["card"], spec, actor, enemy)
        if any(action.get("name") == "negate_chain" for action in spec.actions): score += 10000
        return score

    def ai_chain_step_for(self, actor):
        if self.finished or not self.chain_window or self.chain_priority is not actor: return False, "This side does not have chain priority."
        candidates = self.response_candidates(actor, self.chain_window.get("trigger", ""))
        if not candidates: return self.pass_chain_priority(actor)
        candidate = max(candidates, key=lambda item: (self.ai_response_score(item, actor), item["card"].card.id, item["spec"].effect_id))
        selector = candidate["selector"]
        required = int(selector.get("count", candidate["card"].card.target_count or 0) or 0) if selector else 0
        target = None
        if required:
            legal = list(candidate["targets"])
            if len(legal) < required: return self.pass_chain_priority(actor)
            ranked = sorted(legal, key=lambda item: (self.ai_target_score(item, actor, candidate["spec"]), self.entity_id(item)))
            target = ranked[-1] if required == 1 else ranked[-required:]
        result = self.begin_response_card(candidate["card"], candidate["spec"].effect_id, actor, target)
        if not result[0] and result[1] not in ["pending", "pending_cost"]: return self.pass_chain_priority(actor)
        return result

    def ai_chain_step(self): return self.ai_chain_step_for(self.opponent)

    def consume_chain_response_prompt(self):
        notification = self.pending_notification("chain_response")
        if notification:
            notification.status, notification.answer = "resolved", "card"
            self.notification_history.append({"id": notification.notification_id, "kind": notification.kind, "answer": notification.answer, "payload": notification.payload, "time": time.time()})

    def begin_response_card(self, card, effect_id="", actor=None, target=None):
        actor = actor or self.chain_priority
        candidate = next((item for item in self.response_candidates(actor) if item["card"] is card and (not effect_id or item["spec"].effect_id == effect_id)), None)
        if not candidate: return False, "That card is not a legal response in the current chain window."
        if actor is not self.chain_priority: return False, "That side does not have chain priority."
        self.consume_chain_response_prompt()
        spec, selector = candidate["spec"], candidate["selector"]
        required = int(selector.get("count", card.card.target_count or 0) or 0) if selector else 0
        if required and target is None:
            self.pending_response = {"card": card, "spec": spec, "actor": actor, "selector": selector, "candidates": candidate["targets"], "required": required}
            self.notify("choose_target", f"Select {required} target(s) for {card.card.name}.", ["ok"], {"kind": "chain_response_target", "card": card.card.id, "effect": spec.effect_id, "required": required})
            return True, "pending"
        if required:
            selected = target if isinstance(target, list) else [target]
            if len(selected) != required or any(item not in candidate["targets"] for item in selected): return False, "That response target is not legal."
            target = selected[0] if required == 1 else selected
        target = target or self.other(actor)
        paid, result = self.pay_costs(spec, card, actor)
        if not paid:
            if result.get("status") == "pending":
                if self.pending_cost: self.pending_cost.update({"kind": "response_cost", "response_target": target, "response_effect_id": spec.effect_id})
                return True, "pending_cost"
            return False, result.get("reason", "The response cost could not be paid.")
        owner = self.owner_of(card) or actor
        owner.remove(card)
        card.face_up = True
        card.position = "graveyard"
        owner.graveyard.append(card)
        return self.add_chain_link(card, spec, actor, target or self.other(actor), spec.trigger, {"response": True, "cost_paid": True, "target_snapshot": [self.entity_id(item) for item in (target if isinstance(target, list) else [target] if target is not None else [])]})

    def resolve_pending_response(self, cards):
        pending = self.pending_response
        if not pending: return False, "No chain response target is pending."
        selected = list(cards if isinstance(cards, list) else [cards])
        if len(selected) != pending["required"] or len(set(selected)) != len(selected) or any(item not in pending["candidates"] for item in selected): return False, "Those response targets are not legal."
        self.pending_response = None
        notification = self.pending_notification("choose_target")
        if notification: notification.status, notification.answer = "resolved", "ok"
        return self.begin_response_card(pending["card"], pending["spec"].effect_id, pending["actor"], selected[0] if pending["required"] == 1 else selected)

    def record_observation(self, kind, payload=None):
        if self.observation_guard: return None
        self.observation_sequence += 1
        record = {"sequence": self.observation_sequence, "kind": str(kind), "turn": self.turn, "phase": self.phase, "active": self.side_key(self.active), "payload": dict(payload or {})}
        self.observation_log.append(record)
        self.observation_log = self.observation_log[-512:]
        return record

    def card_instances(self):
        result = []
        for side in [self.player, self.opponent]:
            result.extend([item for item in side.deck if item])
            result.extend([item for item in side.hand if item])
            result.extend([item for item in side.graveyard if item])
            result.extend([item for item in side.banished if item])
            result.extend([item for item in side.extra if item])
            result.extend([item for item in side.monsters if item])
            result.extend([item for item in side.spells if item])
        if self.field_card: result.append(self.field_card)
        return list(dict.fromkeys(result))

    def visibility(self, viewer, card):
        viewer_side = viewer if isinstance(viewer, Duelist) else self.player if str(viewer) == "player" else self.opponent if str(viewer) == "opponent" else None
        owner = self.owner_of(card)
        if viewer_side is owner: return "private"
        if card.position in ["graveyard", "banished"]: return "public"
        if card.position in ["field", "monster", "spell_trap"] and card.face_up: return "public"
        return "hidden"

    def public_card_record(self, viewer, card):
        state = self.visibility(viewer, card)
        if state == "hidden": return {"id": "hidden", "kind": "hidden", "position": card.position, "face_up": False}
        return {"id": card.card.id, "name": card.card.name, "kind": card.card.kind, "position": card.position, "face_up": bool(card.face_up), "battle_position": card.battle_position, "visibility": state}

    def observe_visible_information(self, viewer):
        viewer_key = self.side_key(viewer) if isinstance(viewer, Duelist) else str(viewer)
        if viewer_key not in self.knowledge: return
        known_cards = set(self.knowledge[viewer_key].get("card_ids", []))
        known_effects = set(self.knowledge[viewer_key].get("effect_ids", []))
        effect_facts = dict(self.knowledge[viewer_key].get("effect_facts", {}))
        for card in self.card_instances():
            if self.visibility(viewer, card) == "hidden": continue
            known_cards.add(card.card.id)
            for index, raw in enumerate(card.card.effects):
                spec = EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index))
                known_effects.add(spec.effect_id)
                effect_facts[spec.effect_id] = {"trigger": spec.trigger, "actions": [action.get("name", "") for action in spec.actions], "speed": spec.speed, "optional": spec.optional}
        self.knowledge[viewer_key] = {"card_ids": sorted(known_cards), "effect_ids": sorted(known_effects), "effect_facts": effect_facts}

    def knowledge_for(self, viewer="player"):
        viewer_key = self.side_key(viewer) if isinstance(viewer, Duelist) else str(viewer)
        self.observe_visible_information(viewer_key)
        return {"viewer": viewer_key, "card_ids": list(self.knowledge.get(viewer_key, {}).get("card_ids", [])), "effect_ids": list(self.knowledge.get(viewer_key, {}).get("effect_ids", [])), "effect_facts": dict(self.knowledge.get(viewer_key, {}).get("effect_facts", {}))}

    def export_knowledge(self):
        return {key: {"card_ids": list(value.get("card_ids", [])), "effect_ids": list(value.get("effect_ids", [])), "effect_facts": dict(value.get("effect_facts", {}))} for key, value in self.knowledge.items()}

    def import_knowledge(self, payload):
        if not isinstance(payload, dict): return False
        known_cards = {item.card.id for item in self.card_instances()}
        known_effects = {spec.effect_id for item in self.card_instances() for index, raw in enumerate(item.card.effects) for spec in [EffectSpec.from_dict(raw, item.card.id + "_effect_" + str(index))]}
        for key in ["player", "opponent"]:
            value = payload.get(key, {}) if isinstance(payload.get(key, {}), dict) else {}
            allowed_effects = {str(item) for item in value.get("effect_ids", []) if str(item) in known_effects}
            self.knowledge[key] = {"card_ids": sorted({str(item) for item in value.get("card_ids", []) if str(item) in known_cards}), "effect_ids": sorted(allowed_effects), "effect_facts": {str(effect_id): dict(fact) for effect_id, fact in value.get("effect_facts", {}).items() if str(effect_id) in allowed_effects and isinstance(fact, dict)}}
        return True

    def public_state(self, viewer="player"):
        self.observe_visible_information(viewer)
        state = {"turn": self.turn, "phase": self.phase, "active": self.side_key(self.active), "finished": self.finished, "winner": self.side_key(self.winner) if self.winner else "", "players": [], "knowledge": self.knowledge_for(viewer)}
        for side in [self.player, self.opponent]:
            state["players"].append({"id": side.character.id, "hp": side.hp, "hand": [self.public_card_record(viewer, item) for item in side.hand], "deck_count": len(side.deck), "graveyard": [self.public_card_record(viewer, item) for item in side.graveyard], "banished": [self.public_card_record(viewer, item) for item in side.banished], "monsters": [self.public_card_record(viewer, item) if item else None for item in side.monsters], "spells": [self.public_card_record(viewer, item) if item else None for item in side.spells]})
        return state

    def live_observation(self, viewer="player"):
        self.observe_visible_information(viewer)
        result = []
        known = {item.card.id for item in self.card_instances() if self.visibility(viewer, item) != "hidden"}
        for record in self.observation_log:
            copy = {"sequence": record["sequence"], "kind": record["kind"], "turn": record["turn"], "phase": record["phase"], "active": record["active"], "payload": dict(record.get("payload") or {})}
            payload = copy["payload"]
            for key in ["source_card_id", "card_id", "source", "target_card_id"]:
                if key in payload and payload[key] not in known: payload[key] = "hidden"
            if isinstance(payload.get("card_ids"), list): payload["card_ids"] = [item if item in known else "hidden" for item in payload["card_ids"]]
            result.append(copy)
        return result

    def live_snapshot(self, viewer="player"):
        return {"schema": "cbp.live-observation.v1", "viewer": self.side_key(viewer) if isinstance(viewer, Duelist) else str(viewer), "state": self.public_state(viewer), "events": self.live_observation(viewer), "knowledge": self.knowledge_for(viewer)}

    def checkpoint_card(self, card):
        return {"card_id": card.card.id, "owner": card.owner, "variant": card.variant, "position": card.position, "last_zone": card.last_zone, "face_up": bool(card.face_up), "battle_position": card.battle_position, "summon_method": card.summon_method, "summon_source_zone": card.summon_source_zone, "summon_source_card_id": card.summon_source_card_id, "summon_source_card_name": card.summon_source_card_name, "summon_source_effect_id": card.summon_source_effect_id, "summon_history": list(card.summon_history), "attack_bonus": card.attack_bonus, "defense_bonus": card.defense_bonus, "attacked": bool(card.attacked)}

    def checkpoint_side(self, side):
        return {"id": side.character.id, "name": side.name, "hp": side.hp, "deck": [self.checkpoint_card(item) for item in side.deck], "hand": [self.checkpoint_card(item) for item in side.hand], "monsters": [self.checkpoint_card(item) if item else None for item in side.monsters], "spells": [self.checkpoint_card(item) if item else None for item in side.spells], "graveyard": [self.checkpoint_card(item) for item in side.graveyard], "banished": [self.checkpoint_card(item) for item in side.banished], "extra": [self.checkpoint_card(item) for item in side.extra]}

    def pending_ref(self, item):
        if isinstance(item, Duelist): return {"kind": "side", "value": self.side_key(item)}
        if isinstance(item, CardInstance): return {"kind": "card", "value": item.card.id}
        return item

    def pending_payload(self):
        if self.pending_discard: return {"kind": "discard", "owner": self.side_key(self.pending_discard)}
        if self.pending_target:
            pending = self.pending_target
            return {"kind": "target", "card": pending["card"].card.id, "actor": self.side_key(pending["actor"]), "trigger": pending.get("trigger", ""), "effect_id": pending.get("effect_id", ""), "selector": pending.get("selector", {}), "required": pending.get("required", 1), "target_policy": pending.get("target_policy", {}), "selected": [self.pending_ref(item) for item in pending.get("selected", [])], "candidates": [self.pending_ref(item) for item in pending.get("candidates", [])], "snapshot": list(pending.get("snapshot", []))}
        if self.pending_summon:
            pending = self.pending_summon
            return {"kind": "summon", "actor": self.side_key(pending["actor"]), "method": pending.get("method", "special"), "source_card": pending.get("source_card").card.id if pending.get("source_card") else "", "source_effect_id": pending.get("source_effect_id", ""), "selector": pending.get("selector", {}), "required": pending.get("required", 1), "selected": [self.pending_ref(item) for item in pending.get("selected", [])], "candidates": [self.pending_ref(item) for item in pending.get("candidates", [])]}
        if self.pending_trap: return {"kind": "trap", "trap": self.pending_trap["trap"].card.id}
        if self.pending_effect:
            pending = self.pending_effect
            return {"kind": "effect", "card": pending["card"].card.id, "actor": self.side_key(pending["actor"]), "effect_id": pending["spec"].effect_id, "target": self.pending_ref(pending.get("target"))}
        if self.pending_cost or self.pending_procedure or self.pending_response or self.pending_trigger_order: return {"kind": "unsupported_interactive", "supported": False}
        return None

    def checkpoint_chain_ref(self, item):
        return self.pending_ref(item)

    def checkpoint_chain(self):
        if not self.chain_window and not self.chain_links: return None
        window = dict(self.chain_window or {})
        for key in ["source", "target", "priority"]:
            if key in window: window[key] = self.checkpoint_chain_ref(window[key])
        window["context"] = dict(window.get("context", {}))
        return {"window": window, "priority": self.side_key(self.chain_priority) if self.chain_priority else "", "passes": list(self.chain_passes), "active_link_id": self.active_chain_link_id, "links": [{"link_id": link.link_id, "index": link.index, "source": self.checkpoint_chain_ref(link.source), "actor": self.checkpoint_chain_ref(link.actor), "target": self.checkpoint_chain_ref(link.target), "trigger": link.trigger, "effect_id": link.effect_id, "speed": link.speed, "status": link.status, "negated": link.negated, "context": dict(link.context)} for link in self.chain_links]}

    def full_state_payload(self):
        return {"schema": "cbp.state.v1", "turn": self.turn, "phase_index": self.phase_index, "active": self.side_key(self.active), "finished": self.finished, "winner": self.side_key(self.winner) if self.winner else "", "reason": self.reason, "cpu": self.cpu, "player": self.checkpoint_side(self.player), "opponent": self.checkpoint_side(self.opponent), "field_card": self.checkpoint_card(self.field_card) if self.field_card else None, "field_card_owner": self.side_key(self.field_card_owner) if self.field_card_owner else "", "effect_sequence": self.effect_sequence, "notification_sequence": self.notification_sequence, "rule_event_sequence": self.rule_event_sequence, "trigger_group_sequence": self.trigger_group_sequence, "chain_sequence": self.chain_sequence, "continuous_sequence": self.continuous_sequence, "summon_permissions": self.summon_permissions, "team_effect": self.team_effect, "opponent_team_effect": self.opponent_team_effect, "knowledge": self.export_knowledge(), "notifications": [item.__dict__.copy() for item in self.notifications], "notification_history": list(self.notification_history), "observation_sequence": self.observation_sequence, "observation_log": list(self.observation_log), "event_history": list(self.event_history), "chain_history": list(self.chain_history), "resolution_history": list(self.resolution_history), "chain": self.checkpoint_chain(), "pending": self.pending_payload()}

    def _restore_card(self, payload, owner):
        card = CardInstance(self.store.cards[payload["card_id"]], owner.name)
        for key in ["variant", "position", "last_zone", "face_up", "battle_position", "summon_method", "summon_source_zone", "summon_source_card_id", "summon_source_card_name", "summon_source_effect_id", "attack_bonus", "defense_bonus", "attacked"]:
            if key in payload: setattr(card, key, payload[key])
        card.summon_history = list(payload.get("summon_history", []))
        return card

    def _restore_side(self, side, payload):
        side.hp = int(payload.get("hp", 8000))
        side.deck, side.hand, side.graveyard, side.banished, side.extra = [], [], [], [], []
        side.monsters, side.spells = [None] * 5, [None] * 5
        for zone in ["deck", "hand", "graveyard", "banished", "extra"]:
            setattr(side, zone, [self._restore_card(item, side) for item in payload.get(zone, [])])
        side.monsters = [self._restore_card(item, side) if item else None for item in payload.get("monsters", [None] * 5)]
        side.spells = [self._restore_card(item, side) if item else None for item in payload.get("spells", [None] * 5)]

    def restore_ref(self, ref):
        if not isinstance(ref, dict): return ref
        if ref.get("kind") == "side": return self.player if ref.get("value") == "player" else self.opponent
        if ref.get("kind") == "card": return next((item for item in self.card_instances() if item.card.id == ref.get("value")), None)
        return None

    def restore_pending_payload(self, pending):
        if not isinstance(pending, dict): return True
        kind = pending.get("kind")
        if kind == "discard": self.pending_discard = self.player if pending.get("owner") == "player" else self.opponent; return True
        if kind == "trap":
            trap = next((item for item in self.card_instances() if item.card.id == pending.get("trap")), None)
            if not trap: return False
            self.pending_trap = {"trap": trap}; return True
        if kind == "target":
            card = next((item for item in self.card_instances() if item.card.id == pending.get("card")), None)
            actor = self.player if pending.get("actor") == "player" else self.opponent
            if not card: return False
            self.pending_target = {"card": card, "actor": actor, "trigger": pending.get("trigger", "activate"), "effect_id": pending.get("effect_id", ""), "selector": dict(pending.get("selector", {})), "required": int(pending.get("required", 1)), "target_policy": dict(pending.get("target_policy", {})), "selected": [self.restore_ref(item) for item in pending.get("selected", []) if self.restore_ref(item) is not None], "candidates": [self.restore_ref(item) for item in pending.get("candidates", []) if self.restore_ref(item) is not None], "snapshot": list(pending.get("snapshot", []))}; return True
        if kind == "summon":
            actor = self.player if pending.get("actor") == "player" else self.opponent
            card = next((item for item in self.card_instances() if item.card.id == pending.get("source_card")), None)
            if pending.get("source_card") and not card: return False
            self.pending_summon = {"actor": actor, "method": pending.get("method", "special"), "source_card": card, "source_effect_id": pending.get("source_effect_id", ""), "selector": dict(pending.get("selector", {})), "required": int(pending.get("required", 1)), "selected": [self.restore_ref(item) for item in pending.get("selected", []) if self.restore_ref(item) is not None], "candidates": [self.restore_ref(item) for item in pending.get("candidates", []) if self.restore_ref(item) is not None]}; return True
        if kind == "effect":
            card = next((item for item in self.card_instances() if item.card.id == pending.get("card")), None)
            actor = self.player if pending.get("actor") == "player" else self.opponent
            if not card: return False
            spec = next((EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index)) for index, raw in enumerate(card.card.effects) if EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index)).effect_id == pending.get("effect_id")), None)
            if not spec: return False
            self.pending_effect = {"card": card, "actor": actor, "spec": spec, "target": self.restore_ref(pending.get("target"))}; return True
        return kind == "unsupported_interactive"

    def restore_full_state(self, payload):
        if not isinstance(payload, dict) or payload.get("schema") != "cbp.state.v1": return False
        if payload.get("player", {}).get("id") != self.player.character.id or payload.get("opponent", {}).get("id") != self.opponent.character.id: return False
        try:
            self._restore_side(self.player, payload["player"])
            self._restore_side(self.opponent, payload["opponent"])
            self.field_card = self._restore_card(payload["field_card"], self.player if payload.get("field_card_owner") == "player" else self.opponent) if payload.get("field_card") else None
            self.field_card_owner = self.player if payload.get("field_card_owner") == "player" else self.opponent if payload.get("field_card_owner") == "opponent" else None
            self.turn, self.phase_index = int(payload.get("turn", 1)), int(payload.get("phase_index", 0))
            self.active = self.player if payload.get("active") == "player" else self.opponent
            self.finished, self.reason = bool(payload.get("finished", False)), str(payload.get("reason", ""))
            self.winner = self.player if payload.get("winner") == "player" else self.opponent if payload.get("winner") == "opponent" else None
            self.effect_sequence = int(payload.get("effect_sequence", 0)); self.notification_sequence = int(payload.get("notification_sequence", 0)); self.rule_event_sequence = int(payload.get("rule_event_sequence", 0)); self.trigger_group_sequence = int(payload.get("trigger_group_sequence", 0)); self.chain_sequence = int(payload.get("chain_sequence", 0)); self.continuous_sequence = int(payload.get("continuous_sequence", 0)); self.observation_sequence = int(payload.get("observation_sequence", 0))
            self.summon_permissions = json.loads(json.dumps(payload.get("summon_permissions", self.summon_permissions)))
            self.team_effect = dict(payload.get("team_effect", {})); self.opponent_team_effect = dict(payload.get("opponent_team_effect", {}))
            self.import_knowledge(payload.get("knowledge", {}))
            self.notifications = [Notification(**item) for item in payload.get("notifications", [])]
            self.notification_history = list(payload.get("notification_history", [])); self.observation_log = list(payload.get("observation_log", [])); self.event_history = list(payload.get("event_history", [])); self.chain_history = list(payload.get("chain_history", [])); self.resolution_history = list(payload.get("resolution_history", []))
            self.effect_queue, self.continuous_effects, self.chain_links, self.chain_window = [], [], [], None
            chain_payload = payload.get("chain")
            if chain_payload:
                restored_links = []
                for item in chain_payload.get("links", []):
                    source = self.restore_ref(item.get("source")); actor = self.restore_ref(item.get("actor")); target = self.restore_ref(item.get("target"))
                    if not isinstance(source, CardInstance) or not isinstance(actor, Duelist): return False
                    restored_links.append(ChainLink(item.get("link_id", ""), int(item.get("index", 0)), source, actor, target, item.get("trigger", ""), item.get("effect_id", ""), int(item.get("speed", 1)), item.get("status", "pending"), bool(item.get("negated", False)), dict(item.get("context", {}))))
                self.chain_links = restored_links
                self.chain_window = dict(chain_payload.get("window") or {}) if chain_payload.get("window") else None
                self.chain_priority = self.restore_ref({"kind": "side", "value": chain_payload.get("priority")}) if chain_payload.get("priority") else None
                self.chain_passes = list(chain_payload.get("passes", [])); self.active_chain_link_id = chain_payload.get("active_link_id", "")
            self.pending_discard = self.pending_target = self.pending_summon = self.pending_trap = self.pending_cost = self.pending_procedure = self.pending_effect = self.pending_response = self.pending_trigger_order = None
            return self.restore_pending_payload(payload.get("pending"))
        except (KeyError, TypeError, ValueError): return False

    def state_checkpoint(self):
        payload = self.full_state_payload()
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        pending = payload.get("pending")
        return {"schema": "cbp.state-checkpoint.v1", "sequence": self.observation_sequence, "digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(), "state": payload, "interactive_state_restored": bool(pending is None or pending.get("kind") != "unsupported_interactive")}

    def validate_state_checkpoint(self, checkpoint):
        if not isinstance(checkpoint, dict) or checkpoint.get("schema") != "cbp.state-checkpoint.v1" or not isinstance(checkpoint.get("state"), dict): return False
        canonical = json.dumps(checkpoint["state"], sort_keys=True, separators=(",", ":"), default=str)
        return checkpoint.get("digest") == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def restore_state_checkpoint(self, checkpoint):
        if not self.validate_state_checkpoint(checkpoint): return False
        return self.restore_full_state(checkpoint["state"])

    def observation_checkpoint(self, viewer="player"):
        snapshot = self.live_snapshot(viewer)
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
        return {"schema": "cbp.observation-checkpoint.v1", "sequence": self.observation_sequence, "digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(), "snapshot": snapshot}

    def validate_observation_checkpoint(self, checkpoint):
        if not isinstance(checkpoint, dict) or checkpoint.get("schema") != "cbp.observation-checkpoint.v1": return False
        snapshot = checkpoint.get("snapshot")
        if not isinstance(snapshot, dict): return False
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
        return checkpoint.get("digest") == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def restore_observation_checkpoint(self, checkpoint):
        if not self.validate_observation_checkpoint(checkpoint): return False
        snapshot = checkpoint.get("snapshot", {})
        self.import_knowledge(snapshot.get("knowledge", {}))
        return {"schema": checkpoint.get("schema"), "sequence": checkpoint.get("sequence", 0), "viewer": snapshot.get("viewer", "player"), "validated": True}

    def entity_id(self, item):
        if isinstance(item, Duelist): return item.character.id
        if isinstance(item, CardInstance): return item.card.id
        return getattr(item, "id", getattr(item, "name", ""))

    def chain_speed_allowed(self, speed, actor):
        if not self.chain_links: return True
        top_speed = self.chain_links[-1].speed
        if int(speed) <= 1: return False
        if int(speed) == 2 and top_speed > 2: return False
        if int(speed) == 3: return True
        return int(speed) >= top_speed

    def chain_enabled(self, spec):
        return bool(spec and (spec.speed > 1 or spec.response.get("enabled") or spec.response.get("chain")))

    def add_chain_link(self, card, spec, actor, target=None, trigger=None, context=None):
        if not card or not spec or not actor: return False, "A chain link requires a source card, effect, and actor."
        source_owned = card.owner == actor.name and (card in actor.hand or card in [item for item in actor.monsters + actor.spells if item] or card is self.field_card or card.last_zone in ["hand", "spell_trap", "field", "monster"])
        if not source_owned: return False, "The source card is not controlled by the acting side."
        if not self.chain_window: self.open_chain_window(actor, trigger or spec.trigger, card, target, context)
        if self.chain_priority is not actor: return False, "The other side has chain priority."
        if not self.chain_speed_allowed(spec.speed, actor): return False, "This effect cannot respond at its current spell speed."
        target_items = target if isinstance(target, list) else [target] if target is not None else []
        if spec.selector:
            legal = self.legal_targets(card, actor, spec.selector)
            required = spec.selector.get("count", 1)
            required = len(legal) if required == "all" else max(1, int(required or 1))
            if len(target_items) != required or any(item not in legal for item in target_items): return False, "The chain link targets are not legal."
        self.chain_sequence += 1
        targets = target if isinstance(target, list) else [target] if target is not None else []
        link_context = dict(context or {})
        link_context["legality"] = {"source_controller": self.side_key(actor), "speed": spec.speed, "target_ids": [self.entity_id(item) for item in targets], "target_count": len(targets), "target_snapshot": [self.entity_id(item) for item in targets]}
        link_context.update({"chain_id": self.chain_window["chain_id"], "link_index": len(self.chain_links) + 1, "target_snapshot": [self.entity_id(item) for item in targets]})
        link = ChainLink("link_" + str(self.chain_sequence), len(self.chain_links) + 1, card, actor, target, trigger or spec.trigger, spec.effect_id, spec.speed, "pending", False, link_context)
        self.chain_links.append(link)
        self.chain_history.append({"event": "link_added", "chain_id": self.chain_window["chain_id"], "link_id": link.link_id, "index": link.index, "source": card.card.id, "actor": self.side_key(actor), "speed": spec.speed, "targets": link_context["target_snapshot"]})
        self.chain_priority = self.other(actor)
        self.chain_passes = []
        payload = self.chain_prompt_payload()
        chain_options = ["pass", "card"] if payload["allow_pass"] else ["card"]
        self.notify("chain_response", "Chain response window is open.", chain_options, payload)
        return True, link

    def pass_chain_priority(self, actor):
        if not self.chain_window or self.chain_priority is not actor: return False, "That side does not have chain priority."
        if self.chain_window.get("context", {}).get("mandatory", False) and self.response_candidates(actor, self.chain_window.get("trigger", "")): return False, "A response is required in this window."
        self.chain_passes.append(self.side_key(actor))
        if len(self.chain_passes) >= 2:
            return self.resolve_chain()
        self.chain_priority = self.other(actor)
        self.notify("chain_response", "Chain response window is open.", ["pass"], self.chain_prompt_payload())
        return True, ""

    def negation_link_candidate(self, action):
        pending = [item for item in self.chain_links if item.status == "pending" and item.link_id != self.active_chain_link_id]
        reference = action.get("selector", action.get("link_id", action.get("chain_link", action.get("reference", "previous"))))
        if isinstance(reference, dict):
            selector = reference
            pending = [item for item in pending if (not selector.get("link_id") or item.link_id == selector.get("link_id")) and (not selector.get("effect_id") or item.effect_id == selector.get("effect_id")) and (not selector.get("trigger") or item.trigger == selector.get("trigger")) and (not selector.get("speed") or item.speed == int(selector.get("speed"))) and (not selector.get("actor") or self.side_key(item.actor) == str(selector.get("actor")))]
            return pending[-1] if pending else None
        text = str(reference or "previous").lower()
        if text in ["previous", "latest", "top"]: return pending[-1] if pending else None
        if text in ["oldest", "first"]: return pending[0] if pending else None
        return next((item for item in pending if item.link_id == reference), None)

    def negate_chain_link(self, link_id, source_link_id="", source_effect_id=""):
        link = next((item for item in self.chain_links if item.link_id == link_id and item.status == "pending"), None)
        if not link: return False, "That chain link is not pending."
        if source_link_id and link.link_id == source_link_id: return False, "A chain link cannot negate itself."
        link.negated = True
        link.status = "negated"
        self.chain_history.append({"event": "link_negated", "chain_id": self.chain_window["chain_id"] if self.chain_window else "", "link_id": link.link_id, "index": link.index, "source_link_id": source_link_id, "source_effect_id": source_effect_id})
        return True, ""

    def chain_link_targets_legal(self, link):
        spec = next((EffectSpec.from_dict(raw, link.source.card.id + "_effect_" + str(index)) for index, raw in enumerate(link.source.card.effects) if EffectSpec.from_dict(raw, link.source.card.id + "_effect_" + str(index)).effect_id == link.effect_id), None)
        if not spec or not spec.target_policy.get("revalidate", True) or not spec.selector: return True
        legal = self.legal_targets(link.source, link.actor, spec.selector)
        targets = link.target if isinstance(link.target, list) else [link.target] if link.target is not None else []
        return all(item in legal for item in targets)

    def resolve_chain(self):
        if not self.chain_window: return False, "No chain is open."
        chain = self.chain_window
        links = list(reversed(self.chain_links))
        for link in links:
            if link.negated:
                link.status = "negated"
                continue
            if not self.chain_link_targets_legal(link):
                link.status = "fizzled"
                self.chain_history.append({"event": "link_fizzled", "chain_id": chain["chain_id"], "link_id": link.link_id, "index": link.index, "status": link.status, "targets": link.context.get("target_snapshot", [])})
                continue
            spec_card = link.source
            previous_link_id = self.active_chain_link_id
            self.active_chain_link_id = link.link_id
            self.resolve(spec_card, link.trigger, link.target, link.actor, link.context, link.effect_id)
            self.active_chain_link_id = previous_link_id
            link.status = "resolved"
            self.chain_history.append({"event": "link_resolved", "chain_id": chain["chain_id"], "link_id": link.link_id, "index": link.index, "status": link.status, "targets": link.context.get("target_snapshot", [])})
        for notification in self.notifications:
            if notification.kind == "chain_response" and notification.status == "pending": notification.status, notification.answer = "resolved", "resolved"
        self.chain_history.append({"event": "chain_resolved", "chain_id": chain["chain_id"], "links": [{"id": item.link_id, "status": item.status, "negated": item.negated} for item in self.chain_links]})
        result = [(item.link_id, item.status) for item in self.chain_links]
        self.chain_links = []
        self.chain_window = None
        self.chain_priority = None
        self.chain_passes = []
        self.active_chain_link_id = ""
        return True, result

    def queue_effect(self, card, action, amount, actor, target=None, source="Effect", trigger=""):
        normalized = LogicRuntime.normalize_action(f"{action} {amount}")
        if not normalized["valid"]: return None
        self.effect_sequence += 1
        target_items = target if isinstance(target, list) else [target] if target is not None else []
        context = RuleContext(f"ctx_{self.effect_sequence + 1}", trigger, self.phase, self.turn, getattr(getattr(actor, "character", actor), "id", ""), getattr(getattr(card, "card", card), "id", ""), getattr(card, "last_zone", getattr(card, "position", "")), [getattr(getattr(item, "card", item), "id", getattr(item, "name", "")) for item in target_items], {"phase": self.phase, "turn": self.turn}, {"source": source})
        event = EffectEvent(self.effect_sequence, normalized["name"], normalized["amount"], actor, card, target, trigger, "queued", {}, context.source_zone, context.actor_id, {"source": source}, context.__dict__)

        self.effect_queue.append(event)
        return event

    def resolve_effect_queue(self):
        while self.effect_queue:
            event = self.effect_queue.pop(0)
            event.status = "resolving"
            event.result = self.apply_effect_now(event)
            event.status = event.result.get("status", "resolved")
            target_values = event.target if isinstance(event.target, list) else [event.target] if event.target is not None else []
            event.result.setdefault("legality", {"source_present": event.source in self.card_instances() if isinstance(event.source, CardInstance) else True, "target_ids": [self.entity_id(item) for item in target_values], "target_count": len(target_values), "status": event.status})
            self.resolution_history.append({"sequence": event.sequence, "action": event.action, "amount": event.amount, "source": getattr(getattr(event.source, "card", event.source), "name", str(event.source)), "source_zone": event.source_zone, "source_actor": event.source_actor, "trigger": event.trigger, "policy": event.policy, "status": event.status, "legality": event.result.get("legality", {}), "result": event.result})
            self.record_observation("resolution", {"effect_sequence": event.sequence, "action": event.action, "amount": event.result.get("amount", event.amount), "requested_amount": event.result.get("requested_amount", event.amount), "source_card_id": getattr(getattr(event.source, "card", event.source), "id", ""), "actor_id": event.source_actor, "target_ids": [self.entity_id(item) for item in target_values], "status": event.status, "result": event.result})
        self.resolution_history = self.resolution_history[-64:]
        self.check_end()

    def apply_effect_now(self, event):
        card, action, amount, actor, target = event.source, event.action, event.amount, event.actor, event.target
        source = getattr(getattr(card, "card", card), "name", "Effect")
        result = {"status": "resolved", "action": action, "amount": amount}
        targets = target if isinstance(target, list) else [target] if target is not None else []
        if action == "damage":
            requested_amount = amount
            amount = self.replace_event_value("damage", amount, actor, targets)
            result["requested_amount"] = requested_amount
            result["amount"] = amount
            result["replacements"] = list(self.last_replacement_records)
            recipients = [item for item in targets if hasattr(item, "hp")] or [self.other(actor)]
            values = []
            for recipient in recipients:
                before = recipient.hp
                recipient.hp = max(0, recipient.hp - amount)
                values.append(before - recipient.hp)
            result["value"] = values[0] if len(values) == 1 else values
            for recipient, value in zip(recipients, values): self.emit_event("damage", actor, source=card, target=recipient, metadata={"amount": value, "requested": amount})
            self.log(f"{source} deals {amount} damage to {len(recipients)} target(s).")
        elif action == "heal":
            recipients = [item for item in targets if hasattr(item, "hp")] or [actor]
            values = []
            for recipient in recipients:
                before = recipient.hp
                recipient.hp = min(8000, recipient.hp + amount)
                values.append(recipient.hp - before)
            result["value"] = values[0] if len(values) == 1 else values
            for recipient, value in zip(recipients, values): self.emit_event("heal", actor, source=card, target=recipient, metadata={"amount": value, "requested": amount})
            self.log(f"{source} restores {amount} health to {len(recipients)} target(s).")
        elif action == "draw":
            recipients = [item for item in targets if isinstance(item, Duelist)] or [actor]
            values = []
            for recipient in recipients:
                drawn = recipient.draw(max(1, amount))
                values.append(len(drawn))
                self.emit_event("draw", recipient, source=card, target=recipient, metadata={"count": len(drawn), "card_ids": [item.card.id for item in drawn]})
            result["value"] = values[0] if len(values) == 1 else values
            self.log(f"{source} lets {len(recipients)} duelist(s) draw {sum(values)} card(s).")
        elif action in ["set_face_up", "set_face_down", "switch_position"]:
            selected_cards = [item for item in targets if isinstance(item, CardInstance)] or [card]
            values = []
            for selected_card in selected_cards:
                if action == "set_face_up": selected_card.face_up = True
                elif action == "set_face_down": selected_card.face_up = False
                elif selected_card.face_up: selected_card.battle_position = "defense" if selected_card.battle_position == "attack" else "attack"
                values.append({"id": selected_card.card.id, "face_up": selected_card.face_up, "position": selected_card.battle_position})
                self.emit_event(action, actor, source=card, target=selected_card, metadata={"face_up": selected_card.face_up, "position": selected_card.battle_position})
            result["value"] = values
            self.log(f"{source} changes state of {len(selected_cards)} card(s).")
        elif action in ["boost_attack", "boost_defense"]:
            selected_cards = [item for item in targets if isinstance(item, CardInstance)] or [card]
            values = []
            for selected_card in selected_cards:
                if action == "boost_attack": selected_card.attack_bonus += amount; values.append(selected_card.attack_bonus)
                else: selected_card.defense_bonus += amount; values.append(selected_card.defense_bonus)
            result["value"] = values[0] if len(values) == 1 else values
            result["target_ids"] = [item.card.id for item in selected_cards]
            label = "ATK" if action == "boost_attack" else "DEF"
            self.log(f"{source} modifies {len(selected_cards)} card(s) by {amount} {label}.")
        elif action == "destroy":
            selected_cards = [item for item in targets if isinstance(item, CardInstance)] or [card]
            moved = [item.card.id for item in selected_cards if self.move_card(item, "graveyard")]
            result["value"] = moved
            result["status"] = "resolved" if moved else "blocked"
            if moved: self.log(f"{source} destroys {len(moved)} card(s).")
        elif action == "control":
            selected_cards = [item for item in targets if isinstance(item, CardInstance)] or [card]
            moved = []
            for selected_card in selected_cards:
                current_owner = self.owner_of(selected_card)
                if not current_owner or selected_card.position not in ["field", "monster"]: continue
                empty_zone = next((index for index, item in enumerate(actor.monsters) if item is None), None)
                if empty_zone is None: continue
                previous_zone = selected_card.position
                if selected_card in current_owner.monsters: current_owner.monsters[current_owner.monsters.index(selected_card)] = None
                elif selected_card in current_owner.spells: current_owner.spells[current_owner.spells.index(selected_card)] = None
                actor.monsters[empty_zone] = selected_card
                selected_card.last_zone = previous_zone
                selected_card.owner = actor.name
                selected_card.position = "field"
                selected_card.face_up = True
                moved.append(selected_card.card.id)
                self.emit_event("control", actor, source=card, target=selected_card, metadata={"controller": actor.character.id, "card_id": selected_card.card.id})
            result["value"] = moved
            result["status"] = "resolved" if moved else "blocked"
            if moved: self.log(f"{source} takes control of {len(moved)} card(s).")
        elif action == "shuffle":
            owners = [item for item in targets if isinstance(item, Duelist)]
            owners = owners or [actor]
            for owner in owners: random.shuffle(owner.deck)
            result["value"] = [owner.name for owner in owners]
            self.log(f"{source} shuffles {len(owners)} deck(s).")
        elif action in ["banish", "send_to_graveyard", "return_to_hand"]:
            selected_cards = [item for item in targets if isinstance(item, CardInstance)] or [card]
            destination = "banished" if action == "banish" else "graveyard" if action == "send_to_graveyard" else "hand"
            moved = [item.card.id for item in selected_cards if self.move_card(item, destination)]
            result["value"] = moved[0] if len(moved) == 1 else moved
            result["from_zone"] = getattr(card, "last_zone", "")
            result["to_zone"] = destination
            result["status"] = "resolved" if moved else "blocked"
            if moved: self.log(f"{source} moves {len(moved)} card(s) to {destination}.")
        else: result["status"] = "blocked"
        return result

    def apply_effect(self, card, action, amount, actor, target=None, source="Effect", trigger=""):
        event = self.queue_effect(card, action, amount, actor, target, source, trigger)
        if event is None: return {"status": "blocked", "action": action, "amount": amount}
        self.resolve_effect_queue()
        return event.result

    def run_logic(self, card, trigger, actor, target):
        context = {"card": card, "actor": actor, "target": target}
        for outcome in self.logic_runtime.run(trigger, context):
            self.apply_effect(card, outcome["action"], outcome["amount"], actor, target, f"Logic [{outcome['graph']}]")

    def condition_matches(self, conditions, card, actor, target):
        context = {"card": card, "actor": actor, "target": target, "engine": self}
        def evaluate(condition):
            if isinstance(condition, str): return self.logic_runtime.condition(condition, context)
            if not isinstance(condition, dict): return False
            if "all" in condition: return all(evaluate(item) for item in condition.get("all", []))
            if "any" in condition: return any(evaluate(item) for item in condition.get("any", []))
            if "not" in condition: return not evaluate(condition.get("not"))
            subject = condition.get("subject", "source")
            entity = {"source": card, "card": card, "actor": actor, "target": target, "event": self.active_rule_context}.get(subject, card)
            field_name = condition.get("field", "")
            if field_name.startswith("card."): entity, field_name = card, field_name.split(".", 1)[1]
            if field_name.startswith("actor."): entity, field_name = actor, field_name.split(".", 1)[1]
            if field_name.startswith("target."): entity, field_name = target, field_name.split(".", 1)[1]
            if field_name.startswith("event.") and self.active_rule_context: entity, field_name = self.active_rule_context, field_name.split(".", 1)[1]
            if field_name in ["summon_method", "summon_source_zone", "summon_source_card_id", "summon_source_card_name", "summon_source_effect_id"]: actual = getattr(card, field_name, "")
            else: actual = getattr(getattr(entity, "card", entity), field_name, getattr(entity, field_name, None))
            operator, expected = str(condition.get("operator", "equals")).lower(), condition.get("value")
            if operator in ["truthy", "exists"]: return bool(actual)
            if operator in ["falsy", "missing"]: return not bool(actual)
            if operator in ["in", "not_in"]:
                values = expected if isinstance(expected, list) else [expected]
                matches = actual in values or str(actual).lower() in [str(item).lower() for item in values]
                return not matches if operator == "not_in" else matches
            if isinstance(actual, (int, float)): return SelectorRuntime.compare(actual, operator, expected)
            if operator in ["equals", "=="]: return str(actual).lower() == str(expected).lower()
            if operator in ["not_equals", "!="]: return str(actual).lower() != str(expected).lower()
            if operator == "contains": return str(expected).lower() in str(actual).lower()
            return False
        values = conditions if isinstance(conditions, list) else [conditions]
        return all(evaluate(condition) for condition in values if condition is not None)

    def legacy_selector(self, card, actor):
        types = set(card.card.targets or [])
        if not types or types == {"none"}: return {}
        selector = {"count": max(1, int(card.card.target_count or 1))}
        if "opponent" in types: selector.update({"side": "opponent", "zone": "any", "include_duelist": True})
        elif "player" in types or "self" in types: selector.update({"side": "self", "zone": "any", "include_duelist": True})
        elif "opponent_monster" in types: selector.update({"side": "opponent", "zone": "monster"})
        elif "player_monster" in types: selector.update({"side": "self", "zone": "monster"})
        elif "monster" in types or "any_monster" in types: selector.update({"side": "both", "zone": "monster"})
        elif "opponent_spell_trap" in types: selector.update({"side": "opponent", "zone": "spell_trap"})
        elif "player_spell_trap" in types: selector.update({"side": "self", "zone": "spell_trap"})
        else: selector.update({"side": "both", "zone": "any"})
        return selector

    def cost_candidates(self, cost, card, actor):
        selector = cost.get("select") or cost.get("selector") or {}
        if not selector:
            selector = {"side": "self", "zone": "hand", "count": cost.get("count", 1)}
        selector = dict(selector)
        selector["count"] = "all"
        return [item for item in SelectorRuntime(self, actor, card).select(selector) if item is not card]

    def preflight_costs(self, spec, card, actor, start_index=0):
        hp_remaining = int(actor.hp)
        for index in range(start_index, len(spec.costs)):
            cost = spec.costs[index]
            kind = cost.get("kind", cost.get("action", ""))
            if kind in ["discard", "tribute", "send_to_graveyard"]:
                candidates = self.cost_candidates(cost, card, actor)
                required = max(1, int(cost.get("count", (cost.get("select") or {}).get("count", 1)) or 1))
                if len(candidates) < required: return False, {"status": "blocked", "reason": "insufficient_cost_candidates", "kind": kind, "index": index}
            elif kind == "pay_hp":
                amount = max(0, int(cost.get("amount", 0) or 0))
                hp_remaining -= amount
                if hp_remaining < 0: return False, {"status": "blocked", "reason": "insufficient_hp", "index": index}
            else:
                return False, {"status": "blocked", "reason": "unsupported_cost", "kind": kind, "index": index}
        return True, {"status": "valid"}

    def pay_costs(self, spec, card, actor, start_index=0, continuation_kind=""):
        for index in range(start_index, len(spec.costs)):
            cost = spec.costs[index]
            kind = cost.get("kind", cost.get("action", ""))
            if kind in ["discard", "tribute", "send_to_graveyard"]:
                candidates = self.cost_candidates(cost, card, actor)
                required = max(1, int(cost.get("count", (cost.get("select") or {}).get("count", 1)) or 1))
                if len(candidates) < required: return False, {"status": "blocked", "reason": "insufficient_cost_candidates", "kind": kind}
                if kind == "discard":
                    pending_kind = continuation_kind or kind
                    self.pending_cost = {"kind": pending_kind, "card": card, "spec": spec, "actor": actor, "candidates": candidates, "required": required, "selected": [], "cost_index": index, "cost_kind": kind}
                    self.notify("choose_cards", cost.get("notify", {}).get("text", "Choose cards to discard."), ["ok"], {"required": required, "kind": pending_kind, "cost_kind": kind})
                    return False, {"status": "pending", "kind": kind, "required": required}
                for item in candidates[:required]: self.move_card(item, "graveyard", actor)
            elif kind == "pay_hp":
                amount = int(cost.get("amount", 0))
                if actor.hp < amount: return False, {"status": "blocked", "reason": "insufficient_hp"}
                actor.hp -= amount
            else:
                return False, {"status": "blocked", "reason": "unsupported_cost", "kind": kind}
        return True, {"status": "paid"}

    def resolve_pending_cost(self, cards):
        pending = self.pending_cost
        if not pending or pending["kind"] not in ["discard", "discard_action", "response_cost", "procedure_cost"]: return False, "No card cost is pending."
        selected = list(cards if isinstance(cards, list) else [cards])
        if len(selected) != pending["required"] or any(item not in pending["candidates"] for item in selected): return False, "Those cards cannot pay this cost."
        if len(set(selected)) != len(selected): return False, "A card cannot be selected twice."
        for item in selected: self.move_card(item, "graveyard", pending["actor"])
        card, spec, actor = pending["card"], pending["spec"], pending["actor"]
        pending_kind = pending["kind"]
        self.pending_cost = None
        notification = self.pending_notification("choose_cards")
        if notification: notification.status, notification.answer = "resolved", "ok"
        if pending_kind == "response_cost":
            owner = self.owner_of(card) or actor
            owner.remove(card)
            card.face_up = True
            card.position = "graveyard"
            owner.graveyard.append(card)
            target = pending.get("response_target") or self.other(actor)
            return self.add_chain_link(card, spec, actor, target, spec.trigger, {"response": True, "cost_paid": True, "target_snapshot": [self.entity_id(item) for item in (target if isinstance(target, list) else [target] if target is not None else [])]})
        if pending_kind == "procedure_cost":
            next_index = int(pending.get("cost_index", 0)) + 1
            valid, result = self.preflight_costs(spec, card, actor, next_index)
            if not valid:
                self.pending_procedure = None
                return False, result.get("reason", "The summon procedure cost cannot be paid.")
            paid, result = self.pay_costs(spec, card, actor, next_index, "procedure_cost")
            if not paid:
                if result.get("status") == "pending":
                    notification = self.pending_notification("choose_cards")
                    if notification: notification.payload.update({"kind": "procedure_cost", "card": card.card.id})
                    return True, "pending_cost"
                self.pending_procedure = None
                return False, result.get("reason", "The summon procedure cost could not be paid.")
            if self.pending_procedure: self.pending_procedure["costs_paid"] = True
            return self.prompt_summon_procedure()
        completed = self.execute_effect_spec(card, spec, actor, self.other(actor), pending.get("action_index", 0) + 1) if pending_kind == "discard_action" else self.execute_effect_spec(card, spec, actor, self.other(actor))
        if completed: self.mark_effect_used(card, spec)
        return True, ""

    def execute_effect_spec(self, card, spec, actor, default_target, start_index=0):
        selector = spec.selector or self.legacy_selector(card, actor)
        if selector:
            if isinstance(default_target, list): selected = list(default_target)
            elif isinstance(default_target, CardInstance): selected = [default_target]
            else: selected = SelectorRuntime(self, actor, card).select(selector)
        elif spec.targets:
            selected = []
            for target_group in spec.targets:
                if isinstance(target_group, dict): selector = target_group.get("selector", {})
                elif str(target_group) in ["opponent", "player", "self"]: selector = {"side": "opponent" if str(target_group) == "opponent" else "self", "zone": "any", "include_duelist": True, "count": 1}
                else: selector = {"side": "both", "zone": str(target_group), "count": 1}
                selected.extend(SelectorRuntime(self, actor, card).select(selector))
        else:
            selected = []
        target_map = {"target": selected, "selected": selected}
        for index in range(start_index, len(spec.actions)):
            action = spec.actions[index]
            action_name = action.get("name", "")
            if not action.get("valid", action_name in EffectSpec.action_names): continue
            target_value = action.get("target", "")
            if isinstance(target_value, dict): resolved = SelectorRuntime(self, actor, card).select(target_value)
            elif target_value in target_map: resolved = target_map[target_value]
            elif target_value in ["actor", "self"]: resolved = actor
            elif target_value in ["opponent", "enemy"]: resolved = default_target
            elif target_value in ["source", "card"] or not target_value: resolved = card if action_name in ["boost_attack", "boost_defense"] else default_target
            else: resolved = selected
            if action_name == "discard":
                discard_selector = dict(action.get("select") or action.get("selector") or {"side": "self", "zone": "hand", "count": action.get("count", 1)})
                discard_selector["count"] = "all"
                candidates = SelectorRuntime(self, actor, card).select(discard_selector)
                required = max(1, int(action.get("count", (action.get("select") or {}).get("count", 1)) or 1))
                if len(candidates) < required: return False
                self.pending_cost = {"kind": "discard_action", "card": card, "spec": spec, "actor": actor, "candidates": candidates, "required": required, "selected": [], "action_index": index}
                self.notify("choose_cards", action.get("notify", {}).get("text", "Choose cards to discard."), ["ok"], {"required": required, "kind": "discard_action", "effect": spec.effect_id})
                return False
            if action_name == "grant_normal_summon":
                amount = action.get("count", action.get("amount", 1))
                if isinstance(amount, dict): amount = amount.get("value", 1)
                cost = action.get("cost") or ({"kind": "pay_hp", "amount": action.get("cost_amount", 0)} if action.get("cost_amount") is not None else {})
                self.grant_normal_summon(actor, amount, cost, bool(action.get("per_turn", False)), card.card.id)
                continue
            if action_name == "negate_chain":
                link = self.negation_link_candidate(action)
                if not link: return False
                negated, _ = self.negate_chain_link(link.link_id, self.active_chain_link_id, spec.effect_id)
                if not negated: return False
                continue
            if action_name in ["summon", "special_summon"]:
                summon_selector = action.get("select") or (target_value if isinstance(target_value, dict) else spec.selector)
                summon_method = str(action.get("method", "special" if action_name == "special_summon" else "special")).lower()
                summon_count = action.get("count", len(resolved) if isinstance(resolved, list) else 1)
                candidate_selector = dict(summon_selector or {})
                candidate_selector["count"] = "all"
                summon_source = SelectorRuntime(self, actor, card).select(candidate_selector)
                if summon_source:
                    if summon_method in ["fusion", "ritual", "normal"]:
                        for summon_card in summon_source[:int(summon_count or 1)]:
                            if summon_method in ["fusion", "ritual"]: summon_result = self.begin_summon_procedure(summon_card, actor, ProcedureSpec.from_card(summon_card))
                            else: summon_result = self.summon(summon_card, actor)
                            if not summon_result[0] or summon_result[1] in ["pending_procedure", "pending_cost"]: return False
                    else:
                        summon_result = self.special_summon({"side": "both", "zone": "any", "card_id": [item.card.id for item in summon_source], "count": summon_count}, actor, summon_method, card, spec.effect_id, summon_count)
                        if summon_result[1] == "pending": return False
                continue
            amount = action.get("amount", 0)
            if isinstance(amount, dict): amount = amount.get("value", 0)
            self.apply_effect(card, action_name, int(amount or 0), actor, resolved, card.card.name, spec.trigger)
        if spec.media: self.reaction_events.append({"event": spec.media.get("cue", spec.effect_id), "actor": actor.character.id, "target": default_target.character.id, "selection": spec.media, "time": time.time()})
        return True

    def answer_pending_effect(self, answer):
        pending = self.pending_effect
        notification = self.pending_notification("yes_no")
        if not pending or not notification or answer not in notification.options: return False, "No optional effect decision is pending."
        notification.status, notification.answer = "resolved", answer
        self.pending_effect = None
        if answer == "no": return True, ""
        paid, result = self.pay_costs(pending["spec"], pending["card"], pending["actor"])
        if not paid: return False, result.get("reason", "The effect cost could not be paid.")
        completed = self.execute_effect_spec(pending["card"], pending["spec"], pending["actor"], pending["target"])
        if completed: self.mark_effect_used(pending["card"], pending["spec"])
        return True, ""

    def normalize_trigger_order_policy(self, trigger):
        raw = dict(getattr(self.place, "trigger_order_policies", {}).get(trigger, {}) or {})
        chooser = str(raw.get("chooser", "actor")).lower()
        if chooser not in ["actor", "player", "opponent"]: chooser = "actor"
        optional_mode = raw.get("optional_effects", raw.get("optional", "all"))
        if isinstance(optional_mode, bool): optional_mode = "prompt" if optional_mode else "all"
        optional_mode = str(optional_mode).lower()
        if optional_mode not in ["all", "prompt", "none"]: optional_mode = "all"
        return {"enabled": bool(raw.get("enabled", False)), "chooser": chooser, "mandatory": bool(raw.get("mandatory", True)), "fallback": str(raw.get("fallback", "deterministic")).lower(), "optional_effects": optional_mode}

    def dispatch_trigger_group(self, group, ordered, trigger, actor, target, context):
        previous_context = self.active_rule_context
        self.active_rule_context = context
        self.event_dispatch_stack.append(trigger)
        for _, _, effect_id, source_card, spec in ordered:
            self.resolve(source_card, trigger, target, actor, context, effect_id)
            group["resolved"].append(effect_id)
        self.event_dispatch_stack.pop()
        self.active_rule_context = previous_context
        group["status"] = "resolved"
        context.metadata["trigger_group_resolved"] = list(group["resolved"])
        context.metadata["trigger_group_selected_order"] = list(group.get("selected_order", group["resolved"]))
        context.metadata["trigger_group_included_ids"] = list(group.get("included_ids", group["resolved"]))
        self.record_observation("trigger_group_resolved", {"group_id": group.get("group_id", ""), "trigger": trigger, "selected_order": list(group.get("selected_order", group["resolved"])), "included_ids": list(group.get("included_ids", group["resolved"])), "resolved": list(group["resolved"])})

    def resolve_trigger_order(self, selection):
        pending = self.pending_trigger_order
        if not pending: return False, "No trigger order is pending."
        selected = selection if isinstance(selection, list) else [selection]
        selected_ids = [item if isinstance(item, str) else getattr(getattr(item, "card", item), "id", "") for item in selected]
        required_ids = list(pending.get("required_ids", [item["effect_id"] for item in pending["members"] if not item.get("optional")]))
        allowed_ids = set(required_ids) | set(pending.get("optional_ids", [item["effect_id"] for item in pending["members"] if item.get("optional")]))
        if len(selected_ids) != len(set(selected_ids)) or not set(required_ids).issubset(set(selected_ids)) or not set(selected_ids).issubset(allowed_ids): return False, "Choose every required effect and only legal optional effects."
        ordered_by_id = {item[2]: item for item in pending["ordered"]}
        ordered = [ordered_by_id[item] for item in selected_ids]
        group = pending["group"]
        group["selected_order"] = list(selected_ids)
        group["included_ids"] = list(selected_ids)
        group["excluded_ids"] = [item["effect_id"] for item in pending["members"] if item["effect_id"] not in set(selected_ids)]
        group["order_mode"] = "prompt"
        self.pending_trigger_order = None
        notification = self.pending_notification("choose_trigger_order")
        if notification: notification.status, notification.answer = "resolved", "ok"
        self.dispatch_trigger_group(group, ordered, pending["trigger"], pending["actor"], pending["target"], pending["context"])
        self.active_rule_context = pending["previous_context"]
        return True, ""

    def ai_trigger_effect_score(self, item, actor):
        return self.declarative_effect_score(item[3], item[4], actor, self.other(actor))

    def ai_resolve_pending_trigger_order(self):
        pending = self.pending_trigger_order
        if not pending or pending["chooser"] is not self.opponent: return False
        required = [item for item in pending["members"] if not item.get("optional")]
        optional = [item for item in pending["members"] if item.get("optional")]
        chosen_optional = [item for item in optional if self.ai_trigger_effect_score(item, self.opponent) > 0]
        selected = required + chosen_optional
        selected.sort(key=lambda item: (-self.ai_trigger_effect_score(item, self.opponent), item[2]))
        return self.resolve_trigger_order([item[2] for item in selected])

    def emit_event(self, trigger, actor, source=None, target=None, metadata=None, include_source=True):
        self.rule_event_sequence += 1
        event_metadata = dict(metadata or {})
        policy = self.normalize_event_window(trigger, actor, source, target, event_metadata)
        if policy.get("enabled", False):
            event_metadata.update({"response_window": True, "response_policy": policy, "event_window": {"event": trigger, "phase": self.phase, "turn": self.turn, "priority": policy.get("priority", "opposite")}})
        source_cards = [source] if include_source and isinstance(source, CardInstance) else []
        if not source_cards:
            source_cards = [item for side in [self.player, self.opponent] for item in side.monsters + side.spells if item and item.face_up]
            if self.field_card and self.field_card.face_up: source_cards.append(self.field_card)
            if not include_source and isinstance(source, CardInstance): source_cards = [item for item in source_cards if item is not source]
        source_cards = list(dict.fromkeys(source_cards))
        target_items = target if isinstance(target, list) else [target] if target is not None else []
        context = RuleContext(f"rule_{self.rule_event_sequence}", trigger, self.phase, self.turn, getattr(getattr(actor, "character", actor), "id", ""), getattr(getattr(source, "card", source), "id", ""), getattr(source, "last_zone", getattr(source, "position", "")), [getattr(getattr(item, "card", item), "id", getattr(item, "name", "")) for item in target_items], {"phase": self.phase, "turn": self.turn}, event_metadata)
        self.record_observation("event", {"context_id": context.context_id, "trigger": trigger, "actor_id": context.actor_id, "source_card_id": context.source_card_id, "target_ids": list(context.target_ids), "metadata": event_metadata})
        if trigger in self.event_dispatch_stack:
            self.event_history.append(context.__dict__.copy())
            self.event_history = self.event_history[-128:]
            return context
        ordered = []
        for source_card in source_cards:
            for index, raw_effect in enumerate(source_card.card.effects):
                spec = EffectSpec.from_dict(raw_effect, source_card.card.id + "_effect_" + str(index))
                if spec.trigger == trigger and not spec.validate(): ordered.append((spec.priority, source_card.card.id, spec.effect_id, source_card, spec))
        ordered.sort(key=lambda item: (item[0], item[1], item[2]))
        order_policy = self.normalize_trigger_order_policy(trigger)
        included_ordered = [item for item in ordered if not (order_policy["optional_effects"] == "none" and item[4].optional)]
        self.trigger_group_sequence += 1
        group_id = "trigger_group_" + str(self.trigger_group_sequence)
        members = [{"index": index, "priority": item[0], "source_card_id": item[1], "effect_id": item[2], "optional": bool(item[4].optional), "ordering_key": [item[0], item[1], item[2]]} for index, item in enumerate(ordered)]
        context.metadata.update({"trigger_group_id": group_id, "trigger_group_size": len(members), "trigger_group_order": [item["effect_id"] for item in members]})
        self.event_history.append(context.__dict__.copy())
        self.event_history = self.event_history[-128:]
        group = {"group_id": group_id, "context_id": context.context_id, "trigger": trigger, "phase": self.phase, "turn": self.turn, "members": members, "resolved": [], "status": "pending" if len(members) > 1 else "ready"}
        self.trigger_groups.append(group)
        self.trigger_groups = self.trigger_groups[-64:]
        required_members = [item for item in members if not item["optional"]]
        optional_members = [item for item in members if item["optional"]]
        needs_optional_prompt = order_policy["optional_effects"] == "prompt" and bool(optional_members)
        needs_order_prompt = len(included_ordered) > 1 and order_policy["enabled"]
        if needs_order_prompt or needs_optional_prompt:
            chooser = actor if order_policy["chooser"] == "actor" else self.player if order_policy["chooser"] == "player" else self.opponent
            group["order_mode"] = "prompt"
            group["chooser"] = self.side_key(chooser)
            group["required_ids"] = [item["effect_id"] for item in required_members]
            group["optional_ids"] = [item["effect_id"] for item in optional_members]
            pending_members = members if order_policy["optional_effects"] != "none" else [item for item in members if not item["optional"]]
            pending_ordered = ordered if order_policy["optional_effects"] != "none" else included_ordered
            pending_optional_ids = [item["effect_id"] for item in optional_members] if order_policy["optional_effects"] == "prompt" else []
            self.pending_trigger_order = {"group": group, "members": pending_members, "ordered": pending_ordered, "trigger": trigger, "actor": actor, "target": target, "context": context, "previous_context": self.active_rule_context, "chooser": chooser, "required_ids": [item["effect_id"] for item in required_members], "optional_ids": pending_optional_ids}
            self.notify("choose_trigger_order", "Choose the order of simultaneous effects.", ["ok"], {"kind": "trigger_order", "group_id": group_id, "trigger": trigger, "members": members, "selected_ids": [], "required_ids": self.pending_trigger_order["required_ids"], "optional_ids": self.pending_trigger_order["optional_ids"], "required_count": len(required_members), "chooser": self.side_key(chooser), "mandatory": order_policy["mandatory"], "optional_effects": order_policy["optional_effects"], "fallback": order_policy["fallback"]})
        else:
            group["order_mode"] = "deterministic"
            included_ids = {value[2] for value in included_ordered}
            group["excluded_ids"] = [item["effect_id"] for item in members if item["effect_id"] not in included_ids]
            self.dispatch_trigger_group(group, included_ordered, trigger, actor, target, context)
        if event_metadata.get("response_window") and not self.chain_window: self.open_event_response_window(trigger, actor, source, target, event_metadata)
        return context

    def resolve(self, card, trigger, target=None, actor=None, context=None, effect_id=""):
        actor = actor or (self.player if card in self.player.hand or card in self.player.monsters or card in self.player.spells else self.opponent)
        target = target if target is not None else self.other(actor)
        previous_context = self.active_rule_context
        self.active_rule_context = context or previous_context
        for index, raw_effect in enumerate(card.card.effects):
            spec = EffectSpec.from_dict(raw_effect, card.card.id + "_effect_" + str(index))
            if effect_id and spec.effect_id != effect_id: continue
            if spec.trigger != trigger: continue
            phase_value = spec.window.get("phase", "any")
            phase_values = phase_value if isinstance(phase_value, list) else [phase_value]
            normalized_phase = self.phase.lower().replace(" 1", "").replace(" 2", "")
            if not any(str(value).lower() in ["any", normalized_phase, self.phase.lower()] for value in phase_values): continue
            event_value = spec.window.get("event", trigger)
            event_values = event_value if isinstance(event_value, list) else [event_value]
            if not any(value in [None, "", trigger, self.phase.lower(), self.phase.lower().replace(" ", "_")] for value in event_values): continue
            if spec.validate():
                self.log("Unsupported effect " + spec.effect_id + ": " + ", ".join(spec.validate()))
                continue
            if self.effect_used(card, spec):
                self.log("Effect " + spec.effect_id + " has already resolved for its current policy.")
                continue
            if not self.condition_matches(spec.conditions, card, actor, target): continue
            if spec.notify:
                kind = spec.notify.get("kind", spec.notify.get("type", "info"))
                options = spec.notify.get("options", ["yes", "no"] if kind == "yes_no" else ["ok"])
                if kind == "yes_no":
                    self.pending_effect = {"card": card, "spec": spec, "actor": actor, "target": target}
                    self.notify(kind, spec.notify.get("text", "Activate this effect?"), options, {"effect": spec.effect_id})
                    continue
            cost_paid = context.get("cost_paid", False) if isinstance(context, dict) else False
            if not cost_paid:
                paid, result = self.pay_costs(spec, card, actor)
                if not paid: continue
            self.register_continuous_effect(card, spec, actor)
            if self.execute_effect_spec(card, spec, actor, target): self.mark_effect_used(card, spec)
        self.active_rule_context = previous_context

    def battle_value(self, card, side):
        return self.effective_atk(card, side) if card.battle_position == "attack" else self.effective_defense(card, side)

    def resolve_battle(self, attacker_side, attacker, target=None):
        defender_side = self.other(attacker_side)
        targets = [item for item in defender_side.monsters if item]
        if target is not None and target not in targets: return False, "That target is not on the opponent field."
        target = target or (min(targets, key=lambda item: (self.battle_value(item, defender_side), item.card.id)) if targets else None)
        attacker.attacked = True
        self.emit_event("attack", attacker_side, source=attacker, target=target, metadata={"attacker": attacker.card.id, "target": self.entity_id(target) if target else "", "direct": not bool(targets)})
        self.emit_event("attacked", defender_side, source=None, target=target or defender_side, metadata={"attacker": attacker.card.id, "target": self.entity_id(target) if target else defender_side.character.id, "direct": not bool(targets)})
        if not target:
            damage = self.effective_atk(attacker, attacker_side)
            defender_side.hp = max(0, defender_side.hp - damage)
            self.emit_event("damage", attacker_side, source=attacker, target=defender_side, metadata={"amount": damage, "source": "battle", "direct": True})
            self.log(f"{attacker.card.name} attacks directly for {damage}.")
            self.react("attack", attacker_side.character.id, defender_side.character.id, "opponent")
            self.check_end()
            return True, ""
        if not target.face_up:
            target.face_up = True
            self.log(f"{target.card.name} flips face-up.")
            self.emit_event("flip", defender_side, source=target, target=target, metadata={"position": target.battle_position})
            self.react("flip", defender_side.character.id, attacker_side.character.id, "opponent", "cards", target.card.id)
            self.resolve(target, "flip", actor=defender_side, target=attacker)
            self.run_logic(target, "flip", defender_side, attacker_side)
        attack_value = self.effective_atk(attacker, attacker_side)
        target_in_attack = target.battle_position == "attack"
        target_value = self.battle_value(target, defender_side)
        if attack_value > target_value:
            self.destroy(defender_side, target)
            damage = attack_value - target_value if target_in_attack else 0
            if damage:
                defender_side.hp = max(0, defender_side.hp - damage)
                self.emit_event("damage", attacker_side, source=attacker, target=defender_side, metadata={"amount": damage, "source": "battle", "direct": False, "defeated": target.card.id})
            self.log(f"{attacker.card.name} defeats {target.card.name}" + (f" for {damage} damage." if damage else "."))
            self.react("damage", attacker_side.character.id, defender_side.character.id, "opponent")
        elif attack_value < target_value:
            damage = target_value - attack_value
            self.destroy(attacker_side, attacker)
            attacker_side.hp = max(0, attacker_side.hp - damage)
            self.emit_event("damage", defender_side, source=target, target=attacker_side, metadata={"amount": damage, "source": "battle", "direct": False, "attacker": attacker.card.id})
            self.log(f"{attacker.card.name} loses the battle and {attacker_side.name} takes {damage} damage.")
        elif target_in_attack:
            self.destroy(attacker_side, attacker)
            self.destroy(defender_side, target)
            self.log("Both monsters are destroyed.")
        else:
            self.log(f"{attacker.card.name} is stopped by {target.card.name}.")
        self.check_end()
        return True, ""

    def attack(self, card, target=None):
        if self.finished or self.active is not self.player or self.phase != "BATTLE": return False, "Attacks are only available during Battle."
        if card not in self.player.monsters or card is None: return False, "Select a face-up monster."
        if card.attacked or not card.face_up or card.battle_position != "attack": return False, "That monster cannot attack now."
        return self.resolve_battle(self.player, card, target)

    def destroy(self, duelist, card):
        from_zone = card.position
        duelist.remove(card)
        card.position = "graveyard"
        duelist.graveyard.append(card)
        self.emit_event("destroy", duelist, source=card, target=card, metadata={"from_zone": from_zone, "to_zone": "graveyard", "owner": duelist.character.id})
        self.emit_event("movement", duelist, source=card, target=card, metadata={"from_zone": from_zone, "to_zone": "graveyard", "owner": duelist.character.id})

    def check_end(self):
        if self.player.hp <= 0 and self.opponent.hp <= 0: self.finish(None, "simultaneous zero HP")
        elif self.player.hp <= 0: self.finish(self.opponent, "health")
        elif self.opponent.hp <= 0: self.finish(self.player, "health")

    def finish(self, winner, reason):
        if self.finished: return
        self.finished = True
        self.winner = winner
        self.reason = reason
        if winner is None:
            self.react("draw_result", self.player.character.id, self.opponent.character.id, "opponent")
        else:
            self.react("win" if winner is self.player else "lose", winner.character.id, self.other(winner).character.id, "opponent")
        if not self.match_recorded:
            loser = self.other(winner) if winner else None
            self.transferred_card = self.store.record_duel(winner.character.id if winner else None, loser.character.id if loser else None, self.turn, reason)
            self.match_recorded = True
        self.log("The duel ends in a draw." if winner is None else f"{winner.name} wins by {reason}.")

    def resolve_ai(self, card, trigger, actor=None, target=None):
        actor = actor or self.opponent
        target = target or self.other(actor)
        self.resolve(card, trigger, actor, target)

    def ai_can_summon(self, card, actor):
        if not any(value is None for value in actor.monsters): return False
        if card.card.summon_method in ["fusion", "ritual"]:
            procedure = ProcedureSpec.from_card(card)
            if procedure.costs:
                cost_spec = EffectSpec.from_dict({"id": card.card.id + "_procedure_cost", "trigger": "summon", "cost": procedure.costs}, card.card.id + "_procedure_cost")
                if not self.preflight_costs(cost_spec, card, actor)[0]: return False
            selected = self.ai_procedure_selection(card, actor, procedure)
            return bool(selected) and self.validate_procedure_materials(card, selected, actor, procedure)[0]
        if self.normal_summon_remaining(actor) <= 0: return False
        if card.card.stars <= 4: return True
        procedure = ProcedureSpec.normal_tribute(card, self.store.rules)
        if procedure.special: return False
        candidates = self.procedure_material_candidates(card, actor, procedure)
        return len(candidates) >= procedure.required_count

    def ai_procedure_selection(self, card, actor, procedure):
        candidates = self.procedure_material_candidates(card, actor, procedure)
        ranked = sorted(candidates, key=lambda item: (self.ai_card_score(item, "monster"), item.card.id))
        if procedure.kind == "fusion" and procedure.exact:
            selected = []
            for required_id in procedure.required_card_ids:
                match = next((item for item in ranked if item.card.id == required_id and item not in selected), None)
                if not match: return []
                selected.append(match)
            return selected
        if procedure.kind == "ritual":
            selected, stars = [], 0
            for item in ranked:
                selected.append(item)
                stars += int(item.card.stars)
                if stars >= procedure.min_stars: break
            return selected if stars >= procedure.min_stars else []
        return ranked[:procedure.required_count]

    def ai_resolve_pending_procedure(self):
        pending = self.pending_procedure
        if not pending or pending["actor"] is not self.opponent: return False
        if self.pending_cost and self.pending_cost.get("kind") == "procedure_cost":
            selected = list(self.pending_cost["candidates"][:self.pending_cost["required"]])
            self.resolve_pending_cost(selected)
            return True
        procedure = pending["procedure"]
        selected = self.ai_procedure_selection(pending["card"], self.opponent, procedure)
        if not selected:
            self.abort_procedure("The AI could not find a legal procedure selection.")
            return True
        pending["selected"] = selected
        self.resolve_pending_procedure(selected)
        return True

    def ai_defense_estimate(self, card, actor=None):
        actor = actor or self.opponent
        if not card.face_up: return 0
        return self.effective_atk(card, actor) if card.battle_position == "attack" else self.effective_defense(card, actor)

    def ai_target_score(self, item, actor, spec=None):
        enemy = self.other(actor)
        if isinstance(item, Duelist): return max(0, 8000 - item.hp) if item is enemy else -max(0, 8000 - item.hp)
        if not isinstance(item, CardInstance): return 0
        owner = self.owner_of(item)
        score = self.effective_atk(item, owner) if item.battle_position == "attack" else self.effective_defense(item, owner)
        if owner is enemy: score += 900
        else: score = -score
        if not item.face_up: score += 120 if owner is enemy else -120
        if item.card.kind in ["spell", "field", "trap"]: score += 180 if owner is enemy else -180
        if spec and any(action.get("name") == "destroy" for action in spec.actions) and owner is enemy: score += 300
        return score

    def ai_card_score(self, card, mode, actor=None):
        actor = actor or self.opponent
        enemy = self.other(actor)
        character = actor.character
        weights = character.behavior_weights
        family_weights = weights.get("family_weights", {})
        phase_weights = weights.get("phase_weights", {})
        state = "enemy" if enemy.character.id in character.enemies else "ally" if enemy.character.id in character.allies else character.relationship if character.relationship in ["enemy", "ally"] else "stranger"
        state_weight = float(weights.get("state_weights", {}).get(state, 1.0))
        family_weight = float(family_weights.get(card.card.family, 0.0))
        learned_weight = int(character.learned_cards.get(card.card.id, 0)) * float(weights.get("adaptation", 1.0))
        phase_weight = float(phase_weights.get(self.phase, 1.0))
        urgency = float(weights.get("risk_tolerance", 3.0)) if mode in ["monster", "set"] else float(weights.get("reward_value", 5.0))
        hp_pressure = max(0, 8000 - actor.hp) / 800.0 if mode == "spell" else 0.0
        effect_score = 0
        for index, raw_effect in enumerate(card.card.effects):
            spec = EffectSpec.from_dict(raw_effect, card.card.id + "_effect_" + str(index))
            if not spec.validate():
                effect_score += self.declarative_effect_score(card, spec, actor, enemy)
                if spec.trigger == "flip" and mode == "set": effect_score += 500
                if spec.trigger == "battle" and mode == "set": effect_score += 700
        stat_score = card.atk + card.card.stars * 40
        if mode == "set": stat_score = card.defense * 1.25 + (card.atk * 0.15)
        if mode == "trap": stat_score = effect_score + 150
        bias_key = "summon_bias" if mode == "monster" else "set_bias" if mode == "set" else "activation_bias" if mode in ["spell", "trap"] else "summon_bias"
        bias = max(0.1, float(weights.get("duel", {}).get(bias_key, 1.0)))
        return (stat_score + family_weight * 100 * phase_weight * state_weight + learned_weight * 20 + urgency * 25 + hp_pressure * 200 + effect_score) * bias

    def ai_activation_spec(self, card):
        return next((EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index)) for index, raw in enumerate(card.card.effects) if EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index)).trigger == "activate"), None)

    def ai_activation_score(self, card, actor):
        spec = self.ai_activation_spec(card)
        if not spec: return self.ai_card_score(card, "spell", actor)
        score = self.ai_card_score(card, "spell", actor)
        selector = spec.selector or self.legacy_selector(card, actor)
        legal = self.legal_targets(card, actor, selector) if selector else []
        enemy = self.other(actor)
        own_value = sum(max(0, self.ai_target_score(item, enemy)) for item in legal if self.owner_of(item) is actor)
        enemy_value = sum(max(0, self.ai_target_score(item, actor)) for item in legal if self.owner_of(item) is enemy)
        for action in spec.actions:
            name = action.get("name", "")
            if name == "destroy":
                score += (enemy_value * 2 - own_value * 3) * float(actor.character.behavior_weights.get("duel", {}).get("removal_bias", 1.0))
                if enemy_value <= 0: score -= 100000
            elif name in ["banish", "send_to_graveyard", "return_to_hand", "control"]:
                score += enemy_value - own_value
            elif name == "draw":
                score += max(1, int(action.get("amount", 1) or 1)) * 140
        if selector and selector.get("zone") == "spell_trap" and not any(self.owner_of(item) is enemy for item in legal): score -= 100000
        return score * float(actor.character.behavior_weights.get("duel", {}).get("activation_bias", 1.0))

    def ai_can_activate(self, card, actor):
        if card not in actor.hand or card.card.kind not in ["spell", "field"] or card.card.timing not in ["main", "any"]: return False
        spec = self.ai_activation_spec(card)
        selector = spec.selector if spec and spec.selector else self.legacy_selector(card, actor)
        if selector:
            legal = self.legal_targets(card, actor, selector)
            if not legal: return False
            if selector.get("zone") in ["monster", "spell_trap", "field"] and not any(self.owner_of(item) is self.other(actor) for item in legal if isinstance(item, CardInstance)) and any(action.get("name") in ["destroy", "banish", "send_to_graveyard", "return_to_hand", "control"] for action in (spec.actions if spec else [])): return False
            required = selector.get("count", card.card.target_count or 0)
            if required == "all": return True
            try: required = int(required or 0)
            except (TypeError, ValueError): required = 0
            if required and len(legal) < required: return False
        return self.ai_activation_score(card, actor) > -50000

    def ai_main_plan(self, actor=None):
        actor = actor or self.opponent
        actions = []
        if any(value is None for value in actor.monsters):
            for card in actor.hand + actor.extra:
                if card.card.kind in ["normal", "effect", "legendary", "fusion", "ritual"] and self.ai_can_summon(card, actor):
                    actions.append({"kind": "summon", "card": card, "score": self.ai_card_score(card, "monster", actor) + 120})
        if self.normal_summon_remaining(actor) > 0 and any(value is None for value in actor.monsters):
            for card in actor.hand:
                if card.card.kind in ["normal", "effect", "legendary"] and self.ai_can_summon(card, actor):
                    actions.append({"kind": "set", "card": card, "score": self.ai_card_score(card, "set", actor)})
        for card in actor.hand:
            if card.card.kind in ["spell", "field"] and self.ai_can_activate(card, actor):
                actions.append({"kind": "activate", "card": card, "score": self.ai_activation_score(card, actor)})
            elif card.card.kind == "trap" and any(value is None for value in actor.spells):
                actions.append({"kind": "set", "card": card, "score": self.ai_card_score(card, "trap", actor)})
        return max(actions, key=lambda item: (item["score"], item["card"].card.id, item["kind"])) if actions else None

    def autonomous_actor(self):
        if self.chain_window and self.chain_priority: return self.chain_priority
        if self.pending_discard: return self.pending_discard
        for pending in [self.pending_trigger_order, self.pending_cost, self.pending_procedure, self.pending_response, self.pending_target, self.pending_summon, self.pending_effect]:
            if isinstance(pending, dict) and pending.get("actor"): return pending["actor"]
        if self.pending_trigger_order and self.pending_trigger_order.get("chooser"): return self.pending_trigger_order["chooser"]
        if self.pending_trap:
            defender = self.pending_trap.get("defender")
            if defender: return defender
        return self.active

    def ai_choose_cards(self, cards, actor, count):
        return sorted(list(cards or []), key=lambda item: (self.ai_card_score(item, "cost", actor), item.card.id))[:max(0, int(count or 0))]

    def ai_battle_target_score(self, attacker, target, actor):
        defender = self.other(actor)
        attack_value = self.effective_atk(attacker, actor)
        target_value = self.battle_value(target, defender)
        score = 0
        if target.battle_position == "attack":
            score += (attack_value - target_value) * 4
            if attack_value > target_value: score += 900
            elif attack_value < target_value: score -= 900
        else:
            score += 240 if attack_value > target_value else -180
        if not target.face_up: score += 80
        target_score = self.ai_target_score(target, actor)
        score += target_score
        if target.battle_position == "defense" and attack_value <= target_value:
            score -= target_score + 1000 + (target_value - attack_value) * 4 * float(actor.character.behavior_weights.get("duel", {}).get("defense_bias", 1.0))
        return score * float(actor.character.behavior_weights.get("duel", {}).get("attack_bias", 1.0))

    def ai_open_trap_window(self, attacker):
        defender = self.other(self.owner_of(attacker) or self.active)
        traps = [item for item in defender.spells if item and item.card.kind == "trap" and not item.face_up]
        if not traps: return False
        trap = max(traps, key=lambda item: (self.ai_card_score(item, "trap", defender), item.card.id))
        if self.ai_card_score(trap, "trap", defender) < float(defender.character.behavior_weights.get("duel", {}).get("trap_threshold", 0.0)): return False
        self.pending_trap = {"trap": trap, "attacker": attacker, "defender": defender}
        self.notify("question", f"Activate {trap.card.name}?", ["yes", "no"], {"trap": trap.card.id, "attacker": attacker.card.id, "defender": defender.character.id})
        self.log(f"Trap window: {trap.card.name} can answer {attacker.card.name}.")
        attacker_owner = self.owner_of(attacker)
        self.react("trap_window", defender.character.id, attacker_owner.character.id if attacker_owner else "", "opponent", "cards", trap.card.id)
        return True

    def ai_effect_answer(self, actor):
        notification = self.pending_notification("yes_no")
        if not notification: return "waiting"
        pending = self.pending_effect
        value = self.declarative_effect_score(pending["card"], pending["spec"], actor, self.other(actor)) if pending else 0
        answer = "yes" if value > 0 and "yes" in notification.options else "no" if "no" in notification.options else notification.options[0]
        return self.respond_notification(notification.notification_id, answer)

    def autonomous_step(self, actor):
        if self.finished: return "finished"
        if self.chain_window:
            if self.chain_priority is actor: return self.ai_chain_step_for(actor)
            return "waiting"
        if self.pending_discard:
            if self.pending_discard is actor and actor.hand: return self.discard(self.ai_choose_cards(actor.hand, actor, 1)[0])
            return "waiting"
        if self.pending_trigger_order:
            pending = self.pending_trigger_order
            if pending.get("chooser") is not actor: return "waiting"
            required = [item for item in pending["members"] if not item.get("optional")]
            optional = [item for item in pending["members"] if item.get("optional") and self.ai_trigger_effect_score(item, actor) > 0]
            selected = required + optional
            selected.sort(key=lambda item: (-self.ai_trigger_effect_score(item, actor), item["effect_id"]))
            return self.resolve_trigger_order([item["effect_id"] for item in selected])
        if self.pending_cost:
            if self.pending_cost.get("actor") is not actor: return "waiting"
            required = int(self.pending_cost.get("required", 0))
            return self.resolve_pending_cost(self.ai_choose_cards(self.pending_cost.get("candidates", []), actor, required))
        if self.pending_procedure:
            if self.pending_procedure.get("actor") is not actor: return "waiting"
            procedure = self.pending_procedure["procedure"]
            selected = self.ai_procedure_selection(self.pending_procedure["card"], actor, procedure)
            if not selected: return self.abort_procedure("No legal autonomous procedure selection exists.")
            return self.resolve_pending_procedure(selected)
        if self.pending_response:
            if self.pending_response.get("actor") is not actor: return "waiting"
            candidates = self.pending_response.get("candidates", [])
            if candidates:
                selected = max(candidates, key=lambda item: (self.ai_target_score(item, actor, self.pending_response.get("spec")), self.entity_id(item)))
                return self.resolve_pending_response([selected])
            return "waiting"
        if self.pending_target:
            if self.pending_target.get("actor") is not actor: return "waiting"
            candidates = self.pending_target.get("candidates", [])
            if candidates:
                selected = max(candidates, key=lambda item: (self.ai_target_score(item, actor), self.entity_id(item)))
                return self.respond_notification(self.pending_notification("choose_target").notification_id, "ok", selected)
            return "waiting"
        if self.pending_summon:
            if self.pending_summon.get("actor") is not actor: return "waiting"
            candidates = self.pending_summon.get("candidates", [])
            if candidates:
                selected = max(candidates, key=lambda item: (self.ai_target_score(item, actor), self.entity_id(item)))
                return self.respond_notification(self.pending_notification("choose_target").notification_id, "ok", selected)
            return "waiting"
        if self.pending_effect:
            if self.pending_effect.get("actor") is not actor: return "waiting"
            return self.ai_effect_answer(actor)
        if self.pending_trap:
            defender = self.pending_trap.get("defender") or next((side for side in [self.player, self.opponent] if self.pending_trap["trap"] in side.spells), None)
            if defender is not actor: return "waiting"
            return self.activate_trap(self.pending_trap["trap"], actor)
        if self.active is not actor: return "waiting"
        if self.phase in ["MAIN 1", "MAIN 2"]:
            plan = self.ai_main_plan(actor)
            if plan:
                card, kind = plan["card"], plan["kind"]
                if kind == "summon":
                    if card.card.summon_method in ["fusion", "ritual"]: return self.begin_summon_procedure(card, actor, ProcedureSpec.from_card(card))
                    return self.summon(card, actor)
                if kind == "set": return self.set_card(card, actor)
                if kind == "activate": return self.activate(card, actor)
        if self.phase == "BATTLE":
            attackers = [item for item in actor.monsters if item and item.face_up and item.battle_position == "attack" and not item.attacked]
            if attackers:
                attacker = max(attackers, key=lambda item: (self.ai_card_score(item, "monster", actor), item.card.id))
                if self.ai_open_trap_window(attacker): return "pending_trap"
                targets = [item for item in self.other(actor).monsters if item]
                target = max(targets, key=lambda item: (self.ai_battle_target_score(attacker, item, actor), self.entity_id(item))) if targets else None
                return self.resolve_battle(actor, attacker, target)
        self.advance()
        return "phase_advanced"

    def ai_step(self):
        if self.finished or self.active is not self.opponent: return
        self.autonomous_step(self.opponent)


class Button:
    def __init__(self, rect, label, callback, accent=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.callback = callback
        self.accent = accent or COLORS["line"]
        self.hover = False
        self.selected = False

    def update(self, position):
        self.hover = self.rect.collidepoint(position)

    def draw(self, surface, font, compact=False):
        fill = (151, 108, 73) if self.hover or self.selected else (116, 82, 70)
        outline = COLORS["gold"] if self.hover or self.selected else COLORS["line"]
        rounded(surface, self.rect, fill, outline, 8, 2)
        draw_text(surface, self.label, self.rect.center, font, COLORS["cream"], "center")


class TextInput:
    def __init__(self, rect, value=""):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.active = False

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif event.key == pygame.K_RETURN:
                self.active = False
            elif event.unicode.isprintable() and len(self.value) < 28:
                self.value += event.unicode

    def draw(self, surface, font, label):
        draw_text(surface, label, (self.rect.x, self.rect.y - 22), font, COLORS["muted"])
        rounded(surface, self.rect, (143, 104, 76), COLORS["gold"] if self.active else COLORS["line"], 7, 2)
        draw_text(surface, self.value + ("|" if self.active else ""), (self.rect.x + 10, self.rect.centery), font, COLORS["cream"], "midleft")


class TeamDuelEngine:
    def __init__(self, store, player_team_id=None, opponent_team_id=None, place_id=None, player_team=None, opponent_team=None, format_name="TEAMvTEAM", starter="opponent", reserved=False):
        self.store = store
        roles = store.role_config()
        player_team_id = player_team_id or roles["default_player_team"]
        opponent_team_id = opponent_team_id or roles["default_opponent_team"]
        place_id = place_id or roles["default_place"]
        self.player_team = player_team or store.teams[player_team_id]
        self.opponent_team = opponent_team or store.teams[opponent_team_id]
        self.format_name = format_name
        self.starter = starter
        self.place_id = place_id
        self.place_reserved = reserved or store.reserve_place(place_id)
        self.round = 1
        self.results = []
        self.current = None
        self.finished = False
        self.winner = None
        self.events = []
        self.start_round()

    def log(self, message):
        self.events.append(message)
        self.events = self.events[-8:]

    def roster(self, team):
        return [self.store.characters[key] for key in team.members if key in self.store.characters]

    def start_round(self):
        player_roster = self.roster(self.player_team)
        opponent_roster = self.roster(self.opponent_team)
        if not player_roster or not opponent_roster:
            self.finish(self.opponent_team, "missing roster")
            return
        player = player_roster[(self.round - 1) % len(player_roster)]
        opponent = opponent_roster[(self.round - 1) % len(opponent_roster)]
        player_effect = self.player_team.team_effect.get("selected") if self.player_team.effect_locked and self.player_team.team_effect else None
        opponent_effect = self.opponent_team.team_effect.get("selected") if self.opponent_team.effect_locked and self.opponent_team.team_effect else None
        self.current = DuelEngine(self.store, player.id, opponent.id, self.place_id, self.starter != "player", player_effect, opponent_effect)
        self.log(f"{self.format_name} round {self.round}: {player.name} vs {opponent.name}.")
        if player_effect: self.log(f"{self.player_team.name} effect: {player_effect.get('kind')}.")
        if opponent_effect: self.log(f"{self.opponent_team.name} effect: {opponent_effect.get('kind')}.")

    def step(self):
        if self.finished or not self.current: return
        if self.current.finished:
            winner_id = self.current.winner.character.id if self.current.winner else "draw"
            self.results.append({"round": self.round, "winner": winner_id, "reason": self.current.reason})
            self.log(f"Round {self.round} result: {winner_id} by {self.current.reason}.")
            if self.round >= 3:
                player_wins = sum(1 for result in self.results if result["winner"] in self.player_team.members)
                opponent_wins = sum(1 for result in self.results if result["winner"] in self.opponent_team.members)
                self.finish(self.player_team if player_wins > opponent_wins else self.opponent_team if opponent_wins > player_wins else None, "three rounds complete")
            else:
                self.round += 1
                self.start_round()
            return
        if self.current.active is self.current.opponent:
            self.current.ai_step()
        else:
            monsters = [card for card in self.current.player.hand if card.card.kind in ["normal", "effect", "legendary"]]
            if self.current.phase in ["MAIN 1", "MAIN 2"] and monsters and any(value is None for value in self.current.player.monsters): self.current.summon(monsters[0])
            self.current.advance()

    def finish(self, winner, reason):
        self.finished = True
        self.winner = winner
        if self.place_reserved:
            self.store.release_place(self.place_id)
            self.place_reserved = False
        self.log("Team duel draw." if winner is None else f"{winner.name} wins the team duel.")
        self.store.world.setdefault("championships", [])
        self.store.save()


class Scene:
    def __init__(self, app):
        self.app = app
        self.buttons = []
        self.time = 0

    def enter(self):
        self.buttons = []

    def leave(self):
        pass

    def handle(self, event):
        if event.type == pygame.MOUSEMOTION:
            for button in self.buttons: button.update(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in reversed(self.buttons):
                if button.rect.collidepoint(event.pos):
                    button.callback()
                    return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.pop()

    def update(self, dt):
        self.time += dt

    def draw_background(self, surface, image_name, alpha=255):
        image = self.app.assets.image(image_name, (W, H))
        if not image: return
        if alpha != 255:
            image = image.copy()
            image.set_alpha(alpha)
        ui_blit(surface, image, (0, 0))

    def draw_menu_composition(self, surface):
        background = self.app.assets.menu_layer("menu_background", (W, H))
        if background is None: background = self.app.assets.image("menu_anchor", (W, H))
        ui_blit(surface, background, (0, 0))
        layers = [("dueler_left", (0, 0, 275, 600)), ("dueler_center", (238, 0, 324, 600)), ("dueler_right", (548, 0, 252, 600))]
        for name, rect in layers:
            image = self.app.assets.menu_layer(name, (rect[2], rect[3]))
            if image is not None: ui_blit(surface, image, rect[:2])

    def draw_panel(self, surface, rect, title=None, accent=COLORS["gold"]):
        rect = pygame.Rect(rect)
        shadow = pygame.Surface((rect.width + 8, rect.height + 8), pygame.SRCALPHA)
        shadow.fill((58, 43, 53, 35))
        ui_blit(surface, shadow, (rect.x + 4, rect.y + 5))
        rounded(surface, rect, (117, 83, 70), COLORS["line"], 12, 2)
        ui_draw_line(surface, COLORS["gold"], (rect.x + 18, rect.y + 45), (rect.right - 18, rect.y + 45), 2)
        if title:
            draw_text(surface, title, (rect.x + 18, rect.y + 15), self.app.assets.font(18, True), COLORS["cream"])

    def draw_buttons(self, surface, size=15):
        for button in self.buttons: button.draw(surface, self.app.assets.font(size, True))


class FirstRunScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.name = TextInput((238, 208, 324, 36), "")
        self.portrait = TextInput((238, 278, 324, 36), "pfp_placeholder")
        self.gender = "other"

    def enter(self):
        self.buttons = [Button((238, 356, 100, 38), "HE", lambda: self.choose_gender("he"), COLORS["cyan"]), Button((348, 356, 100, 38), "SHE", lambda: self.choose_gender("she"), COLORS["violet"]), Button((458, 356, 104, 38), "OTHER", lambda: self.choose_gender("other"), COLORS["gold"]), Button((284, 428, 232, 44), "ENTER PLAYGROUND", lambda: self.complete(), COLORS["green"])]

    def choose_gender(self, gender):
        self.gender = gender

    def complete(self):
        self.app.store.register_user(self.name.value, self.portrait.value, self.gender)
        self.app.replace(MainMenuScene(self.app))

    def handle(self, event):
        self.name.handle(event)
        self.portrait.handle(event)
        super().handle(event)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        ui_blit(surface, self.app.assets.image("splash", (W, H)), (0, 0))
        veil = ui_surface((W, H), pygame.SRCALPHA); veil.fill((247, 227, 177, 48)); ui_blit(surface, veil, (0, 0))
        self.draw_panel(surface, (170, 92, 460, 430), "WELCOME TO THE PLAYGROUND", COLORS["gold"])
        draw_text(surface, "Set your player identity. Every value can be changed later.", (400, 145), self.app.assets.font(13), COLORS["muted"], "center")
        self.name.draw(surface, self.app.assets.font(13), "Player name")
        self.portrait.draw(surface, self.app.assets.font(13), "PFP asset name or file key")
        draw_text(surface, "Gender: " + self.gender.upper(), (400, 414), self.app.assets.font(14, True), COLORS["cream"], "center")
        self.draw_buttons(surface, 12)


class SplashScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.elapsed = 0
        self.splash_name = "splash"

    def enter(self):
        names = self.app.assets.splash_names or ["splash"]
        self.splash_name = names[int(time.time()) % len(names)]

    def update(self, dt):
        super().update(dt)
        self.elapsed += dt
        if self.elapsed > 3.4:
            target = FirstRunScene(self.app) if not self.app.store.save_data.get("setup_complete", False) else MainMenuScene(self.app)
            self.app.replace(target)

    def draw(self, surface):
        self.draw_background(surface, self.splash_name)
        veil = ui_surface((W, H), pygame.SRCALPHA)
        veil.fill((247, 227, 177, 32))
        ui_blit(surface, veil, (0, 0))
        alpha = clamp(int((self.elapsed - 0.4) * 160), 0, 255)
        title = self.app.assets.font(34, True).render("CARDS BATTLERS PLAYGROUNDS", True, COLORS["cream"])
        title.set_alpha(alpha)
        ui_blit(surface, title, title.get_rect(center=(W // 2, H - 120)))
        draw_text(surface, "THE PLAYGROUND IS WAITING", (W // 2, H - 78), self.app.assets.font(15), COLORS["gold"], "center")
        draw_text(surface, "Click or press Enter to continue", (W // 2, H - 34), self.app.assets.font(12), COLORS["muted"], "center")

    def handle(self, event):
        if event.type in [pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN]:
            self.app.replace(MainMenuScene(self.app))


class MainMenuScene(Scene):
    primary_items = [("BATTLE", "battle", COLORS["gold"]), ("CARDS", "cards", COLORS["cyan"]), ("CHARACTERS", "characters", COLORS["violet"]), ("PLACES", "places", COLORS["green"]), ("SETTINGS", "settings", COLORS["muted"]), ("QUIT", "quit", COLORS["red"])]
    secondary_map = {
        "battle": [("FREE CHARACTERS", "free"), ("TEAMS", "teams"), ("REQUESTS", "requests"), ("ORDERS", "orders"), ("WATCH", "watch"), ("CHAMPIONSHIPS", "championship")],
        "cards": [("VIEW LIBRARY", "library"), ("DECKS", "decks"), ("CARD MAKER", "card_maker"), ("LOGIC MANAGER", "logic"), ("TRADING", "trading"), ("IMPORT / EXPORT", "import")],
        "characters": [("ALL CHARACTERS", "characters"), ("TEAMS", "teams"), ("CHARACTER MAKER", "character_maker")],
        "places": [("VIEW PLACES", "places"), ("ACTIVE / FREE", "active_places"), ("PLACE MAKER", "place_maker")],
        "settings": [("AUDIO / VOCALS", "settings"), ("WINDOW / FULLSCREEN", "settings"), ("DIFFICULTY", "settings")]
    }

    def enter(self):
        self.section = ""
        self.secondary_items = []
        self.primary_buttons = []
        self.buttons = []
        for index, (label, target, accent) in enumerate(self.primary_items):
            rect = (298, 188 + index * 43, 204, 34)
            callback = self.app.quit if target == "quit" else lambda target=target: self.select_section(target)
            button = Button(rect, label, callback, accent)
            self.primary_buttons.append(button)
        self.buttons = list(self.primary_buttons)
        self.app.assets.play_music(self.app.store.save_data.get("music", True), 0.35)

    def select_section(self, section):
        self.section = section
        self.secondary_items = list(self.secondary_map.get(section, []))
        self.buttons = list(self.primary_buttons)
        if not section: return
        for index, (label, target) in enumerate(self.secondary_items):
            self.buttons.append(Button((42, 191 + index * 43, 218, 34), label, lambda target=target: self.open_secondary(target), COLORS["cyan"]))
        self.buttons.append(Button((42, 191 + len(self.secondary_map.get(section, [])) * 43, 218, 34), "CLOSE LIST", lambda: self.select_section(""), COLORS["muted"]))

    def open_secondary(self, target):
        if target == "free": self.app.push(BattleScene(self.app))
        elif target in ["requests", "orders", "watch", "championship"]:
            scene = BattleScene(self.app); self.app.push(scene); scene.set_tab(target)
        elif target == "teams": self.app.push(TeamsScene(self.app))
        elif target == "library": self.app.push(LibraryScene(self.app))
        elif target == "decks": self.app.push(DeckScene(self.app))
        elif target == "card_maker": self.app.push(CardMakerScene(self.app))
        elif target == "logic": self.app.push(LogicManagerScene(self.app))
        elif target == "trading": self.app.push(TradingScene(self.app))
        elif target == "import": self.app.push(ImportExportScene(self.app))
        elif target == "character_maker": self.app.push(CharacterMakerScene(self.app))
        elif target == "place_maker": self.app.push(PlaceMakerScene(self.app))
        elif target in ["characters", "places", "settings"]: self.app.open_target(target)
        elif target == "active_places": self.app.push(PlacesScene(self.app))

    def draw(self, surface):
        self.draw_menu_composition(surface)
        veil = ui_surface((W, H), pygame.SRCALPHA)
        veil.fill((246, 222, 163, 28))
        ui_blit(surface, veil, (0, 0))
        draw_text(surface, "CARDS BATTLERS PLAYGROUNDS", (W // 2, 48), self.app.assets.font(28, True), COLORS["cream"], "midtop")
        draw_text(surface, "A community-built card battle playground", (W // 2, 83), self.app.assets.font(14), COLORS["cream"], "midtop")
        rounded(surface, (286, 149, 228, 323), (112, 79, 68), COLORS["gold"], 14, 2)
        draw_text(surface, "MAIN MENU", (W // 2, 166), self.app.assets.font(14, True), COLORS["cream"], "midtop")
        if self.section:
            rounded(surface, (30, 149, 242, 323), (132, 94, 73), COLORS["gold"], 14, 2)
            draw_text(surface, self.section.upper() + " LIST", (151, 166), self.app.assets.font(13, True), COLORS["cream"], "midtop")
        self.draw_buttons(surface, 14)
        active = self.app.store.characters.get(self.app.store.role_config()["player_character"])
        draw_text(surface, f"{self.app.clock_text()}  |  {active.name if active else 'Unregistered'}", (W - 18, 576), self.app.assets.font(11), COLORS["muted"], "bottomright")
        team_id = self.app.store.role_config()["default_player_team"]
        team = self.app.store.teams.get(team_id)
        draw_text(surface, team.name if team else "", (W // 2, 552), self.app.assets.font(13, True), COLORS["cream"], "center")


class BattleScene(Scene):
    formats = ["1v1", "1vTEAM", "TEAMv1", "TEAMvTEAM"]

    def enter(self):
        self.tab = "free"
        self.format_index = 0
        self.nav_buttons = [
            Button((36, 96, 112, 32), "FREE DUEL", lambda: self.set_tab("free")),
            Button((156, 96, 112, 32), "REQUESTS", lambda: self.set_tab("requests")),
            Button((276, 96, 104, 32), "ORDERS", lambda: self.set_tab("orders")),
            Button((388, 96, 110, 32), "WATCH", lambda: self.set_tab("watch"))
        ]
        self.utility_button = Button((516, 96, 120, 32), "CHAMPIONSHIP", lambda: self.set_tab("championship"))
        self.format_button = Button((640, 96, 120, 32), "FORMAT: 1V1", lambda: self.cycle_format(), COLORS["violet"])
        self.back_button = Button((652, 530, 110, 38), "BACK", lambda: self.app.pop())
        self.refresh_content()

    @property
    def duel_format(self):
        return self.formats[self.format_index]

    def cycle_format(self):
        self.format_index = (self.format_index + 1) % len(self.formats)
        self.format_button.label = "FORMAT: " + self.duel_format
        self.refresh_content()

    def set_tab(self, tab):
        self.tab = tab
        for button in self.nav_buttons: button.selected = button.label.lower().replace(" ", "") == ("free" + "duel" if tab == "free" else tab)
        if tab == "orders": self.utility_button.label, self.utility_button.callback = "OPEN ORDER", self.add_world_entry
        elif tab == "requests": self.utility_button.label, self.utility_button.callback = "NEW REQUEST", self.add_world_entry
        elif tab == "free": self.utility_button.label, self.utility_button.callback = "CHAMPIONSHIP", lambda: self.set_tab("championship")
        elif tab == "championship": self.utility_button.label, self.utility_button.callback = "HOST LEVEL", lambda: self.select_opponent(self.app.store.role_config()["default_opponent_character"], 1)
        else: self.utility_button.label, self.utility_button.callback = "REFRESH", self.refresh_content
        self.refresh_content()

    def refresh_content(self):
        self.items = []
        if self.tab == "free":
            if self.duel_format in ["1v1", "TEAMv1"]:
                player_id = self.app.store.role_config()["player_character"]
                self.items = [(char.name, char.id, char.relationship, char.stars, char.smartness, None) for char in self.app.store.characters.values() if char.id != player_id]
            else:
                player_team_id = self.app.store.role_config()["default_player_team"]
                self.items = [(team.name, team.id, team.relationship, team.rank, len(team.members), None) for team in self.app.store.teams.values() if team.id != player_team_id and len(team.members) == 3]
        elif self.tab == "requests":
            self.items = [(entry.get("title", "Request"), entry.get("from", ""), entry.get("status", "open"), 5, 7, entry.get("id")) for entry in self.app.store.world.get("requests", []) if entry.get("status") in ["open", "queued", "active"]]
        elif self.tab == "orders":
            self.items = [(entry.get("title", "Order"), entry.get("taker", ""), entry.get("status", "open"), 5, 7, entry.get("id")) for entry in self.app.store.world.get("orders", []) if entry.get("status") == "open"]
        elif self.tab == "championship":
            self.items = [(f"Level {level} championship", self.app.store.role_config()["default_opponent_character"], "hostable", level + 3, level + 4, level) for level in range(1, 4)]
        else:
            roles = self.app.store.role_config()
            player_name = self.app.store.characters[roles["player_character"]].name
            opponent_name = self.app.store.characters[roles["default_opponent_character"]].name
            self.items = [(f"Live duel: {opponent_name} vs {player_name}", "watch", "active", 8, 10, None), ("Archived duel: authored showcase", "watch", "history", 5, 7, None)]
        self.buttons = list(self.nav_buttons) + [self.utility_button, self.format_button]
        self.request_button_indices = []
        for index, item in enumerate(self.items):
            target = item[1]
            action = "WATCH" if self.tab == "watch" else "ACCEPT" if self.tab == "requests" else "TAKE" if self.tab == "orders" else "HOST" if self.tab == "championship" else "DUEL"
            if self.tab == "requests":
                request = self.app.store.request_by_id(item[5])
                main_index = None
                ignore_index = None
                if request and request.get("status") == "open":
                    is_cancel = request.get("from") == self.app.store.role_config()["player_character"]
                    row_action = "CANCEL" if is_cancel else action
                    main_index = len(self.buttons)
                    self.buttons.append(Button((600, 205 + index * 78 + 17, 78, 36), row_action, lambda entry_id=item[5], is_cancel=is_cancel: self.select_opponent("cancel" if is_cancel else "accept", entry_id)))
                    if not is_cancel:
                        ignore_index = len(self.buttons)
                        self.buttons.append(Button((684, 205 + index * 78 + 17, 54, 36), "IGNORE", lambda entry_id=item[5]: self.select_opponent("ignore", entry_id), COLORS["muted"]))
                self.request_button_indices.append((main_index, ignore_index))
            else: self.buttons.append(Button((640, 205 + index * 78 + 17, 80, 36), action, lambda target=target, entry_id=item[5]: self.select_opponent(target, entry_id)))
        self.buttons.append(self.back_button)

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN and event.key in [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4]:
            self.set_tab(["free", "requests", "orders", "watch"][event.key - pygame.K_1])

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "BATTLE", (34, 28), self.app.assets.font(30, True), COLORS["gold"])
        draw_text(surface, "Choose an active character, request, order, or simulated duel to watch.", (36, 65), self.app.assets.font(14), COLORS["muted"])
        for button in self.buttons[:4]: button.draw(surface, self.app.assets.font(12, True))
        self.draw_panel(surface, (34, 142, 732, 382), self.tab.upper() + " BOARD", COLORS["cyan"])
        for index, item in enumerate(self.items):
            name, target, relation, stars, smartness, entry_id = item
            y = 205 + index * 78
            accent = COLORS["red"] if target == self.app.store.role_config()["default_opponent_character"] else COLORS["cyan"]
            rounded(surface, (62, y, 676, 70), (132, 94, 73), COLORS["line"], 8, 1)
            draw_text(surface, name, (82, y + 14), self.app.assets.font(16, True), COLORS["cream"])
            draw_text(surface, f"Status: {relation}   |   Star level: {stars}   |   Smartness: {smartness}/10", (82, y + 42), self.app.assets.font(12), COLORS["muted"])
            if self.tab == "requests":
                main_index, ignore_index = self.request_button_indices[index]
                if main_index is not None: self.buttons[main_index].draw(surface, self.app.assets.font(9, True))
                if ignore_index is not None: self.buttons[ignore_index].draw(surface, self.app.assets.font(8, True))
            else: self.buttons[6 + index].draw(surface, self.app.assets.font(11, True))
        self.buttons[4].draw(surface, self.app.assets.font(11, True))
        self.buttons[5].draw(surface, self.app.assets.font(11, True))
        self.buttons[-1].draw(surface, self.app.assets.font(12, True))

    def add_world_entry(self):
        roles = self.app.store.role_config()
        if self.tab == "orders": self.app.store.place_order(roles["player_character"], roles["default_opponent_character"], "a card by type")
        elif self.tab in ["free", "requests"]: self.app.store.add_request(roles["player_character"], roles["default_opponent_character"], "friendly duel", kind="duel", format_name="1v1", preferred_place=roles["default_place"], relationship_intent="stranger")
        self.refresh_content()

    def select_opponent(self, target, entry_id=None):
        if self.tab == "championship" and entry_id:
            player_id = self.app.store.role_config()["player_character"]
            self.app.store.world.setdefault("championships", []).append({"id": "champ_" + str(int(time.time() * 1000)), "level": entry_id, "host": player_id, "status": "open", "participants": [player_id]})
            self.app.store.save()
            self.app.notify(f"Level {entry_id} championship hosted. The world can now populate its bracket.")
            self.refresh_content()
            return
        if self.tab == "requests" and entry_id:
            decision = "ignore" if target == "ignore" else "cancel" if target == "cancel" else "accept"
            if self.app.store.respond_request(entry_id, self.app.store.role_config()["player_character"], decision):
                self.app.notify("Request moved to " + ("the real-time queue." if decision == "accept" else decision + "."))
            self.refresh_content()
            return
        if self.tab == "orders" and entry_id: self.app.store.close_world_entry("orders", entry_id)
        if target == "watch": self.app.push(WatchScene(self.app))
        elif self.tab == "free": self.app.push(PreDuelScene(self.app, target, self.duel_format))
        else: self.app.push(PreDuelScene(self.app, target))


class PreDuelScene(Scene):
    def __init__(self, app, opponent_id, format_name="1v1"):
        super().__init__(app)
        self.opponent_id = opponent_id
        self.format_name = format_name
        self.requester_id = opponent_id
        self.acceptor_id = app.store.role_config()["player_character"]
        self.requested_first_side = "opponent"
        self.dice_launcher_id = self.acceptor_id
        self.choice = ""
        self.decision = "request"
        self.dice_value = None
        self.dice_owner = ""
        self.dice_clock = 0.0
        self.dice_rolling = False
        self.elapsed = 0

    def enter(self):
        self.buttons = [Button((90, 496, 180, 44), "ACCEPT FIRST", lambda: self.accept_first(), COLORS["cyan"]), Button((290, 496, 180, 44), "DENY / ROLL", lambda: self.deny_first(), COLORS["gold"]), Button((490, 496, 120, 44), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def accept_first(self):
        self.choice = self.requested_first_side
        self.decision = "accepted"
        self.app.store.world.setdefault("simulation_events", []).append({"type": "first_play_decision", "mode": "accepted", "requester": self.requester_id, "acceptor": self.acceptor_id, "first": self.choice, "time": time.time()})
        self.app.store.save()
        self.launch()

    def deny_first(self):
        self.decision = "denied"
        self.dice_rolling = True
        self.dice_clock = 0.0
        self.dice_value = None
        self.dice_owner = self.dice_launcher_id
        self.buttons = [Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def roll_result(self):
        self.dice_value = random.randint(1, 6)
        self.choice = self.dice_launcher_id if self.dice_value <= 3 else self.requester_id
        self.decision = "rolled"
        self.dice_rolling = False
        self.app.store.world.setdefault("simulation_events", []).append({"type": "first_play_decision", "mode": "dice", "requester": self.requester_id, "acceptor": self.acceptor_id, "launcher": self.dice_launcher_id, "value": self.dice_value, "first": self.choice, "time": time.time()})
        self.app.store.save()
        self.app.notify(f"Dice result {self.dice_value}: {self.choice} goes first.")
        self.buttons = [Button((170, 496, 180, 44), "START DUEL", lambda: self.launch(), COLORS["cyan"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def launch(self):
        place_id = self.app.store.role_config()["default_place"]
        place = self.app.store.places[place_id]
        if not self.app.store.reserve_place(place_id):
            self.app.notify(place.name + " is full. This duel must wait or choose another place.")
            return
        if self.format_name == "1v1": self.app.push(DuelScene(self.app, self.opponent_id, self.choice or self.acceptor_id, place_id, True))
        else: self.app.push(TeamDuelScene(self.app, self.format_name, self.opponent_id, self.choice or self.acceptor_id, True))

    def update(self, dt):
        self.elapsed += dt
        if self.dice_rolling:
            self.dice_clock += dt
            if self.dice_clock >= 0.8: self.roll_result()

    def draw_dice(self, surface):
        rounded(surface, (328, 150, 144, 144), (238, 241, 252), COLORS["gold"], 18, 4)
        value = random.randint(1, 6) if self.dice_rolling else self.dice_value or 0
        if value:
            points = {1: [(400, 222)], 2: [(374, 196), (426, 248)], 3: [(374, 196), (400, 222), (426, 248)], 4: [(374, 196), (426, 196), (374, 248), (426, 248)], 5: [(374, 196), (426, 196), (400, 222), (374, 248), (426, 248)], 6: [(374, 190), (426, 190), (374, 222), (426, 222), (374, 254), (426, 254)]}[value]
            for point in points: ui_draw_circle(surface, COLORS["ink"], point, 9)
        else: draw_text(surface, "?", (400, 222), self.app.assets.font(48, True), COLORS["ink"], "center")

    def draw(self, surface):
        self.draw_background(surface, self.app.store.places[self.app.store.role_config()["default_place"]].background)
        veil = ui_surface((W, H), pygame.SRCALPHA)
        veil.fill((247, 227, 177, 36))
        ui_blit(surface, veil, (0, 0))
        roles = self.app.store.role_config()
        player = self.app.store.characters[roles["player_character"]]
        rival = self.app.store.characters.get(self.opponent_id, self.app.store.characters[roles["default_opponent_character"]])
        self.draw_panel(surface, (54, 74, 692, 375), "PRE-DUEL  |  " + self.format_name, COLORS["gold"])
        draw_text(surface, self.app.store.places[self.app.store.role_config()["default_place"]].name, (400, 115), self.app.assets.font(17, True), COLORS["cyan"], "center")
        if self.format_name == "1v1":
            draw_text(surface, f"REQUESTER: {rival.name}", (86, 138), self.app.assets.font(10, True), COLORS["red"])
            draw_text(surface, f"ACCEPTOR: {player.name}", (506, 138), self.app.assets.font(10, True), COLORS["cyan"], "topright")
            self.draw_character_card(surface, player, (86, 159), COLORS["cyan"])
            self.draw_character_card(surface, rival, (506, 159), COLORS["red"])
        else:
            player_team, opponent_team = self.team_sides()
            draw_text(surface, f"REQUESTER: {opponent_team.name}", (86, 138), self.app.assets.font(10, True), COLORS["red"])
            draw_text(surface, f"ACCEPTOR: {player_team.name}", (506, 138), self.app.assets.font(10, True), COLORS["cyan"], "topright")
            self.draw_team_card(surface, player_team, (86, 159), COLORS["cyan"])
            self.draw_team_card(surface, opponent_team, (506, 159), COLORS["red"])
        draw_text(surface, "VS", (400, 270), self.app.assets.font(32, True), COLORS["gold"], "center")
        requester_name, acceptor_name = self.side_labels()
        if self.decision == "request": draw_text(surface, f"{requester_name} requests first play. Accept or deny to trigger the GDD dice rule.", (400, 403), self.app.assets.font(12), COLORS["muted"], "center")
        elif self.decision == "denied" or self.dice_rolling: draw_text(surface, f"{requester_name} denied the request. Launcher: {acceptor_name}. Launcher owns 1–3; {requester_name} owns 4–6.", (400, 403), self.app.assets.font(11), COLORS["gold"], "center"); self.draw_dice(surface)
        else: draw_text(surface, f"Dice result {self.dice_value}: {acceptor_name if self.choice == 'player' else requester_name} goes first.", (400, 403), self.app.assets.font(13), COLORS["gold"], "center"); self.draw_dice(surface)
        self.draw_buttons(surface, 12)

    def side_labels(self):
        roles = self.app.store.role_config()
        if self.format_name == "1v1": return self.app.store.characters.get(self.requester_id, self.app.store.characters[roles["default_opponent_character"]]).name, self.app.store.characters[roles["player_character"]].name
        player_team, opponent_team = self.team_sides()
        return opponent_team.name, player_team.name

    def team_sides(self):
        if self.format_name == "1vTEAM":
            roles = self.app.store.role_config()
            player = self.app.store.characters[roles["player_character"]]
            player_team = TeamDef("match_player", player.name, [player.id], player.id, [roles["default_place"]], "solo")
            opponent_team = self.app.store.teams.get(self.opponent_id, self.app.store.teams[roles["default_opponent_team"]])
        elif self.format_name == "TEAMv1":
            roles = self.app.store.role_config()
            opponent = self.app.store.characters.get(self.opponent_id, self.app.store.characters[roles["default_opponent_character"]])
            player_team = self.app.store.teams[roles["default_player_team"]]
            opponent_team = TeamDef("match_opponent", opponent.name, [opponent.id], opponent.id, [roles["default_place"]], "solo")
        else:
            roles = self.app.store.role_config()
            player_team = self.app.store.teams[roles["default_player_team"]]
            opponent_team = self.app.store.teams.get(self.opponent_id, self.app.store.teams[roles["default_opponent_team"]])
        return player_team, opponent_team

    def draw_team_card(self, surface, team, pos, accent):
        x, y = pos
        rounded(surface, (x, y, 210, 190), (12, 21, 47), accent, 2, 12)
        draw_text(surface, team.name, (x + 105, y + 24), self.app.assets.font(17, True), COLORS["cream"], "center")
        members = [self.app.store.characters[key].name for key in team.members if key in self.app.store.characters]
        for index, name in enumerate(members[:3]): draw_text(surface, f"{index + 1}. {name}", (x + 18, y + 72 + index * 28), self.app.assets.font(13), accent)
        draw_text(surface, f"{len(team.members)} member roster", (x + 105, y + 166), self.app.assets.font(11), COLORS["muted"], "center")

    def draw_character_card(self, surface, char, pos, accent):
        x, y = pos
        rounded(surface, (x, y, 210, 190), (12, 21, 47), accent, 2, 12)
        image = self.app.assets.image(char.portrait, (92, 92)) or self.app.assets.image("pfp_placeholder", (92, 92))
        if image: ui_blit(surface, image, (x + 59, y + 14))
        draw_text(surface, char.name, (x + 105, y + 123), self.app.assets.font(17, True), COLORS["cream"], "center")
        draw_text(surface, f"{char.stars} stars  |  {char.mood}", (x + 105, y + 150), self.app.assets.font(12), accent, "center")
        draw_text(surface, ", ".join(char.preferred_families), (x + 105, y + 171), self.app.assets.font(11), COLORS["muted"], "center")



class DuelScene(Scene):
    def __init__(self, app, opponent_id=None, starter="player", place_id=None, reserved=False, spectator_battle=None, spectator_engine=None):
        super().__init__(app)
        roles = app.store.role_config()
        place_id = place_id or roles["default_place"]
        self.spectator = bool(spectator_battle)
        self.watched_battle = spectator_battle or {}
        if spectator_engine:
            self.engine = spectator_engine
        elif self.spectator:
            house_id = self.watched_battle.get("house") or self.watched_battle.get("accepted_by") or self.watched_battle.get("to") or self.watched_battle.get("from")
            guest_id = self.watched_battle.get("guest") or (self.watched_battle.get("to") if house_id == self.watched_battle.get("from") else self.watched_battle.get("from"))
            self.engine = app.store._world_session(self.watched_battle) or DuelEngine(app.store, house_id, guest_id, place_id, True)
        else:
            self.engine = DuelEngine(app.store, roles["player_character"], opponent_id, place_id, starter == "opponent")
        self.layout = DuelLayout()
        self.place_id = place_id
        self.place_reserved = reserved
        self.reaction_player = ReactionPlayer()
        self.reaction_seen = 0
        self.stage = "watching" if self.spectator else "battle"
        self.message = "Live house POV: watching the duel." if self.spectator else "Select a card, then choose an action."
        self.ai_timer = 0
        self.buttons = []
        self.interactions_open = False
        self.interaction_rects = []
        self.hover_hand = None
        self.hover_hand_rect = None
        self.hover_attacker = None
        self.hover_target = None
        self.hover_set = None
        self.hover_procedure = None
        self.action_mode = "summon"
        self.action_mode_card = None
        self.question = None
        self.trigger_selection = []
        self.question_choice_rects = []
        self.card_list_popup = None
        self.player_deck_rect = self.layout.side_well_rect("player", "deck")
        self.hp_display = {"player": 8000, "opponent": 8000}
        self.hp_delta = {"player": 0, "opponent": 0}
        self.hp_delta_until = {"player": 0.0, "opponent": 0.0}

    def enter(self):
        super().enter()
        night = time.localtime().tm_hour < 6 or time.localtime().tm_hour >= 18
        self.app.assets.play_duel_music(self.place_id, self.app.store.save_data.get("music", True), 0.35, night)
        if self.spectator:
            self.reaction_seen = len(self.engine.reaction_events)
            self.buttons = [Button((650, 530, 110, 38), "EXIT WATCH", lambda: self.app.pop(), COLORS["muted"])]

    def handle(self, event):
        if self.spectator:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: self.app.pop(); return
            super().handle(event)
            return
        if event.type == pygame.MOUSEMOTION:
            self.update_hover(event.pos)
            if self.interactions_open:
                for button_rect, action in self.interaction_rects:
                    if button_rect.collidepoint(event.pos): self.message = action.upper()
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.question:
                if self.engine.pending_procedure: self.engine.cancel_pending_procedure()
                self.question = None
                return
            if event.key == pygame.K_SPACE and not self.question: self.next_phase()
            return super().handle(event)
        if event.type != pygame.MOUSEBUTTONDOWN: return
        if event.button == 1 and self.layout.hud_rect("player").collidepoint(event.pos) and not self.question:
            self.interactions_open = not self.interactions_open
            return
        if self.interactions_open and event.button == 1:
            for rect, action in self.interaction_rects:
                if rect.collidepoint(event.pos):
                    self.engine.interact(action)
                    self.message = self.engine.events[-1]
                    self.interactions_open = False
                    return
        if self.question:
            if event.button == 3 and self.question.get("stage") == "confirm":
                if self.question.get("kind") == "notifier": self.engine.answer_pending_effect("no")
                self.question = None
                return
            if not (self.question.get("kind") in ["discard", "procedure"] and self.question.get("stage") == "choose_card" and event.button == 1 and (self.question.get("kind") == "discard" or self.hover_procedure)):
                self.handle_question(event.pos)
                return
        if self.card_list_popup:
            if event.button == 1 and not self.layout.card_list_popup_rect().collidepoint(event.pos): self.card_list_popup = None
            return
        if event.button == 1:
            for side in ["opponent", "player"]:
                fusion_rect = self.layout.side_well_rect(side, "extra")
                graveyard_rect = self.layout.side_well_rect(side, "graveyard")
                if fusion_rect.collidepoint(event.pos):
                    if side == "player": self.open_card_list("FUSION", self.fusion_cards(side))
                    return
                if graveyard_rect.collidepoint(event.pos):
                    self.open_card_list("GRAVEYARD", self.engine.opponent.graveyard if side == "opponent" else self.engine.player.graveyard)
                    return
        if event.button == 1:
            for index, phase_name in enumerate(DUEL_PHASES):
                if self.layout.phase_rect(index).collidepoint(event.pos):
                    self.jump_to_phase(index)
                    return
        if event.button == 1 and self.player_deck_rect.collidepoint(event.pos):
            self.question = {"kind": "surrender", "stage": "confirm"}
            return
        if event.button == 3 and self.hover_hand:
            self.engine.selected_hand = self.hover_hand
            self.engine.selected_monster = None
            self.action_mode = "set"
            self.action_mode_card = self.hover_hand
            return
        if event.button == 1:
            if self.engine.pending_procedure and self.hover_procedure:
                success, msg = self.engine.toggle_procedure_material(self.hover_procedure)
                self.message = self.engine.procedure_selection_summary() if success else msg
                return
            if self.engine.phase == "BATTLE" and self.engine.selected_monster and self.hover_target:
                success, msg = self.engine.attack(self.engine.selected_monster, self.hover_target)
                self.message = self.engine.events[-1] if success else msg
                self.engine.selected_monster = None
                self.hover_target = None
                return
            if self.engine.pending_target and self.hover_target:
                notification = self.engine.pending_notification("choose_target")
                result = self.engine.respond_notification(notification.notification_id, "ok", self.hover_target) if notification else (False, "No target notification is pending.")
                success, msg = result
                self.message = self.engine.events[-1] if success and self.engine.events else msg
                self.hover_target = None
                return
            if self.hover_set:
                if self.engine.pending_trap:
                    success, msg = self.engine.activate_trap(self.hover_set)
                else:
                    success, msg = self.engine.activate_set_spell(self.hover_set)
                self.message = self.engine.events[-1] if success else msg
                return
            if self.hover_hand:
                if self.engine.pending_procedure:
                    success, msg = self.engine.toggle_procedure_material(self.hover_hand)
                    self.message = self.engine.procedure_selection_summary() if success else msg
                    return
                if self.engine.pending_cost and self.question and self.question.get("stage") == "choose_card":
                    success, msg = self.engine.respond_notification(self.question.get("notification_id"), "ok", self.hover_hand)
                    self.message = msg or (self.engine.events[-1] if success and self.engine.events else "")
                    if success: self.question = None
                    return
                if self.engine.pending_discard is self.engine.player and self.question and self.question.get("stage") == "choose_card":
                    self.engine.selected_hand = self.hover_hand
                    self.do_action("discard")
                    self.question = None
                    return
                self.engine.selected_hand = self.hover_hand
                self.engine.selected_monster = None
                self.do_action(self.action_mode_for_hand(self.hover_hand))
                self.action_mode_card = None
                return
            if self.hover_target is None and self.hover_attacker and self.engine.phase == "BATTLE":
                self.engine.selected_monster = self.hover_attacker
                return

    def action_mode_for_hand(self, card):
        if self.action_mode == "set": return "set"
        if card.card.kind in ["spell", "field"]: return "activate"
        return "summon"

    def hand_card_at(self, pos):
        hand = self.engine.player.hand
        if not hand: return None, None
        for index in reversed(range(len(hand))):
            normal_rect = self.layout.hand_rect("player", index, len(hand))
            lifted_rect = self.layout.hand_rect("player", index, len(hand), lifted=True)
            if lifted_rect.collidepoint(pos): return hand[index], lifted_rect
            if normal_rect.collidepoint(pos): return hand[index], normal_rect
        return None, None

    def player_monster_at(self, pos):
        for index, card in enumerate(self.engine.player.monsters):
            rect = self.layout.monster_rect("player", index)
            if card and rect.collidepoint(pos): return card
        return None

    def opponent_monster_at(self, pos):
        for index, card in enumerate(self.engine.opponent.monsters):
            rect = self.layout.monster_rect("opponent", index)
            if card and rect.collidepoint(pos): return card
        return None

    def opponent_monster_rect(self, card):
        index = self.engine.opponent.monsters.index(card)
        return self.layout.monster_rect("opponent", index)

    def player_set_at(self, pos):
        for index, card in enumerate(self.engine.player.spells):
            rect = self.layout.spell_rect("player", index)
            if card and not card.face_up and rect.collidepoint(pos): return card
        return None

    def update_hover(self, pos):
        self.hover_procedure = None
        self.hover_hand, self.hover_hand_rect = self.hand_card_at(pos)
        self.hover_attacker = self.player_monster_at(pos) if self.engine.phase == "BATTLE" else None
        self.hover_target = self.opponent_monster_at(pos) if self.engine.phase == "BATTLE" else None
        self.hover_set = self.player_set_at(pos)
        if self.engine.pending_procedure:
            if self.hover_hand in self.engine.pending_procedure["candidates"]: self.hover_procedure = self.hover_hand
            else:
                candidate = self.player_monster_at(pos)
                self.hover_procedure = candidate if candidate in self.engine.pending_procedure["candidates"] else None
        if self.engine.pending_discard is self.engine.player and self.question and self.question.get("stage") == "choose_card":
            return
        if self.hover_hand and self.hover_hand is not self.action_mode_card:
            self.action_mode = "summon" if self.hover_hand.card.kind not in ["spell", "field"] else "activate"
            self.action_mode_card = self.hover_hand

    def sync_notification(self):
        notification = self.engine.pending_notification()
        if self.question and self.question.get("notification_id"):
            current = next((item for item in self.engine.notifications if item.notification_id == self.question["notification_id"]), None)
            if not current or current.status != "pending": self.question = None
        if self.question or not notification: return
        kind = "procedure" if notification.kind == "choose_cards" and notification.payload.get("kind") == "procedure_materials" else "discard" if notification.kind in ["discard", "choose_cards"] else "chain" if notification.kind == "chain_response" else "trigger_order" if notification.kind == "choose_trigger_order" else "notifier"
        stage = "choose_card" if kind == "procedure" else "choose_response" if kind == "chain" else "choose_order" if kind == "trigger_order" else "confirm" if "no" in notification.options else "await_ok"
        if kind == "trigger_order": self.trigger_selection = list(notification.payload.get("selected_ids", []))
        self.question = {"kind": kind, "stage": stage, "notification_id": notification.notification_id, "text": notification.message, "options": notification.options}

    def question_panel(self):
        if self.question and self.question.get("kind") in ["chain", "trigger_order"]: return pygame.Rect(208, 148, 500, 330)
        return self.layout.question_rect()

    def response_choice_rects(self, candidates):
        panel = self.question_panel()
        visible = list(candidates[:7])
        gap = 66
        width = 56
        start = panel.centerx - ((len(visible) - 1) * gap + width) // 2
        return [pygame.Rect(start + index * gap, panel.y + 76, width, 92) for index in range(len(visible))]

    def trigger_order_choice_rects(self, members):
        panel = self.question_panel()
        return [pygame.Rect(panel.x + 24, panel.y + 66 + index * 29, panel.width - 48, 24) for index in range(len(members))]

    def question_button_rect(self, name):
        if self.question and self.question.get("kind") in ["chain", "trigger_order"]:
            panel = self.question_panel()
            if name == "pass": return pygame.Rect(panel.centerx + 38, panel.bottom - 42, 74, 28)
            if name == "card": return pygame.Rect(panel.centerx - 112, panel.bottom - 42, 74, 28)
            return pygame.Rect(panel.centerx - 32, panel.bottom - 42, 64, 28)
        return self.layout.question_action_rect(name)

    def handle_question(self, pos):
        if not self.question: return
        kind, stage = self.question["kind"], self.question["stage"]
        if kind == "trigger_order" and stage == "choose_order":
            notification = next((item for item in self.engine.notifications if item.notification_id == self.question.get("notification_id") and item.status == "pending"), None)
            if not notification: return
            members = notification.payload.get("members", [])
            for index, rect in enumerate(self.trigger_order_choice_rects(members)):
                if rect.collidepoint(pos):
                    effect_id = members[index].get("effect_id", "")
                    if effect_id in self.trigger_selection: self.trigger_selection.remove(effect_id)
                    else: self.trigger_selection.append(effect_id)
                    return
            if self.question_button_rect("ok").collidepoint(pos):
                result = self.engine.respond_notification(notification.notification_id, "ok", list(self.trigger_selection))
                self.message = result[1]
                if result[0]: self.question = None
            return
        if kind == "chain" and stage == "choose_response":
            notification = next((item for item in self.engine.notifications if item.notification_id == self.question.get("notification_id") and item.status == "pending"), None)
            if not notification: return
            candidates = self.engine.response_candidates(self.engine.chain_priority, self.engine.chain_window.get("trigger", "") if self.engine.chain_window else "")
            rects = self.response_choice_rects(candidates)
            for index, rect in enumerate(rects):
                if rect.collidepoint(pos):
                    result = self.engine.respond_notification(notification.notification_id, "card", candidates[index]["card"].card.id)
                    self.message = result[1]
                    if result[0]: self.question = None
                    return
            if self.question_button_rect("pass").collidepoint(pos) and "pass" in notification.options:
                result = self.engine.respond_notification(notification.notification_id, "pass")
                self.message = result[1]
                if result[0]: self.question = None
            return
        if kind == "notifier" and stage == "confirm":
            if self.layout.question_action_rect("yes").collidepoint(pos):
                success, msg = self.engine.answer_pending_effect("yes")
                self.message = msg or (self.engine.events[-1] if success and self.engine.events else "")
                self.question = None if success else self.question
            elif self.layout.question_action_rect("no").collidepoint(pos):
                success, msg = self.engine.answer_pending_effect("no")
                self.message = msg
                self.question = None if success else self.question
        elif kind == "notifier" and stage == "await_ok":
            if self.layout.question_action_rect("ok").collidepoint(pos):
                notification = next((item for item in self.engine.notifications if item.notification_id == self.question.get("notification_id")), None)
                if notification and "ok" in notification.options: self.engine.respond_notification(notification.notification_id, "ok")
                self.question = None
        elif kind == "chain" and stage == "await_ok":
            if self.layout.question_action_rect("ok").collidepoint(pos):
                notification = next((item for item in self.engine.notifications if item.notification_id == self.question.get("notification_id")), None)
                result = self.engine.respond_notification(notification.notification_id, "pass") if notification else (False, "No chain response is pending.")
                self.message = result[1]
                if result[0]: self.question = None
        elif kind == "surrender" and stage == "confirm":
            if self.layout.question_action_rect("yes").collidepoint(pos):
                self.surrender()
                self.question = None
            elif self.layout.question_action_rect("no").collidepoint(pos):
                self.question = None
        elif kind == "discard" and stage == "await_ok" and self.layout.question_action_rect("ok").collidepoint(pos):
            self.question["stage"] = "choose_card"
        elif kind == "procedure" and stage == "choose_card" and self.layout.question_action_rect("ok").collidepoint(pos):
            notification = next((item for item in self.engine.notifications if item.notification_id == self.question.get("notification_id")), None)
            result = self.engine.respond_notification(notification.notification_id, "ok", list(self.engine.pending_procedure["selected"])) if notification and self.engine.pending_procedure else (False, "No summon procedure is pending.")
            self.message = result[1] or (self.engine.events[-1] if result[0] and self.engine.events else "")
            if result[0]: self.question = None

    def select_hand(self, pos):
        card, _ = self.hand_card_at(pos)
        if card:
            self.engine.selected_hand = card
            self.engine.selected_monster = None
            self.message = f"{card.card.name}: {card.card.description}"

    def select_default_target(self):
        if not self.engine.pending_target:
            self.message = "No targeted effect is waiting."
            return
        targets = self.engine.legal_targets(self.engine.pending_target["card"])
        if targets:
            success, msg = self.engine.select_target(targets[0])
            self.message = self.engine.events[-1] if success else msg
        else:
            self.message = "No legal target exists."

    def select_monster(self, pos):
        card = self.player_monster_at(pos)
        if card:
            self.engine.selected_monster = card
            self.engine.selected_hand = None
            self.message = f"{card.card.name} | ATK {card.atk} | DEF {card.defense}"

    def do_action(self, action):
        if action == "summon" and self.engine.selected_hand:
            card = self.engine.selected_hand
            if card.card.summon_method == "fusion":
                success, msg = self.engine.fusion_summon(card)
            elif card.card.summon_method == "ritual":
                success, msg = self.engine.ritual_summon(card)
            else: success, msg = self.engine.summon(card)
        elif action == "set" and self.engine.selected_hand: success, msg = self.engine.set_card(self.engine.selected_hand)
        elif action == "activate" and self.engine.selected_hand: success, msg = self.engine.activate(self.engine.selected_hand)
        elif action == "attack" and self.engine.selected_monster: success, msg = self.engine.attack(self.engine.selected_monster, self.hover_target)
        elif action == "trap" and self.engine.pending_trap: success, msg = self.engine.activate_trap(self.engine.pending_trap["trap"])
        elif action == "discard" and self.engine.selected_hand: success, msg = self.engine.discard(self.engine.selected_hand)
        else: success, msg = False, "Select a compatible card first."
        if not success: self.message = msg or "That action is not available."
        else: self.message = self.engine.events[-1]
        self.engine.selected_hand = None
        self.engine.selected_monster = None

    def next_phase(self):
        self.engine.advance()
        self.message = self.engine.events[-1]

    def jump_to_phase(self, target_index):
        if target_index <= self.engine.phase_index: return
        while self.engine.phase_index < target_index and not self.engine.finished:
            self.engine.advance()
        self.message = self.engine.events[-1]

    def surrender(self):
        self.engine.finish(self.engine.opponent, "surrender")

    def start_reaction(self, record):
        selection = ReactionSelection(**record["selection"])
        self.reaction_player.start(selection)
        enabled = bool(self.app.store.save_data.get("vocals", True) and self.app.store.save_data.get("sfx", True))
        if selection.audio: self.app.assets.play_reaction_audio(selection.audio, enabled, 0.8)

    def update(self, dt):
        super().update(dt)
        if self.spectator:
            self.app.store.advance_world(dt)
            session = self.app.store._world_session(self.watched_battle)
            if session: self.engine = session
            if len(self.engine.reaction_events) > self.reaction_seen:
                record = self.engine.reaction_events[-1]
                self.start_reaction(record)
                self.reaction_seen = len(self.engine.reaction_events)
            self.reaction_player.update(dt)
            return
        if self.engine.pending_discard is self.engine.player and self.question is None:
            self.question = {"kind": "discard", "stage": "await_ok"}
        self.sync_notification()
        if self.engine.chain_window:
            if self.engine.chain_priority is self.engine.opponent and not self.engine.finished:
                self.ai_timer += dt
                if self.ai_timer > 0.6:
                    self.ai_timer = 0
                    self.engine.ai_chain_step()
        elif self.engine.active is self.engine.opponent and not self.engine.finished:
            self.ai_timer += dt
            if self.ai_timer > 0.6:
                self.ai_timer = 0
                self.engine.ai_step()
        if len(self.engine.reaction_events) > self.reaction_seen:
            record = self.engine.reaction_events[-1]
            self.start_reaction(record)
            self.reaction_seen = len(self.engine.reaction_events)
        self.reaction_player.update(dt)
        if self.engine.finished and self.stage == "battle":
            if self.place_reserved:
                self.app.store.release_place(self.place_id)
                self.place_reserved = False
            self.stage = "post"
            self.app.store.world.setdefault("simulation_events", []).append({"type": "duel_completed", "winner": self.engine.winner.character.id if self.engine.winner else "draw", "reason": self.engine.reason, "time": time.time()})
            self.app.store.save()

    def draw(self, surface):
        self.draw_duel_backdrop(surface)
        self.draw_phase_rail(surface)
        self.draw_opponent_hand(surface)
        self.draw_board(surface)
        self.draw_duel_header(surface)
        if self.spectator:
            draw_text(surface, "LIVE HOUSE POV  |  " + self.engine.player.character.name.upper(), (400, 74), self.app.assets.font(10, True), COLORS["gold"], "center")
        self.draw_reaction(surface)
        self.draw_hand(surface)
        self.draw_interactions(surface)
        self.draw_hover_cloud(surface)
        self.draw_question(surface)
        self.draw_card_list_popup(surface)
        if self.engine.finished: self.draw_result(surface)

    def draw_duel_backdrop(self, surface):
        ground = self.app.assets.role_image("place_ground", (W, H)) or self.app.assets.role_image("duel_environment", (W, H))
        if ground: ui_blit(surface, ground, (0, 0))
        else:
            place = self.app.store.places.get(self.place_id)
            image = self.app.assets.image(place.background, (W, H)) if place and place.background else None
            if image: ui_blit(surface, image, (0, 0))
        table = self.app.assets.role_image("table_frame", (646, 564)) or self.app.assets.image("table_frame_cycle12", (646, 564))
        frame = self.app.assets.role_image("duel_frame", (552, 480)) or self.app.assets.image("duel_frame_cycle12", (552, 480))
        field_surface = self.app.assets.role_image("field_surface", self.layout.field.size) or self.app.assets.image("field_surface_cycle12", self.layout.field.size)
        ui_blit(surface, table, self.layout.table.topleft)
        ui_blit(surface, frame, self.layout.duel_frame.topleft)
        ui_blit(surface, field_surface, self.layout.field.topleft)

    def draw_reaction(self, surface):
        state = self.reaction_player.state()
        if not state.get("active"): return
        rounded(surface, (286, 78, 228, 42), (232, 218, 173), (126, 112, 73), 7, 1)
        label = state["event"].replace("_", " ").upper()
        source = "PLACEHOLDER" if state["placeholder"] else f"VARIANT {state['variant']}"
        draw_text(surface, f"REACTION  {label}", (400, 91), self.app.assets.font(9, True), COLORS["ink"], "midtop")
        draw_text(surface, source, (400, 106), self.app.assets.font(8), COLORS["muted"], "midtop")
        image_path = state.get("image")
        if image_path and Path(image_path).exists():
            try:
                image = pygame.image.load(image_path).convert_alpha()
                image = pygame.transform.smoothscale(image, (52, 32))
                ui_blit(surface, image, (292, 82))
            except pygame.error:
                pass

    def draw_duel_header(self, surface):
        for side, participant in [("opponent", self.engine.opponent), ("player", self.engine.player)]:
            plaque = self.layout.hud_rect(side)
            pfp = self.layout.pfp_rect(side)
            current = int(participant.hp)
            previous = self.hp_display[side]
            if current != previous:
                self.hp_delta[side] = current - previous
                self.hp_delta_until[side] = self.time + 1.0
                self.hp_display[side] = current
            rounded(surface, plaque, (53, 45, 54), (255, 255, 255), 8, 2)
            ui_draw_line(surface, (255, 255, 255, 255), (plaque.x + 62, plaque.y + 9), (plaque.right - 10, plaque.y + 9), 1)
            source = self.app.assets.images.get(participant.character.portrait) or self.app.assets.images.get("pfp_placeholder")
            if source:
                portrait = pygame.transform.smoothscale(source, pfp.size)
                ui_blit(surface, portrait, pfp.topleft)
            draw_text(surface, "LP", (plaque.x + 64, plaque.y + 15), self.app.assets.font(7, True), COLORS["gold"], "topleft")
            draw_text(surface, f"{current:04d}", (plaque.right - 10, plaque.y + 22), self.app.assets.font(19, True), COLORS["white"], "topright")
            if self.hp_delta_until[side] > self.time and self.hp_delta[side]:
                delta = self.hp_delta[side]
                color = COLORS["blue"] if delta > 0 else COLORS["red"]
                draw_text(surface, f"{delta:+d}", (plaque.right - 12, plaque.bottom - 7), self.app.assets.font(9, True), color, "bottomright")

    def draw_phase_rail(self, surface):
        phases = DUEL_PHASES
        x, y, width, height = self.layout.phase_x, 116, 54, 32
        phase_asset = self.app.assets.role_image("phase_rail", (width + 12, len(phases) * 38 + 6))
        if phase_asset:
            ui_blit(surface, phase_asset, (x - 6, y - 6))
        else:
            rounded(surface, (x - 3, y - 6, width + 6, len(phases) * 38 + 6), (220, 207, 166), (119, 105, 72), 8, 1)
        for index, phase_name in enumerate(phases):
            short_label = DUEL_PHASE_ABBREVIATIONS[phase_name]
            rect = self.layout.phase_rect(index)
            active = phase_name == self.engine.phase
            if phase_asset:
                ui_draw_rect(surface, (255, 245, 198) if active else (76, 62, 52), rect, 1, border_radius=5)
                color = (255, 248, 224) if active else (35, 31, 31)
            else:
                rounded(surface, rect, (202, 164, 75) if active else (236, 225, 188), (125, 106, 70), 5, 1)
                color = COLORS["ink"]
            draw_text(surface, short_label, rect.center, self.app.assets.font(10, True), color, "center")

    def draw_hover_cloud(self, surface):
        if self.question: return
        if self.hover_hand and self.hover_hand_rect and self.engine.phase in ["MAIN 1", "MAIN 2"]:
            label = "Set!!" if self.action_mode == "set" else "Activate!" if self.hover_hand.card.kind in ["spell", "field"] else "Summon!"
            self.draw_cloud(surface, self.hover_hand_rect.centerx, self.hover_hand_rect.y - 18, label)
        elif self.engine.phase == "BATTLE" and self.engine.selected_monster and self.hover_target:
            rect = self.opponent_monster_rect(self.hover_target)
            self.draw_cloud(surface, rect.centerx, rect.y - 12, "Attack!")
        elif self.hover_attacker:
            rect = self.monster_rect(self.hover_attacker, True)
            self.draw_cloud(surface, rect.centerx, rect.y - 12, "Attack!")
        elif self.hover_set and self.engine.phase in ["MAIN 1", "MAIN 2"] or self.hover_set and self.engine.pending_trap:
            rect = self.set_rect(self.hover_set)
            self.draw_cloud(surface, rect.centerx, rect.y - 12, "Activate!")

    def draw_cloud(self, surface, center_x, bottom_y, label):
        font = self.app.assets.font(9, True)
        text = font.render(label, True, COLORS["ink"])
        width = max(76, text.get_width() + 22)
        rect = pygame.Rect(center_x - width // 2, bottom_y - 34, width, 28)
        rounded(surface, rect, (255, 247, 213), (118, 94, 58), 11, 2)
        ui_draw_polygon(surface, (255, 247, 213), [(center_x - 7, rect.bottom - 1), (center_x + 7, rect.bottom - 1), (center_x, rect.bottom + 8)])
        ui_draw_line(surface, (118, 94, 58), (center_x, rect.bottom + 7), (center_x, rect.bottom - 1), 1)
        draw_text(surface, label, rect.center, font, COLORS["ink"], "center")

    def draw_question(self, surface):
        if not self.question: return
        panel = self.question_panel()
        rounded(surface, panel, (255, 247, 213), (118, 94, 58), 16, 2)
        kind, stage = self.question["kind"], self.question["stage"]
        if kind == "surrender": text = "Surrender the duel?"
        elif kind == "notifier": text = self.question.get("text", "Resolve the notification.")
        elif kind == "chain": text = "Choose a legal response card or pass."
        elif kind == "trigger_order": text = "Choose the simultaneous-effect order."
        elif stage == "await_ok": text = self.question.get("text", "Discard one card.")
        else: text = self.question.get("text", "Choose a card to discard.")
        draw_text(surface, text, (panel.centerx, panel.y + 27), self.app.assets.font(12, True), COLORS["ink"], "center")
        if kind == "trigger_order" and stage == "choose_order":
            notification = next((item for item in self.engine.notifications if item.notification_id == self.question.get("notification_id") and item.status == "pending"), None)
            members = notification.payload.get("members", []) if notification else []
            required_ids = set(notification.payload.get("required_ids", [])) if notification else set()
            self.question_choice_rects = self.trigger_order_choice_rects(members)
            for index, member in enumerate(members):
                rect = self.question_choice_rects[index]
                effect_id = member.get("effect_id", "")
                selected = effect_id in self.trigger_selection
                fill = (220, 187, 91) if selected else (244, 232, 194)
                rounded(surface, rect, fill, (118, 94, 58), 5, 1)
                role = "REQUIRED" if effect_id in required_ids else "OPTIONAL"
                draw_text(surface, f"{index + 1}. {effect_id}  [{role}]", (rect.x + 9, rect.centery), self.app.assets.font(8, True), COLORS["ink"], "midleft")
                draw_text(surface, "INCLUDED" if selected else "SKIPPED", (rect.right - 9, rect.centery), self.app.assets.font(7, True), COLORS["ink"], "midright")
            rect = self.question_button_rect("ok")
            rounded(surface, rect, (220, 187, 91), (118, 94, 58), 7, 1)
            draw_text(surface, "OK", rect.center, self.app.assets.font(9, True), COLORS["ink"], "center")
        elif kind == "chain" and stage == "choose_response":
            candidates = self.engine.response_candidates(self.engine.chain_priority, self.engine.chain_window.get("trigger", "") if self.engine.chain_window else "")
            self.question_choice_rects = self.response_choice_rects(candidates)
            for index, candidate in enumerate(candidates[:7]):
                rect = self.question_choice_rects[index]
                render_engine_card(surface, rect, candidate["card"].card, self.app.assets, self.app.store.media, True, False, candidate["card"].variant, True)
                draw_text(surface, candidate["card"].card.name[:12], (rect.centerx, rect.bottom + 5), self.app.assets.font(6, True), COLORS["ink"], "midtop")
            if "pass" in self.question.get("options", []):
                rect = self.question_button_rect("pass")
                rounded(surface, rect, (220, 187, 91), (118, 94, 58), 7, 1)
                draw_text(surface, "PASS", rect.center, self.app.assets.font(8, True), COLORS["ink"], "center")
        elif kind in ["surrender", "notifier"] and stage == "confirm":
            for role, rect, label in [("prompt_yes", self.layout.question_action_rect("yes"), "YES"), ("prompt_no", self.layout.question_action_rect("no"), "NO")]:
                image = self.app.assets.role_image(role, rect.size)
                if image: ui_blit(surface, image, rect.topleft)
                else:
                    rounded(surface, rect, (220, 187, 91), (118, 94, 58), 7, 1)
                    draw_text(surface, label, rect.center, self.app.assets.font(9, True), COLORS["ink"], "center")
        elif kind in ["discard", "notifier", "chain"] and stage == "await_ok":
            rect = self.layout.question_action_rect("ok")
            image = self.app.assets.role_image("prompt_ok", rect.size)
            if image: ui_blit(surface, image, rect.topleft)
            else:
                rounded(surface, rect, (220, 187, 91), (118, 94, 58), 7, 1)
                draw_text(surface, "PASS" if kind == "chain" else "OK", rect.center, self.app.assets.font(9, True), COLORS["ink"], "center")

    def draw_card_list_popup(self, surface):
        if not self.card_list_popup: return
        panel = self.layout.card_list_popup_rect()
        rounded(surface, panel, (45, 42, 49), (255, 255, 255), 12, 2)
        draw_text(surface, self.card_list_popup["label"], (panel.centerx, panel.y + 13), self.app.assets.font(10, True), COLORS["white"], "center")
        cards = self.card_list_popup["cards"]
        visible = cards[:7]
        card_width, card_height, gap = 62, 94, 76
        start_x = panel.centerx - ((len(visible) - 1) * gap + card_width) // 2
        for index, item in enumerate(visible):
            rect = pygame.Rect(start_x + index * gap, panel.y + 32, card_width, card_height)
            render_engine_card(surface, rect, item.card, self.app.assets, self.app.store.media, True, False, item.variant, True)
        if len(cards) > len(visible): draw_text(surface, f"+{len(cards) - len(visible)}", (panel.right - 20, panel.bottom - 14), self.app.assets.font(8, True), COLORS["gold"], "center")

    def draw_interactions(self, surface):
        self.interaction_rects = []
        if not self.interactions_open: return
        panel = self.layout.interaction_rect()
        rounded(surface, panel, (220, 207, 166), (119, 105, 72), 8, 2)
        draw_text(surface, "PFP INTERACTIONS", (panel.centerx, panel.y + 12), self.app.assets.font(9, True), COLORS["ink"], "center")
        for index, action in enumerate(["thank", "taunt", "beg", "flirt", "insult", "apologize"]):
            rect = pygame.Rect(panel.x + 8 + (index % 2) * 94, panel.y + 34 + (index // 2) * 28, 86, 22)
            self.interaction_rects.append((rect, action))
            rounded(surface, rect, (236, 225, 188), (119, 105, 72), 5, 1)
            draw_text(surface, action.upper(), rect.center, self.app.assets.font(8, True), COLORS["ink"], "center")

    def draw_slot_guides(self, surface):
        l = self.layout
        for side in ["opponent", "player"]:
            for index in range(5):
                for rect in [l.spell_rect(side, index), l.monster_rect(side, index)]:
                    guide = pygame.Surface(rect.size, pygame.SRCALPHA)
                    ui_draw_rect(guide, (255, 255, 255, 64), guide.get_rect(), 2, border_radius=5)
                    ui_blit(surface, guide, rect.topleft)
        divider = pygame.Surface((l.field.width - 12, 4), pygame.SRCALPHA)
        divider.fill((255, 255, 255, 76))
        ui_blit(surface, divider, (l.field.x + 6, l.field.y + 200))

    def fusion_cards(self, side):
        duelist = self.engine.opponent if side == "opponent" else self.engine.player
        return [item for item in duelist.deck if item.card.summon_method == "fusion"]

    def open_card_list(self, label, cards):
        self.card_list_popup = {"label": label, "cards": list(cards or [])}

    def draw_board(self, surface):
        l = self.layout
        self.draw_slot_guides(surface)
        opponent_fusion = self.fusion_cards("opponent")
        player_fusion = self.fusion_cards("player")
        self.draw_pile(surface, "FUSION", opponent_fusion, l.side_well_rect("opponent", "extra"), True, 180)
        self.draw_pile(surface, "", [], l.side_well_rect("opponent", "field"), False, 180, False)
        self.draw_pile(surface, "DECK", self.engine.opponent.deck, l.side_well_rect("opponent", "deck"), True, 180)
        self.draw_pile(surface, "GY", self.engine.opponent.graveyard, l.side_well_rect("opponent", "graveyard"), False, 180)
        self.draw_banish_marker(surface, l.side_well_rect("opponent", "banished"), len(self.engine.opponent.banished), True)
        self.draw_pile(surface, "FUSION", player_fusion, l.side_well_rect("player", "extra"), True, 0)
        self.draw_pile(surface, "", [self.engine.field_card] if self.engine.field_card else [], l.side_well_rect("player", "field"), False, 0, False)
        self.draw_pile(surface, "DECK", self.engine.player.deck, l.side_well_rect("player", "deck"), True, 0)
        self.draw_pile(surface, "GY", self.engine.player.graveyard, l.side_well_rect("player", "graveyard"), False, 0)
        self.draw_banish_marker(surface, l.side_well_rect("player", "banished"), len(self.engine.player.banished), False)
        for index, card in enumerate(self.engine.opponent.monsters): self.draw_zone_card(surface, card, l.monster_rect("opponent", index), False)
        for index, card in enumerate(self.engine.player.monsters): self.draw_zone_card(surface, card, l.monster_rect("player", index), True)
        for index, card in enumerate(self.engine.opponent.spells): self.draw_zone_card(surface, card, l.spell_rect("opponent", index), False)
        for index, card in enumerate(self.engine.player.spells): self.draw_zone_card(surface, card, l.spell_rect("player", index), True)

    def pile_card_rect(self, rect, index, rotation):
        rect = pygame.Rect(rect)
        dx = index * 2
        dy = -index if rotation == 0 else index
        return pygame.Rect(rect.x + dx, rect.y + dy, rect.width, rect.height)

    def draw_pile_label(self, surface, label, count, rect, rotation):
        font = self.app.assets.font(6, True)
        text = font.render(f"{label[:6]} {count}", True, COLORS["white"])
        label_y = min(rect.bottom + 5, H - 9)
        target = text.get_rect(center=(rect.centerx, label_y))
        ui_blit(surface, text, target)

    def draw_banish_marker(self, surface, rect, count, opponent):
        rect = pygame.Rect(rect)
        direction = -1 if opponent else 1
        start = (rect.centerx - direction * 13, rect.centery)
        end = (rect.centerx + direction * 13, rect.centery)
        ui_draw_line(surface, (255, 255, 255, 180), start, end, 2)
        ui_draw_polygon(surface, (255, 255, 255, 210), [end, (end[0] - direction * 7, end[1] - 5), (end[0] - direction * 7, end[1] + 5)])
        draw_text(surface, str(count), (rect.centerx, rect.bottom + 5 if not opponent else rect.y - 5), self.app.assets.font(8, True), COLORS["white"], "center")

    def draw_pile(self, surface, label, cards, rect, face_down, rotation=0, show_label=True):
        rect = pygame.Rect(rect)
        cards = list(cards or [])
        layers = min(8, (len(cards) + 9) // 10)
        if face_down: layers = max(1, layers)
        for index in range(layers):
            target = self.pile_card_rect(rect, index, rotation)
            if face_down:
                image = self.app.assets.image("card_back")
                if image:
                    if rotation: image = pygame.transform.rotate(image, rotation)
                    blit_aspect(surface, image, target)
            elif cards:
                card = cards[-1 - index]
                card_surface = pygame.Surface(target.size, pygame.SRCALPHA)
                render_engine_card(card_surface, card_surface.get_rect(), card.card, self.app.assets, self.app.store.media, True, False, card.variant, False)
                if rotation: card_surface = pygame.transform.rotate(card_surface, rotation)
                ui_blit(surface, card_surface, target.topleft)
            else:
                overlay = pygame.Surface(target.size, pygame.SRCALPHA)
                overlay.fill((54, 75, 51, 84))
                ui_blit(surface, overlay, target.topleft)
        if show_label and (cards or face_down): self.draw_pile_label(surface, label, len(cards), rect, rotation)

    def draw_opponent_hand(self, surface):
        hand_count = len(self.engine.opponent.hand)
        for index in range(hand_count):
            rect = self.layout.hand_rect("opponent", index, hand_count)
            self.draw_zone_card_back(surface, rect, 180)

    def draw_zone_card_back(self, surface, rect, rotation=0):
        image = self.app.assets.image("card_back")
        if image and rotation: image = pygame.transform.rotate(image, rotation)
        if image: blit_aspect(surface, image, rect)

    def zone_display_rect(self, card, rect):
        rect = pygame.Rect(rect)
        monster_kind = card.card.kind in ["normal", "effect", "fusion", "ritual", "legendary"]
        if not card.face_up and monster_kind:
            return pygame.Rect(rect.centerx - rect.height // 2, rect.centery - rect.width // 2, rect.height, rect.width)
        return rect

    def draw_card_stats(self, surface, card, rect, owner):
        font = self.app.assets.font(6, True)
        attack = self.engine.effective_atk(card, owner)
        attack_color = COLORS["blue"] if attack > card.card.atk else COLORS["red"] if attack < card.card.atk else COLORS["white"]
        attack_text = font.render(str(attack), True, attack_color)
        divider = font.render(" / ", True, COLORS["white"])
        defense = card.defense
        defense_color = COLORS["blue"] if defense > card.card.defense else COLORS["red"] if defense < card.card.defense else COLORS["white"]
        defense_text = font.render(str(defense), True, defense_color)
        width = attack_text.get_width() + divider.get_width() + defense_text.get_width()
        x = rect.centerx - width // 2
        y = rect.bottom + 2
        ui_blit(surface, attack_text, (x, y))
        x += attack_text.get_width()
        ui_blit(surface, divider, (x, y))
        x += divider.get_width()
        ui_blit(surface, defense_text, (x, y))

    def draw_zone_card(self, surface, card, rect, own):
        rect = pygame.Rect(rect)
        if not card: return
        display_rect = self.zone_display_rect(card, rect)
        monster_kind = card.card.kind in ["normal", "effect", "fusion", "ritual", "legendary"]
        face_down = not card.face_up
        show_stats = monster_kind and (own or not face_down)
        stat_height = 14 if show_stats and own else 0
        card_surface = pygame.Surface((display_rect.width, display_rect.height + stat_height), pygame.SRCALPHA)
        card_rect = pygame.Rect(0, 0, display_rect.width, display_rect.height)
        render_engine_card(card_surface, card_rect, card.card, self.app.assets, self.app.store.media, not face_down, face_down, card.variant, False, face_down and monster_kind)
        owner = self.engine.player if own else self.engine.opponent
        if show_stats and own: self.draw_card_stats(card_surface, card, card_rect, owner)
        if not own: card_surface = pygame.transform.rotate(card_surface, 180)
        ui_blit(surface, card_surface, display_rect.topleft)
        if show_stats and not own: self.draw_card_stats(surface, card, display_rect, owner)
        if card is self.engine.selected_monster or card is self.hover_target:
            highlight = pygame.Surface(rect.size, pygame.SRCALPHA)
            highlight.fill((255, 224, 119, 72))
            ui_blit(surface, highlight, rect.topleft)
            ui_draw_rect(surface, COLORS["gold"], rect.inflate(5, 5), 3, border_radius=7)

    def monster_rect(self, card, own):
        roster = self.engine.player.monsters if own else self.engine.opponent.monsters
        index = roster.index(card)
        return self.layout.monster_rect("player" if own else "opponent", index)

    def set_rect(self, card):
        index = self.engine.player.spells.index(card)
        return self.layout.spell_rect("player", index)

    def draw_hand(self, surface):
        hand = self.engine.player.hand
        for index, card in enumerate(hand):
            selected = card is self.engine.selected_hand
            rect = self.layout.hand_rect("player", index, len(hand), selected, card is self.hover_hand)
            if selected: ui_draw_rect(surface, COLORS["gold"], rect.inflate(5, 5), border_radius=7)
            render_engine_card(surface, rect, card.card, self.app.assets, self.app.store.media, True, False, card.variant, True)

    def draw_mini_zone(self, surface, card, pos, own):
        if card: self.draw_zone_card(surface, card, pygame.Rect(pos[0], pos[1], *self.layout.spell_card_size), own)

    def draw_result(self, surface):
        overlay = ui_surface((W, H), pygame.SRCALPHA)
        overlay.fill((247, 227, 177, 75))
        ui_blit(surface, overlay, (0, 0))
        rounded(surface, (180, 175, 440, 205), COLORS["panel"], COLORS["gold"], 12, 2)
        title = "DRAW" if self.engine.winner is None else f"{self.engine.winner.name} WINS"
        color = COLORS["gold"] if self.engine.winner is None else COLORS["cyan"] if self.engine.winner is self.engine.player else COLORS["red"]
        draw_text(surface, "DUEL COMPLETE", (400, 210), self.app.assets.font(24, True), COLORS["gold"], "center")
        draw_text(surface, title, (400, 255), self.app.assets.font(25, True), color, "center")
        draw_text(surface, f"Resolution: {self.engine.reason}", (400, 293), self.app.assets.font(13), COLORS["cream"], "center")
        reward = self.app.store.cards[self.engine.transferred_card].name if self.engine.transferred_card in self.app.store.cards else "No card transfer in a draw"
        draw_text(surface, "Card transfer: " + reward, (400, 316), self.app.assets.font(12), COLORS["gold"])
        draw_text(surface, "Press Escape to return to Battle", (400, 347), self.app.assets.font(12), COLORS["muted"], "center")


class CardsScene(Scene):
    def enter(self):
        self.buttons = [Button((55, 145, 210, 46), "VIEW LIBRARY", lambda: self.app.push(LibraryScene(self.app)), COLORS["cyan"]), Button((55, 205, 210, 46), "DECK WORKSHOP", lambda: self.app.push(DeckScene(self.app)), COLORS["gold"]), Button((55, 265, 210, 46), "CARD MAKER", lambda: self.app.push(CardMakerScene(self.app)), COLORS["violet"]), Button((55, 325, 210, 46), "LOGIC MANAGER", lambda: self.app.push(LogicManagerScene(self.app)), COLORS["green"]), Button((55, 385, 210, 46), "TRADING", lambda: self.app.push(TradingScene(self.app)), COLORS["orange"]), Button((55, 445, 210, 46), "IMPORT / EXPORT", lambda: self.app.push(ImportExportScene(self.app)), COLORS["muted"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CARDS", (36, 30), self.app.assets.font(30, True), COLORS["cyan"])
        draw_text(surface, "Cards are data, images, effects, ownership, and history. The files stay editable.", (38, 68), self.app.assets.font(14), COLORS["muted"])
        self.draw_panel(surface, (320, 122, 420, 356), "PLAYGROUND CARD SYSTEM", COLORS["gold"])
        draw_text(surface, "LIBRARY", (350, 172), self.app.assets.font(16, True), COLORS["cyan"])
        draw_text(surface, f"{len(self.app.store.cards)} cards registered", (350, 198), self.app.assets.font(13), COLORS["cream"])
        draw_text(surface, "DECKS", (350, 244), self.app.assets.font(16, True), COLORS["gold"])
        draw_text(surface, f"{len(self.app.store.decks)} named decks in the world", (350, 270), self.app.assets.font(13), COLORS["cream"])
        draw_text(surface, "EFFECTS", (350, 316), self.app.assets.font(16, True), COLORS["green"])
        draw_text(surface, f"{sum(len(card.effects) for card in self.app.store.cards.values())} starter effects", (350, 342), self.app.assets.font(13), COLORS["cream"])
        draw_text(surface, "CONTENT PATH", (350, 388), self.app.assets.font(16, True), COLORS["violet"])
        draw_text(surface, "data/cards/ and data/logic/", (350, 414), self.app.assets.font(13), COLORS["cream"])
        self.draw_buttons(surface, 13)


class EffectDescriber:
    phrases = {"damage": "deal {amount} damage", "heal": "restore {amount} health", "draw": "draw {amount} card(s)", "boost": "increase this card by {amount} ATK"}

    @classmethod
    def describe(cls, card):
        if not card.effects: return card.description
        parts = []
        for effect in card.effects:
            template = cls.phrases.get(effect.get("action"), effect.get("action", "perform an action") + " {amount}")
            parts.append(template.format(amount=effect.get("amount", 0)))
        return "When " + ", then ".join(parts) + "."


class LibraryScene(Scene):
    def enter(self):
        self.page = 0
        self.card_rects = []
        self.buttons = [Button((650, 530, 110, 38), "BACK", lambda: self.app.pop())]

    def known_cards(self):
        player = self.app.store.characters[self.app.store.role_config()["player_character"]]
        deck = self.app.store.decks.get(player.deck_id, {})
        return set(player.library_cards) | set(deck.get("cards", []))

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RIGHT: self.page += 1
            if event.key == pygame.K_LEFT: self.page = max(0, self.page - 1)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, card_id in self.card_rects:
                if rect.collidepoint(event.pos):
                    self.app.push(CardDetailScene(self.app, card_id))
                    return

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CARD LIBRARY", (34, 28), self.app.assets.font(28, True), COLORS["cyan"])
        draw_text(surface, "Owned cards are face-up. Unknown cards can remain covered until discovered in play.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        cards = list(self.app.store.cards.values())
        visible = cards[self.page * 6:self.page * 6 + 6]
        known = self.known_cards()
        self.card_rects = []
        for index, card in enumerate(visible):
            x = 36 + (index % 3) * 245
            y = 110 + (index // 3) * 205
            rect = pygame.Rect(x, y, 210, 175)
            self.card_rects.append((rect, card.id))
            self.draw_library_card(surface, card, x, y, card.id in known)
        draw_text(surface, "Click a card to inspect its authored description and effect data.", (400, 530), self.app.assets.font(11), COLORS["gold"], "center")
        draw_text(surface, f"Page {self.page + 1} / {max(1, math.ceil(len(cards) / 6))}   Left / Right", (400, 576), self.app.assets.font(12), COLORS["muted"], "center")
        self.draw_buttons(surface, 12)

    def draw_library_card(self, surface, card, x, y, known):
        rounded(surface, (x, y, 210, 175), COLORS["panel"], COLORS["line"] if known else COLORS["muted"], 9, 2)
        if not known:
            blit_aspect(surface, self.app.assets.image("card_back"), pygame.Rect(x + 8, y + 8, 194, 106))
            draw_text(surface, "UNKNOWN CARD", (x + 105, y + 128), self.app.assets.font(13, True), COLORS["gold"], "center")
            draw_text(surface, "Not owned or studied", (x + 105, y + 151), self.app.assets.font(11), COLORS["muted"], "center")
            return
        render_engine_card(surface, (x + 8, y + 8, 194, 159), card, self.app.assets, self.app.store.media, True, False, card.art_variant, False)


class CardDetailScene(Scene):
    def __init__(self, app, card_id):
        super().__init__(app)
        self.card = app.store.cards[card_id]
        player = app.store.characters[app.store.role_config()["player_character"]]
        deck = app.store.decks.get(player.deck_id, {})
        self.known = self.card.id in set(player.library_cards) | set(deck.get("cards", []))

    def enter(self):
        self.buttons = [Button((70, 470, 230, 46), "RUN EFFECT EXAMPLE", lambda: self.app.push(CardSimulationScene(self.app, self.card.id))), Button((315, 470, 170, 46), "MODIFY CARD", lambda: self.app.push(CardMakerScene(self.app, self.card.id))), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop())]

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CARD DETAIL", (34, 28), self.app.assets.font(28, True), COLORS["cyan"])
        draw_text(surface, "The engine generates a readable explanation from structured effect data.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        rounded(surface, (60, 122, 240, 280), (22, 35, 67), COLORS["gold"] if self.card.legendary and self.known else COLORS["line"], 12, 3)
        if not self.known:
            blit_aspect(surface, self.app.assets.image("card_back"), pygame.Rect(75, 139, 210, 240))
            draw_text(surface, "UNKNOWN CARD", (180, 306), self.app.assets.font(16, True), COLORS["gold"], "center")
            self.draw_panel(surface, (350, 122, 400, 280), "CARD JOURNAL", COLORS["muted"])
            draw_text(surface, "Not owned or studied yet.", (550, 230), self.app.assets.font(18, True), COLORS["cream"], "center")
            draw_text(surface, "Play against it, study it, or receive it to reveal details.", (550, 274), self.app.assets.font(12), COLORS["muted"], "center")
            self.draw_buttons(surface, 12)
            return
        render_engine_card(surface, (60, 122, 240, 280), self.card, self.app.assets, self.app.store.media, True, False, self.card.art_variant, False)
        self.draw_panel(surface, (350, 122, 400, 280), "PARSED EFFECT", COLORS["green"])
        for index, line in enumerate(wrap(self.app.assets.font(16), EffectDescriber.describe(self.card), 350)):
            draw_text(surface, line, (375, 185 + index * 26), self.app.assets.font(16), COLORS["cream"])
        draw_text(surface, "Assigned graph: " + (self.card.logic_graph or "none"), (375, 310), self.app.assets.font(13), COLORS["violet"])
        draw_text(surface, self.card.description, (375, 350), self.app.assets.font(12), COLORS["muted"])
        self.draw_buttons(surface, 12)


class CardSimulationScene(Scene):
    def __init__(self, app, card_id):
        super().__init__(app)
        self.card_id = card_id
        self.card = app.store.cards[card_id]
        roles = app.store.role_config()
        self.engine = DuelEngine(app.store, roles["player_character"], roles["default_opponent_character"], roles["default_place"], False)
        self.engine.match_recorded = True
        self.demo_card = CardInstance(self.card, "example")
        self.engine.player.hand.insert(0, self.demo_card)
        self.elapsed = 0.0
        self.steps = 0

    def enter(self):
        self.buttons = [Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def update(self, dt):
        self.elapsed += dt
        if self.elapsed < 0.55 or self.engine.finished: return
        self.elapsed = 0.0
        self.steps += 1
        if self.engine.active is self.engine.player:
            if self.engine.phase in ["MAIN 1", "MAIN 2"] and self.demo_card in self.engine.player.hand:
                if self.card.kind in ["normal", "effect", "legendary"]: self.engine.summon(self.demo_card)
                elif self.card.kind in ["spell", "field"]: self.engine.activate(self.demo_card)
                else: self.engine.set_card(self.demo_card)
            self.engine.advance()
        else:
            self.engine.ai_step()
        if self.steps >= 30 and not self.engine.finished: self.engine.finish(None, "example complete")

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        self.draw_background(surface, "duel_field", 155)
        draw_text(surface, "CARD EFFECT EXAMPLE", (34, 28), self.app.assets.font(28, True), COLORS["gold"])
        draw_text(surface, f"Two CPU duel walkthrough: {self.card.name}", (36, 65), self.app.assets.font(13), COLORS["cream"])
        self.draw_panel(surface, (42, 104, 716, 382), "LIVE EFFECT OBSERVATION", COLORS["gold"])
        draw_text(surface, f"{self.engine.player.name}: {self.engine.player.hp} HP", (72, 158), self.app.assets.font(17, True), COLORS["cyan"])
        draw_text(surface, f"{self.engine.opponent.name}: {self.engine.opponent.hp} HP", (520, 158), self.app.assets.font(17, True), COLORS["red"])
        draw_text(surface, f"TURN {self.engine.turn}  |  {self.engine.phase}", (400, 198), self.app.assets.font(15, True), COLORS["gold"], "center")
        render_engine_card(surface, (72, 238, 190, 278), self.card, self.app.assets, self.app.store.media, True, False, self.card.art_variant, False)
        draw_text(surface, EffectDescriber.describe(self.card), (292, 252), self.app.assets.font(12), COLORS["cream"])
        for index, event in enumerate(self.engine.events[-8:]): draw_text(surface, event, (292, 292 + index * 24), self.app.assets.font(11), COLORS["muted"])
        draw_text(surface, "This is a player-facing example feature, not a developer test or replay.", (400, 505), self.app.assets.font(11), COLORS["gold"], "center")
        self.draw_buttons(surface, 12)
        self.app.draw_notice(surface)


class DeckScene(Scene):
    def enter(self):
        self.deck_rects = []
        self.buttons = [Button((430, 530, 190, 38), "CREATE PRESET", lambda: self.create_preset(), COLORS["gold"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, deck_id in self.deck_rects:
                if rect.collidepoint(event.pos): self.app.push(DeckEditorScene(self.app, deck_id)); return

    def create_preset(self):
        if len(self.app.store.decks) >= 10: self.app.notify("The ten preset-deck limit has been reached."); return
        deck_id = "deck_" + str(int(time.time() * 1000))
        name = "Preset Deck " + str(len(self.app.store.decks) + 1)
        cards = DeckRules.normalized(list(self.app.store.cards), self.app.store.cards)
        self.app.store.decks[deck_id] = {"name": name, "cards": cards, "media_folder": self.app.store.scaffold_entity("decks", deck_id, name)}
        self.app.store.save()
        self.app.notify("Preset deck created with a legal card pool.")
        self.enter()

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "DECK WORKSHOP", (34, 28), self.app.assets.font(28, True), COLORS["gold"])
        draw_text(surface, "Create, inspect, and modify up to ten named decks with the shared legality rules.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (36, 112, 728, 370), "DECKS", COLORS["gold"])
        self.deck_rects = []
        for index, (deck_id, deck) in enumerate(self.app.store.decks.items()):
            y = 165 + index * 54
            if y > 452: break
            rect = pygame.Rect(60, y, 680, 42)
            self.deck_rects.append((rect, deck_id))
            rounded(surface, rect, (16, 28, 58), COLORS["gold"], 6, 1)
            draw_text(surface, deck.get("name", deck_id), (78, y + 13), self.app.assets.font(14, True), COLORS["cream"])
            draw_text(surface, f"{len(deck.get('cards', []))} cards | {DeckRules.summary(deck.get('cards', []), self.app.store.cards)} | click to edit", (340, y + 13), self.app.assets.font(10), COLORS["muted"])
        self.draw_buttons(surface, 12)
        self.app.draw_notice(surface)


class DeckEditorScene(Scene):
    def __init__(self, app, deck_id):
        super().__init__(app)
        self.deck_id = deck_id
        self.card_buttons = []
        self.name = None

    def enter(self):
        deck = self.app.store.decks.get(self.deck_id, {})
        self.name = TextInput((40, 76, 300, 32), deck.get("name", self.deck_id))
        self.card_buttons = []
        self.buttons = [Button((360, 76, 130, 32), "SAVE NAME", lambda: self.save_name(), COLORS["cyan"]), Button((500, 530, 120, 38), "NORMALIZE", lambda: self.normalize(), COLORS["gold"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def save_name(self):
        if self.name.value.strip(): self.app.store.decks[self.deck_id]["name"] = self.name.value.strip(); self.app.store.save(); self.app.notify("Deck name saved.")

    def normalize(self):
        deck = self.app.store.decks[self.deck_id]
        deck["cards"] = DeckRules.normalized(deck.get("cards", []), self.app.store.cards)
        self.app.store.save()
        self.app.notify("Deck normalized with authored cards and copy limits; no runtime padding was added.")
        self.enter()

    def add_card(self, card_id):
        deck = self.app.store.decks[self.deck_id]
        candidate = list(deck.get("cards", [])) + [card_id]
        errors = DeckRules.validate(candidate, self.app.store.cards)
        main_count = len(DeckRules.partition(candidate, self.app.store.cards)[0])
        if main_count > DeckRules.maximum or any("exceeds" in error for error in errors): self.app.notify("That card cannot be added under the deck copy or size rules."); return
        deck["cards"] = candidate; self.app.store.save(); self.enter()

    def remove_card(self, card_id):
        deck = self.app.store.decks[self.deck_id]
        if card_id in deck.get("cards", []): deck["cards"].remove(card_id); self.app.store.save(); self.enter()

    def handle(self, event):
        self.name.handle(event)
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, action, card_id in self.card_buttons:
                if rect.collidepoint(event.pos): action(card_id); return

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        deck = self.app.store.decks[self.deck_id]
        draw_text(surface, "DECK EDITOR", (34, 28), self.app.assets.font(28, True), COLORS["gold"])
        self.name.draw(surface, self.app.assets.font(12), "Deck name")
        draw_text(surface, f"{len(deck.get('cards', []))}/80 cards | {DeckRules.summary(deck.get('cards', []), self.app.store.cards)}", (370, 92), self.app.assets.font(12), COLORS["muted"])
        self.draw_panel(surface, (32, 128, 360, 370), "CURRENT CARDS", COLORS["gold"])
        self.draw_panel(surface, (410, 128, 358, 370), "ADD CARD", COLORS["cyan"])
        self.card_buttons = []
        counts = {}
        for card_id in deck.get("cards", []): counts[card_id] = counts.get(card_id, 0) + 1
        for index, (card_id, count) in enumerate(counts.items()):
            if index >= 11: break
            card = self.app.store.cards.get(card_id)
            if not card: continue
            y = 178 + index * 26
            draw_text(surface, f"{card.name[:18]} x{count}", (52, y), self.app.assets.font(10), COLORS["cream"])
            rect = pygame.Rect(320, y - 5, 48, 22)
            rounded(surface, rect, (22, 38, 77), COLORS["red"], 5, 1)
            draw_text(surface, "-1", rect.center, self.app.assets.font(10, True), COLORS["cream"], "center")
            self.card_buttons.append((rect, self.remove_card, card.id))
        for index, card in enumerate(list(self.app.store.cards.values())[:12]):
            x = 430 + (index % 2) * 166
            y = 178 + (index // 2) * 50
            rect = pygame.Rect(x, y, 152, 36)
            rounded(surface, rect, tuple(card.art_color), COLORS["line"], 5, 1)
            draw_text(surface, "+ " + card.name[:16], rect.center, self.app.assets.font(9, True), COLORS["ink"], "center")
            self.card_buttons.append((rect, self.add_card, card.id))
        self.draw_buttons(surface, 10)
        self.app.draw_notice(surface)


class CardMakerScene(Scene):
    def __init__(self, app, card_id=None):
        super().__init__(app)
        self.card_id = card_id

    def enter(self):
        card = self.app.store.cards.get(self.card_id) if self.card_id else None
        self.name = TextInput((80, 150, 290, 34), card.name if card else "New Card")
        self.art_path = TextInput((80, 210, 290, 34), "")
        self.description = TextInput((80, 270, 640, 34), card.description if card else "A community-created card.")
        self.kind = card.kind if card else "effect"
        self.family = card.family if card else "warrior"
        self.stars = int(card.stars) if card else 4
        self.atk = int(card.atk) if card else 1500
        self.defense = int(card.defense) if card else 1200
        self.logic_graph = card.logic_graph if card else ""
        self.targets = list(card.targets) if card else ["none"]
        self.target_count = int(card.target_count) if card else 0
        self.timing = card.timing if card else "main"
        self.summon_method = card.summon_method if card else "normal"
        self.materials = list(card.materials) if card else []
        self.materials_text = TextInput((80, 365, 640, 34), ", ".join(self.materials))
        self.ritual_cost = int(card.ritual_cost) if card else 0
        self.effects = [dict(raw) for raw in card.effects] if card else []
        self.refresh_buttons()

    def refresh_buttons(self):
        self.buttons = [Button((420, 150, 150, 34), "TYPE: " + self.kind.upper(), lambda: self.cycle_kind(), COLORS["violet"]), Button((590, 150, 150, 34), "FAMILY: " + self.family.upper(), lambda: self.cycle_family(), COLORS["cyan"]), Button((420, 200, 150, 34), "LOGIC: " + (self.logic_graph or "NONE").upper(), lambda: self.cycle_logic(), COLORS["gold"]), Button((590, 200, 150, 34), "TARGET: " + self.targets[0].upper(), lambda: self.cycle_target(), COLORS["green"]), Button((420, 245, 150, 34), "EFFECTS: " + str(len(self.effects)), lambda: self.open_effects(), COLORS["orange"]), Button((80, 340, 110, 34), "STAR +", lambda: self.change("stars", 1)), Button((200, 340, 110, 34), "ATK +", lambda: self.change("atk", 100)), Button((320, 340, 110, 34), "DEF +", lambda: self.change("defense", 100)), Button((440, 340, 150, 34), "TIMING", lambda: self.cycle_timing()), Button((80, 410, 180, 34), "SUMMON MODE", lambda: self.cycle_summon()), Button((280, 410, 180, 34), "TARGET COUNT", lambda: self.cycle_target_count()), Button((80, 470, 240, 38), "SAVE MODIFIED" if self.card_id else "CREATE CARD", lambda: self.save_card(), COLORS["green"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def cycle_kind(self):
        values = ["normal", "effect", "spell", "trap", "field", "fusion", "ritual", "legendary"]
        self.kind = values[(values.index(self.kind) + 1) % len(values)]
        if self.kind == "fusion": self.summon_method, self.materials, self.ritual_cost = "fusion", [], 0
        elif self.kind == "ritual": self.summon_method, self.materials, self.ritual_cost = "ritual", [], 7
        else: self.summon_method, self.materials, self.ritual_cost = "normal", [], 0
        self.materials_text.value = ", ".join(self.materials)
        self.refresh_buttons()

    def open_effects(self): self.app.push(CardEffectsScene(self, self))

    def cycle_family(self):
        values = ["warrior", "aqua", "machine", "fiend", "spell", "dragon", "beast"]
        self.family = values[(values.index(self.family) + 1) % len(values)]
        self.refresh_buttons()

    def cycle_logic(self):
        values = [""] + sorted(self.app.store.logic)
        self.logic_graph = values[(values.index(self.logic_graph) + 1) % len(values)] if self.logic_graph in values else ""
        self.refresh_buttons()

    def cycle_target(self):
        values = [["none"], ["opponent"], ["player"], ["any_monster"]]
        self.targets = values[(values.index(self.targets) + 1) % len(values)] if self.targets in values else ["none"]
        self.target_count = 0 if self.targets == ["none"] else max(1, self.target_count)
        self.refresh_buttons()

    def cycle_timing(self):
        values = ["main", "opponent_attack", "any"]
        self.timing = values[(values.index(self.timing) + 1) % len(values)]
        self.refresh_buttons()

    def cycle_summon(self):
        values = ["normal", "fusion", "ritual"]
        self.summon_method = values[(values.index(self.summon_method) + 1) % len(values)]
        if self.summon_method == "fusion": self.materials, self.ritual_cost = [], 0
        elif self.summon_method == "ritual": self.materials, self.ritual_cost = [], 7
        else: self.materials, self.ritual_cost = [], 0
        self.materials_text.value = ", ".join(self.materials)
        self.refresh_buttons()

    def cycle_target_count(self):
        self.target_count = 0 if self.targets == ["none"] else (self.target_count % 3) + 1
        self.refresh_buttons()

    def change(self, field_name, amount): setattr(self, field_name, clamp(getattr(self, field_name) + amount, 0, 10000)); self.refresh_buttons()

    def save_card(self):
        graph = self.logic_graph
        self.materials = [value.strip() for value in self.materials_text.value.split(",") if value.strip()]
        values = {"name": self.name.value, "kind": self.kind, "stars": self.stars if self.kind in ["normal", "effect", "fusion", "ritual", "legendary"] else 0, "atk": self.atk if self.kind in ["normal", "effect", "fusion", "ritual", "legendary"] else 0, "defense": self.defense if self.kind in ["normal", "effect", "fusion", "ritual", "legendary"] else 0, "family": self.family, "description": self.description.value, "logic_graph": graph, "targets": self.targets, "target_count": self.target_count, "timing": self.timing, "field_effect": {"family": self.family, "atk": 300} if self.kind == "field" else {}, "materials": self.materials, "ritual_cost": self.ritual_cost, "summon_method": self.summon_method, "effects": self.effects}
        errors = self.app.store.validate_card_definition(values["kind"], values["stars"], values["atk"], values["defense"], values["family"], values["description"], values["targets"], values["target_count"], values["timing"], values["materials"], values["ritual_cost"], values["summon_method"], values["effects"])
        if errors: self.app.notify("Card rejected: " + "; ".join(errors[:2])); return
        if self.card_id:
            if not self.app.store.update_card(self.card_id, values): self.app.notify("Card update failed."); return
        else:             self.app.store.create_card(values["name"], values["kind"], values["stars"], values["atk"], values["defense"], values["family"], values["description"], graph, values["targets"], values["target_count"], values["timing"], values["field_effect"], values["materials"], values["ritual_cost"], values["summon_method"], self.art_path.value, values["effects"])

        self.app.store.load()
        self.app.notify("Card saved with its authored data and editable folder structure.")

    def handle(self, event):
        self.name.handle(event); self.art_path.handle(event); self.description.handle(event); self.materials_text.handle(event); super().handle(event)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CARD MAKER", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, "Create or modify a card definition; engine frame and metadata remain separate from user art.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (42, 112, 720, 390), "CARD DEFINITION", COLORS["violet"])
        self.name.draw(surface, self.app.assets.font(12), "Card name")
        self.art_path.draw(surface, self.app.assets.font(12), "User art path, optional")
        self.description.draw(surface, self.app.assets.font(12), "Description")
        draw_text(surface, f"STARS {self.stars} | ATK {self.atk} | DEF {self.defense} | RITUAL COST {self.ritual_cost}", (80, 325), self.app.assets.font(13, True), COLORS["cream"])
        self.materials_text.draw(surface, self.app.assets.font(12), "Fusion material IDs, comma-separated")
        draw_text(surface, "Effects and logic are authored through the card definition and assigned logic graphs.", (80, 445), self.app.assets.font(10), COLORS["gold"])
        self.draw_buttons(surface, 10)
        self.app.draw_notice(surface)


class CardEffectsScene(Scene):
    def __init__(self, owner, card_maker):
        super().__init__(owner.app)
        self.owner = card_maker
        self.card_maker = card_maker

    def enter(self):
        self.effects = self.card_maker.effects
        self.selected_index = None
        self.effect_id = TextInput((46, 132, 310, 32), "effect_1")
        self.trigger = TextInput((46, 190, 310, 32), "on_summon")
        self.condition = TextInput((46, 248, 310, 32), "")
        self.action = TextInput((46, 306, 310, 32), "damage")
        self.amount = TextInput((46, 364, 150, 32), "500")
        self.target = TextInput((206, 364, 150, 32), "source")
        self.count = TextInput((46, 422, 150, 32), "0")
        self.cost_count = TextInput((206, 422, 150, 32), "1")
        self.phase = "any"
        self.cost_kind = "none"
        self.once = ""
        self.speed = 1
        self.optional = False
        self.refresh_buttons()

    def integer(self, value, fallback=0):
        try: return int(str(value).strip())
        except (TypeError, ValueError): return fallback

    def selected_effect(self):
        return self.effects[self.selected_index] if self.selected_index is not None and self.selected_index < len(self.effects) else None

    def load_effect(self, index):
        if index < 0 or index >= len(self.effects): return
        self.selected_index = index
        spec = EffectSpec.from_dict(self.effects[index], "effect_" + str(index + 1))
        self.effect_id.value = spec.effect_id
        self.trigger.value = spec.trigger
        self.condition.value = str(spec.conditions[0]) if spec.conditions else ""
        action = spec.actions[0] if spec.actions else {"name": "damage", "amount": 500, "target": "source"}
        self.action.value = action.get("name", "damage")
        self.amount.value = str(action.get("amount", 500))
        self.target.value = str(action.get("target", "source"))
        self.count.value = str(spec.selector.get("count", 0) if spec.selector else 0)
        self.phase = str(spec.window.get("phase", "any")) if not isinstance(spec.window.get("phase", "any"), list) else str(spec.window.get("phase", ["any"])[0])
        self.once = spec.once
        self.speed = spec.speed
        self.optional = spec.optional
        costs = spec.costs[0] if spec.costs else {}
        self.cost_kind = str(costs.get("kind", "none"))
        self.cost_count.value = str(costs.get("count", costs.get("amount", 1)))
        self.refresh_buttons()

    def new_effect(self):
        self.selected_index = None
        self.effect_id.value = "effect_" + str(len(self.effects) + 1)
        self.trigger.value = "on_summon"
        self.condition.value = ""
        self.action.value = "damage"
        self.amount.value = "500"
        self.target.value = "source"
        self.count.value = "0"
        self.cost_count.value = "1"
        self.phase, self.cost_kind, self.once, self.speed, self.optional = "any", "none", "", 1, False
        self.refresh_buttons()

    def cycle(self, attribute, values):
        current = getattr(self, attribute)
        setattr(self, attribute, values[(values.index(current) + 1) % len(values)] if current in values else values[0])
        self.refresh_buttons()

    def cycle_phase(self): self.cycle("phase", ["any", "draw", "standby", "main", "battle", "end"])
    def cycle_cost(self): self.cycle("cost_kind", ["none", "discard", "tribute", "pay_hp"])
    def cycle_once(self): self.cycle("once", ["", "once", "once_per_turn", "once_per_duel"])
    def cycle_speed(self): self.speed = self.speed % 3 + 1; self.refresh_buttons()
    def toggle_optional(self): self.optional = not self.optional; self.refresh_buttons()

    def effect_payload(self):
        effect_id = self.effect_id.value.strip() or "effect_" + str(len(self.effects) + 1)
        trigger = self.trigger.value.strip() or "manual"
        action = self.action.value.strip() or "damage"
        amount = self.integer(self.amount.value, 0)
        target = self.target.value.strip() or "source"
        count = max(0, self.integer(self.count.value, 0))
        targets = [] if target in ["", "source", "none"] else [target]
        selector = {"target_groups": targets, "count": count} if targets and count else {}
        costs = []
        cost_count = max(1, self.integer(self.cost_count.value, 1))
        if self.cost_kind in ["discard", "tribute"]: costs = [{"kind": self.cost_kind, "count": cost_count, "select": {"side": "self", "zone": "hand" if self.cost_kind == "discard" else "monster", "count": cost_count}}]
        elif self.cost_kind == "pay_hp": costs = [{"kind": "pay_hp", "amount": max(0, amount)}]
        return {"id": effect_id, "trigger": trigger, "window": {"phase": self.phase, "event": trigger}, "when": [self.condition.value.strip()] if self.condition.value.strip() else [], "cost": costs, "select": selector, "targets": targets, "actions": [{"name": action, "amount": amount, "target": target}], "optional": self.optional, "once": self.once, "speed": self.speed, "notify": {"kind": "yes_no", "text": "Activate this effect?", "options": ["yes", "no"]} if self.optional else {}}

    def save_effect(self):
        raw = self.effect_payload()
        errors = self.app.store.validate_effects([raw])
        if errors:
            self.app.notify("Effect rejected: " + "; ".join(errors[:2]))
            return
        if self.selected_index is None: self.effects.append(raw); self.selected_index = len(self.effects) - 1
        else: self.effects[self.selected_index] = raw
        self.card_maker.effects = self.effects
        self.app.notify("Structured effect saved to the card draft.")
        self.load_effect(self.selected_index)

    def delete_effect(self):
        if self.selected_index is None or self.selected_index >= len(self.effects): return
        self.effects.pop(self.selected_index)
        self.card_maker.effects = self.effects
        self.new_effect()

    def apply_and_back(self):
        self.card_maker.effects = self.effects
        self.card_maker.refresh_buttons()
        self.app.pop()

    def refresh_buttons(self):
        self.buttons = [Button((420, 72, 104, 34), "NEW", lambda: self.new_effect(), COLORS["gold"]), Button((532, 72, 118, 34), "SAVE EFFECT", lambda: self.save_effect(), COLORS["green"]), Button((662, 72, 98, 34), "DELETE", lambda: self.delete_effect(), COLORS["red"]), Button((420, 500, 190, 38), "APPLY TO CARD", lambda: self.apply_and_back(), COLORS["violet"]), Button((620, 500, 140, 38), "CANCEL", lambda: self.app.pop(), COLORS["muted"]), Button((420, 132, 150, 32), "PHASE: " + self.phase.upper(), lambda: self.cycle_phase(), COLORS["cyan"]), Button((580, 132, 180, 32), "COST: " + self.cost_kind.upper(), lambda: self.cycle_cost(), COLORS["orange"]), Button((420, 190, 150, 32), "ONCE: " + (self.once.upper() or "NO"), lambda: self.cycle_once(), COLORS["gold"]), Button((580, 190, 180, 32), "SPEED: " + str(self.speed), lambda: self.cycle_speed(), COLORS["cyan"]), Button((420, 248, 150, 32), "OPTIONAL: " + ("YES" if self.optional else "NO"), lambda: self.toggle_optional(), COLORS["green"])]

    def handle(self, event):
        for field_input in [self.effect_id, self.trigger, self.condition, self.action, self.amount, self.target, self.count, self.cost_count]: field_input.handle(event)
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and 42 <= event.pos[0] <= 360 and 118 <= event.pos[1] <= 470:
            index = (event.pos[1] - 118) // 42
            if index < len(self.effects): self.load_effect(index)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CARD EFFECTS EDITOR", (34, 28), self.app.assets.font(28, True), COLORS["orange"])
        draw_text(surface, "Author valid structured effects; each card can contain multiple independent effect records.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (32, 96, 350, 400), "EFFECT FORM", COLORS["orange"])
        self.draw_panel(surface, (402, 96, 368, 390), "EFFECT POLICY", COLORS["cyan"])
        for field_input, label in [(self.effect_id, "Effect ID"), (self.trigger, "Trigger"), (self.condition, "Condition expression"), (self.action, "Action name"), (self.amount, "Amount"), (self.target, "Action target"), (self.count, "Target count"), (self.cost_count, "Cost count / HP")]: field_input.draw(surface, self.app.assets.font(11), label)
        draw_text(surface, "EFFECTS", (52, 108), self.app.assets.font(12, True), COLORS["gold"])
        for index, raw in enumerate(self.effects[:8]):
            y = 130 + index * 42
            color = COLORS["violet"] if index == self.selected_index else COLORS["line"]
            pygame.draw.rect(surface, color, pygame.Rect(42, y, 318, 34), 1)
            spec = EffectSpec.from_dict(raw, "effect_" + str(index + 1))
            draw_text(surface, f"{index + 1}. {spec.effect_id} | {spec.trigger}", (50, y + 9), self.app.assets.font(10, True), COLORS["cream"])
        draw_text(surface, "Action vocabulary", (420, 300), self.app.assets.font(11, True), COLORS["gold"])
        draw_text(surface, ", ".join(sorted(EffectSpec.action_names)), (420, 322), self.app.assets.font(9), COLORS["muted"])
        draw_text(surface, "Costs: discard, tribute, or pay HP. Selectors and conditions are saved as schema data.", (420, 382), self.app.assets.font(10), COLORS["cream"])
        self.draw_buttons(surface, 10)
        self.app.draw_notice(surface)


class LogicManagerScene(Scene):
    def enter(self):
        self.graph_key = next(iter(self.app.store.logic), "")
        self.graph = self.app.store.logic.get(self.graph_key, LogicGraph("New Logic"))
        for node in self.graph.nodes: node.y = max(180, node.y)
        self.selected = None
        self.dragging = False
        self.drag_offset = (0, 0)
        self.buttons = [Button((28, 530, 116, 38), "ADD TRIGGER", lambda: self.add_node("trigger")), Button((152, 530, 126, 38), "ADD CONDITION", lambda: self.add_node("condition")), Button((286, 530, 112, 38), "ADD ACTION", lambda: self.add_node("action")), Button((406, 530, 92, 38), "SAVE", lambda: self.save_graph()), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop())]

    def add_node(self, kind):
        node_id = "n" + str(len(self.graph.nodes) + 1)
        labels = {"trigger": ("WHEN", "on_summon"), "condition": ("IF", "card.family == warrior"), "action": ("DO", "damage 500")}
        label, value = labels[kind]
        x = 62 + (len(self.graph.nodes) % 3) * 230
        y = 190 + (len(self.graph.nodes) // 3) * 145
        inputs = [self.graph.nodes[-1].node_id] if self.graph.nodes else []
        self.graph.nodes.append(LogicNode(node_id, kind, label, value, len(self.graph.nodes) + 1, x, y, inputs))

    def save_graph(self):
        errors = LogicRuntime.validate_graph(self.graph)
        if errors:
            self.app.notify("Logic graph rejected: " + "; ".join(errors[:2]))
            return
        self.app.store.logic[self.graph_key] = self.graph
        self.app.store.save()
        self.app.notify("Logic graph saved with validated levels and connections.")


    def cycle_selected_value(self):
        if not self.selected: return
        values = {
            "trigger": ["on_summon", "on_activate", "on_battle", "on_turn_end"],
            "condition": ["always", "card.family == warrior", "card.kind == spell", "card.family == fiend"],
            "action": ["boost_attack +200", "boost_defense +200", "damage 500", "heal 400", "draw 1", "banish 1", "send_to_graveyard 1", "return_to_hand 1"]
        }
        options = values[self.selected.kind]
        self.selected.value = options[(options.index(self.selected.value) + 1) % len(options)] if self.selected.value in options else options[0]

    def delete_selected(self):
        if not self.selected: return
        deleted = self.selected.node_id
        self.graph.nodes = [node for node in self.graph.nodes if node.node_id != deleted]
        for node in self.graph.nodes: node.inputs = [value for value in node.inputs if value != deleted]
        self.selected = None

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for node in self.graph.nodes:
                if pygame.Rect(node.x, node.y, 180, 94).collidepoint(event.pos):
                    self.selected = node
                    self.dragging = True
                    self.drag_offset = (event.pos[0] - node.x, event.pos[1] - node.y)
                    return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        if event.type == pygame.MOUSEMOTION and self.dragging and self.selected:
            self.selected.x = clamp(event.pos[0] - self.drag_offset[0], 46, 570)
            self.selected.y = clamp(event.pos[1] - self.drag_offset[1], 112, 420)
        if event.type == pygame.KEYDOWN and self.selected:
            if event.key == pygame.K_TAB: self.cycle_selected_value()
            elif event.key == pygame.K_DELETE: self.delete_selected()
            elif event.key == pygame.K_LEFT: self.selected.x = clamp(self.selected.x - 10, 46, 570)
            elif event.key == pygame.K_RIGHT: self.selected.x = clamp(self.selected.x + 10, 46, 570)
            elif event.key == pygame.K_UP: self.selected.y = clamp(self.selected.y - 10, 112, 420)
            elif event.key == pygame.K_DOWN: self.selected.y = clamp(self.selected.y + 10, 112, 420)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "LOGIC MANAGER", (34, 28), self.app.assets.font(28, True), COLORS["green"])
        draw_text(surface, "Executable levels: click and drag nodes, TAB cycles values, DELETE removes, SAVE validates and persists the graph.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (26, 102, 748, 402), self.graph.name, COLORS["green"])
        for node in self.graph.nodes:
            for target in self.graph.nodes:
                if node.node_id in target.inputs:
                    ui_draw_line(surface, COLORS["line"], (node.x + 180, node.y + 47), (target.x, target.y + 47), 2)
        for node in self.graph.nodes:
            accent = COLORS["cyan"] if node.kind == "trigger" else COLORS["gold"] if node.kind == "condition" else COLORS["green"]
            if node is self.selected: accent = COLORS["red"]
            rounded(surface, (node.x, node.y, 180, 94), (16, 29, 62), accent, 9, 2)
            draw_text(surface, f"LEVEL {node.level}  {node.label}", (node.x + 12, node.y + 15), self.app.assets.font(11, True), accent)
            for index, line in enumerate(wrap(self.app.assets.font(12), node.value, 150)[:3]): draw_text(surface, line, (node.x + 12, node.y + 45 + index * 15), self.app.assets.font(12), COLORS["cream"])
        self.draw_buttons(surface, 11)
        self.app.draw_notice(surface)


class CharactersScene(Scene):
    def enter(self):
        self.query = TextInput((420, 28, 220, 30), "")
        self.sort_mode = "name"
        self.row_buttons = []
        self.buttons = [Button((34, 530, 168, 38), "CHARACTER MAKER", lambda: self.app.push(CharacterMakerScene(self.app))), Button((214, 530, 126, 38), "TEAMS", lambda: self.app.push(TeamsScene(self.app))), Button((348, 530, 126, 38), "SORT: NAME", lambda: self.toggle_sort()), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop())]

    def toggle_sort(self):
        self.sort_mode = "rank" if self.sort_mode == "name" else "name"
        self.buttons[2].label = "SORT: " + self.sort_mode.upper()

    def handle(self, event):
        self.query.handle(event)
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in self.row_buttons:
                if button.rect.collidepoint(event.pos): button.callback(); return

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CHARACTERS", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, "Identity, preferences, relationships, smartness, decks, and experience live together.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.query.draw(surface, self.app.assets.font(11), "Search characters")
        self.row_buttons = []
        for index, char in enumerate(query_entities(self.app.store.characters.values(), self.query.value, self.sort_mode)[:4]):
            y = 118 + index * 95
            roles = self.app.store.role_config()
            accent = COLORS["cyan"] if char.id == roles["player_character"] else COLORS["red"] if char.id == roles["default_opponent_character"] else COLORS["violet"]
            rounded(surface, (36, y, 728, 82), (14, 24, 52), accent, 8, 2)
            image = self.app.assets.image(char.portrait, (64, 64)) or self.app.assets.image("pfp_placeholder", (64, 64))
            if image: ui_blit(surface, image, (50, y + 9))
            draw_text(surface, char.name, (132, y + 14), self.app.assets.font(16, True), COLORS["cream"])
            draw_text(surface, f"{char.stars} stars  |  rank {char.rank}  |  smartness {char.smartness}/10  |  mood {char.mood}", (132, y + 41), self.app.assets.font(11), accent)
            draw_text(surface, "Preferred: " + ", ".join(char.preferred_families) + "  |  best cards: " + str(len(char.best_cards)), (132, y + 62), self.app.assets.font(10), COLORS["muted"])
            button = Button((650, y + 23, 92, 34), "DETAIL", lambda char_id=char.id: self.app.push(EntityDetailScene(self.app, "characters", char_id)), COLORS["cyan"])
            self.row_buttons.append(button)
            button.draw(surface, self.app.assets.font(10, True))
        self.draw_buttons(surface, 11)


class EntityDetailScene(Scene):
    def __init__(self, app, entity_type, entity_id):
        super().__init__(app)
        self.entity_type = entity_type
        self.entity_id = entity_id

    def enter(self):
        self.buttons = []
        if self.entity_type == "characters": self.buttons.append(Button((470, 530, 160, 38), "EDIT WEIGHTS", lambda: self.app.push(BehaviorWeightsScene(self.app, self.entity_id)), COLORS["gold"]))
        self.buttons.append(Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"]))

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        entity = getattr(self.app.store, self.entity_type).get(self.entity_id)
        if not entity:
            draw_text(surface, "ENTITY NOT FOUND", (400, 280), self.app.assets.font(22, True), COLORS["red"], "center")
            self.draw_buttons(surface, 12)
            return
        accent = COLORS["violet"] if self.entity_type == "characters" else COLORS["green"] if self.entity_type == "places" else COLORS["gold"]
        draw_text(surface, entity.name, (34, 28), self.app.assets.font(28, True), accent)
        draw_text(surface, self.entity_type[:-1].upper() + " DETAIL", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (42, 112, 716, 360), "PERSISTENT STATUS", accent)
        if self.entity_type == "characters":
            image = self.app.assets.image(entity.portrait, (150, 150)) or self.app.assets.image("pfp_placeholder", (150, 150))
            if image: ui_blit(surface, image, (68, 165))
            weights = ", ".join(f"{key}={float(value):.1f}" for key, value in sorted(entity.behavior_weights.items()) if key != "movement_duration" and isinstance(value, (int, float)))
            lines = [f"Gender: {entity.gender}", f"Origin: {entity.origin}", f"Stars: {entity.stars}", f"Rank: {entity.rank}", f"Smartness: {entity.smartness}/10", f"Mood: {entity.mood}", f"Relationship: {entity.relationship}", "Preferred: " + ", ".join(entity.preferred_families), "Best cards: " + ", ".join(entity.best_cards or ["not set"]), f"Learned opponents: {len(entity.learned_opponents)}  |  learned cards: {len(entity.learned_cards)}", "Weights: " + (weights or "default"), f"History events: {len(entity.history)}"]
        elif self.entity_type == "places":
            lines = [f"Capacity: {entity.capacity}", f"Active duels: {entity.current_duels}", f"Background: {entity.background}", f"Day/night: {'enabled' if entity.day_night else 'disabled'}", f"Media folder: {entity.media_folder or 'legacy/id folder'}"]
        else:
            effect = entity.team_effect.get("selected") if entity.team_effect else None
            lines = [f"Members: {len(entity.members)}", f"Leader: {entity.leader}", f"Rank: {entity.rank}", f"Relationship: {entity.relationship}", f"Effect: {effect.get('kind') if effect else 'not crafted'}", f"History events: {len(entity.history)}"]
        for index, line in enumerate(lines): draw_text(surface, line, (270 if self.entity_type == "characters" else 70, 170 + index * 28), self.app.assets.font(13), COLORS["cream"])
        self.draw_buttons(surface, 12)


class BehaviorWeightsScene(Scene):
    scalar_keys = ["risk_tolerance", "learning_value", "rematch_desire", "reward_value", "place_preference", "ally_bias", "enemy_bias", "adaptation"]
    state_keys = ["stranger", "ally", "enemy", "opponent"]
    phase_keys = ["MAIN 1", "MAIN 2", "BATTLE"]

    def __init__(self, app, character_id):
        super().__init__(app)
        self.character_id = character_id

    def enter(self):
        self.character = self.app.store.characters.get(self.character_id)
        self.buttons = []
        for index, key in enumerate(self.scalar_keys):
            x = 50 if index < 4 else 400
            y = 150 + (index % 4) * 48
            self.buttons.append(Button((x, y, 300, 36), "", lambda key=key: self.cycle_scalar(key), COLORS["gold"]))
        for index, key in enumerate(self.state_keys):
            self.buttons.append(Button((50 + index * 175, 370, 160, 34), "", lambda key=key: self.cycle_state(key), COLORS["cyan"]))
        for index, key in enumerate(self.phase_keys):
            self.buttons.append(Button((50 + index * 175, 420, 160, 34), "", lambda key=key: self.cycle_phase(key), COLORS["violet"]))
        self.buttons.append(Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"]))
        self.refresh_labels()

    def refresh_labels(self):
        if not self.character: return
        for index, key in enumerate(self.scalar_keys): self.buttons[index].label = key.upper().replace("_", " ") + ": " + str(round(float(self.character.behavior_weights.get(key, 0)), 1))
        offset = len(self.scalar_keys)
        for index, key in enumerate(self.state_keys): self.buttons[offset + index].label = key.upper() + ": " + str(round(float(self.character.behavior_weights.get("state_weights", {}).get(key, 1)), 1))
        offset += len(self.state_keys)
        for index, key in enumerate(self.phase_keys): self.buttons[offset + index].label = key + ": " + str(round(float(self.character.behavior_weights.get("phase_weights", {}).get(key, 1)), 1))

    def cycle_scalar(self, key):
        self.character.behavior_weights[key] = (float(self.character.behavior_weights.get(key, 0)) + 1.0) % 11.0
        self.app.store.save()
        self.refresh_labels()

    def cycle_state(self, key):
        values = self.character.behavior_weights.setdefault("state_weights", {})
        values[key] = (float(values.get(key, 1)) + 0.5) % 10.5
        self.app.store.save()
        self.refresh_labels()

    def cycle_phase(self, key):
        values = self.character.behavior_weights.setdefault("phase_weights", {})
        values[key] = (float(values.get(key, 1)) + 0.5) % 10.5
        self.app.store.save()
        self.refresh_labels()

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CHARACTER BEHAVIOR WEIGHTS", (34, 28), self.app.assets.font(27, True), COLORS["gold"])
        draw_text(surface, "These values shape requests, card choices, risk, rematches, and adaptation over real simulated history.", (36, 66), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (34, 104, 732, 390), "WEIGHT PROFILE  |  " + (self.character.name if self.character else "UNKNOWN"), COLORS["gold"])
        draw_text(surface, "RELATIONSHIP STATE", (50, 350), self.app.assets.font(12, True), COLORS["cyan"])
        draw_text(surface, "DUEL PHASE", (50, 402), self.app.assets.font(12, True), COLORS["violet"])
        self.draw_buttons(surface, 12)


class CharacterMakerScene(Scene):
    genders = ["other", "he", "she"]

    def enter(self):
        self.name = TextInput((90, 150, 300, 34), "New Character")
        self.family = TextInput((90, 215, 300, 34), "warrior")
        self.portrait = TextInput((430, 150, 280, 34), "pfp_placeholder")
        self.origin = TextInput((430, 215, 280, 34), "community")
        self.deck = TextInput((90, 280, 300, 34), "")
        self.gender = "other"
        self.stars = 5
        self.smartness = 5
        self.buttons = [Button((430, 280, 160, 34), "GENDER: OTHER", lambda: self.cycle_gender(), COLORS["violet"]), Button((90, 345, 110, 38), "STARS +", lambda: self.change("stars", 1), COLORS["gold"]), Button((210, 345, 110, 38), "SMART +", lambda: self.change("smartness", 1), COLORS["cyan"]), Button((90, 410, 230, 44), "CREATE CHARACTER", lambda: self.create(), COLORS["green"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def change(self, field, amount): setattr(self, field, clamp(getattr(self, field) + amount, 1, 10))

    def cycle_gender(self):
        self.gender = self.genders[(self.genders.index(self.gender) + 1) % len(self.genders)]
        self.buttons[0].label = "GENDER: " + self.gender.upper()

    def create(self):
        self.app.store.create_character(self.name.value, self.stars, self.smartness, self.family.value, self.portrait.value, self.gender, self.origin.value, self.deck.value)
        self.app.store.load()
        self.app.notify("Character saved with explicit identity, deck, and reaction folders.")

    def handle(self, event):
        self.name.handle(event)
        self.family.handle(event)
        self.portrait.handle(event)
        self.origin.handle(event)
        self.deck.handle(event)
        super().handle(event)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CHARACTER MAKER", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, "Create a character from explicit authored identity and deck choices; runtime experience stays in state.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (42, 112, 720, 354), "CHARACTER DEFINITION", COLORS["violet"])
        self.name.draw(surface, self.app.assets.font(13), "Character name")
        self.family.draw(surface, self.app.assets.font(13), "Preferred card family")
        self.portrait.draw(surface, self.app.assets.font(13), "Portrait file key")
        self.origin.draw(surface, self.app.assets.font(13), "Origin")
        self.deck.draw(surface, self.app.assets.font(13), "Existing deck id, optional")
        draw_text(surface, f"STAR LEVEL {self.stars}     SMARTNESS {self.smartness}/10", (430, 355), self.app.assets.font(16, True), COLORS["cream"])
        draw_text(surface, "The AI foundation records duel history, studied cards, preferences, and relationships separately.", (90, 390), self.app.assets.font(11), COLORS["muted"])
        self.draw_buttons(surface, 12)
        self.app.draw_notice(surface)


class TeamsScene(Scene):
    def enter(self):
        self.query = TextInput((420, 28, 220, 30), "")
        self.sort_mode = "name"
        self.row_buttons = []
        self.buttons = [Button((34, 530, 140, 38), "TEAM MAKER", lambda: self.app.push(TeamMakerScene(self.app))), Button((200, 530, 140, 38), "TEAM DUEL", lambda: self.app.push(TeamDuelScene(self.app))), Button((360, 530, 180, 38), "CRAFT TEAM EFFECT", lambda: self.app.push(TeamEffectScene(self.app))), Button((548, 530, 92, 38), "SORT: NAME", lambda: self.toggle_sort()), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop())]

    def toggle_sort(self):
        self.sort_mode = "rank" if self.sort_mode == "name" else "name"
        self.buttons[3].label = "SORT: " + self.sort_mode.upper()

    def handle(self, event):
        self.query.handle(event)
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in self.row_buttons:
                if button.rect.collidepoint(event.pos): button.callback(); return

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "TEAMS", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, "Teams carry members, leaders, preferred places, relationships, and shared identity.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.query.draw(surface, self.app.assets.font(11), "Search teams")
        self.row_buttons = []
        for index, team in enumerate(query_entities(self.app.store.teams.values(), self.query.value, self.sort_mode)[:4]):
            y = 118 + index * 95
            rounded(surface, (40, y, 720, 82), (14, 24, 52), COLORS["violet"], 8, 2)
            draw_text(surface, team.name, (64, y + 14), self.app.assets.font(16, True), COLORS["cream"])
            draw_text(surface, f"Members: {len(team.members)}   |   Leader: {team.leader}   |   Rank: {team.rank}   |   {team.relationship}", (64, y + 42), self.app.assets.font(11), COLORS["cyan"])
            effect = team.team_effect.get("selected") if team.team_effect else None
            draw_text(surface, "Effect: " + (effect.get("kind", "candidate") if effect else "not crafted") + "  |  places: " + (", ".join(team.preferred_places) or "none"), (64, y + 63), self.app.assets.font(10), COLORS["muted"])
            button = Button((650, y + 22, 92, 34), "DETAIL", lambda team_id=team.id: self.app.push(EntityDetailScene(self.app, "teams", team_id)), COLORS["gold"])
            self.row_buttons.append(button)
            button.draw(surface, self.app.assets.font(10, True))
        self.draw_buttons(surface, 11)


class TeamEffectScene(Scene):
    def enter(self):
        self.team_id = self.app.store.role_config()["default_player_team"]
        self.team = self.app.store.teams[self.team_id]
        self.selected = []
        self.candidates = self.team.team_effect.get("candidates", []) if self.team.team_effect else []
        self.card_rects = []
        self.buttons = [Button((48, 530, 170, 38), "CRAFT CANDIDATES", lambda: self.craft(), COLORS["gold"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def available_cards(self):
        result = []
        for member_id in self.team.members:
            character = self.app.store.characters.get(member_id)
            for card_id in dict.fromkeys(character.library_cards if character else []):
                if card_id in self.app.store.cards and card_id not in [item[0] for item in result]: result.append((card_id, member_id))
        return result

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, card_id in self.card_rects:
                if rect.collidepoint(event.pos):
                    if card_id in self.selected: self.selected.remove(card_id)
                    elif len(self.selected) < 3: self.selected.append(card_id)

    def craft(self):
        if self.team.effect_locked:
            self.app.notify("This team effect is permanently locked already.")
            return
        if len(self.selected) != 3:
            self.app.notify("Sacrifice three different cards to create effect candidates.")
            return
        result = self.app.store.craft_team_effect(self.team_id, self.selected)
        if result:
            self.candidates = result.get("candidates", [])
            self.app.notify("Three team effects were generated. Choose one forever.")
            self.buttons = [Button((48 + index * 232, 470, 210, 42), "CHOOSE " + str(index + 1), lambda index=index: self.choose(index), COLORS["gold"]) for index in range(3)] + [Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]
        else: self.app.notify("The selected cards cannot form a team effect.")

    def choose(self, index):
        if self.app.store.choose_team_effect(self.team_id, index): self.app.notify("Team effect locked permanently: " + self.candidates[index].get("kind", "effect"))
        else: self.app.notify("A team effect is already locked or the choice is invalid.")

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "TEAM EFFECT CRAFTING", (34, 28), self.app.assets.font(28, True), COLORS["gold"])
        draw_text(surface, "Sacrifice three different member-owned cards. The team chooses one generated effect forever.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (36, 104, 728, 330), self.team.name, COLORS["gold"])
        self.card_rects = []
        for index, (card_id, owner) in enumerate(self.available_cards()[:12]):
            x = 58 + (index % 4) * 174
            y = 148 + (index // 4) * 88
            rect = pygame.Rect(x, y, 156, 68)
            self.card_rects.append((rect, card_id))
            accent = COLORS["gold"] if card_id in self.selected else COLORS["cyan"]
            rounded(surface, rect, (16, 30, 62), accent, 7, 2)
            draw_text(surface, self.app.store.cards[card_id].name, (x + 78, y + 20), self.app.assets.font(11, True), COLORS["cream"], "center")
            draw_text(surface, owner, (x + 78, y + 44), self.app.assets.font(9), COLORS["muted"], "center")
        if self.candidates:
            draw_text(surface, "CANDIDATES", (400, 450), self.app.assets.font(12, True), COLORS["gold"], "center")
            for index, candidate in enumerate(self.candidates): draw_text(surface, f"{index + 1}. {candidate}", (400, 470 + index * 18), self.app.assets.font(10), COLORS["cream"], "center")
        else: draw_text(surface, f"Selected sacrifices: {len(self.selected)} / 3", (400, 450), self.app.assets.font(13, True), COLORS["cyan"], "center")
        self.draw_buttons(surface, 11)
        self.app.draw_notice(surface)


class TeamDuelScene(Scene):
    def __init__(self, app, format_name="TEAMvTEAM", target_id=None, starter="opponent", reserved=False):
        super().__init__(app)
        roles = app.store.role_config()
        self.format_name = format_name
        self.target_id = target_id or roles["default_opponent_team"]
        self.starter = starter
        self.reserved = reserved
        player_team = app.store.teams.get(roles["default_player_team"])
        opponent_team = app.store.teams.get(roles["default_opponent_team"])
        if format_name == "1vTEAM":
            player = app.store.characters[roles["player_character"]]
            player_team = TeamDef("match_player", player.name, [player.id], player.id, [roles["default_place"]], "solo")
            opponent_team = app.store.teams.get(self.target_id, opponent_team)
        elif format_name == "TEAMv1":
            opponent = app.store.characters.get(self.target_id, app.store.characters[roles["default_opponent_character"]])
            opponent_team = TeamDef("match_opponent", opponent.name, [opponent.id], opponent.id, [roles["default_place"]], "solo")
        elif format_name == "TEAMvTEAM":
            opponent_team = app.store.teams.get(self.target_id, opponent_team)
        self.engine = TeamDuelEngine(app.store, player_team=player_team, opponent_team=opponent_team, format_name=format_name, starter=starter, reserved=reserved)
        self.timer = 0.0
        self.buttons = [Button((650, 530, 110, 38), "BACK", lambda: self.app.pop())]

    def update(self, dt):
        self.timer += dt
        if self.timer >= 0.35 and not self.engine.finished:
            self.timer = 0.0
            self.engine.step()

    def draw(self, surface):
        self.draw_background(surface, self.app.store.places[self.app.store.role_config()["default_place"]].background)
        veil = ui_surface((W, H), pygame.SRCALPHA)
        veil.fill((247, 227, 177, 46))
        ui_blit(surface, veil, (0, 0))
        draw_text(surface, self.format_name + " BATTLE", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, f"Round {min(self.engine.round, 3)} / 3   |   ordered roster rotation   |   {self.engine.place_id}", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (34, 104, 350, 350), self.engine.player_team.name, COLORS["cyan"])
        self.draw_panel(surface, (416, 104, 350, 350), self.engine.opponent_team.name, COLORS["red"])
        for index, character in enumerate(self.engine.roster(self.engine.player_team)):
            y = 160 + index * 62
            color = COLORS["gold"] if self.engine.current and self.engine.current.player.character.id == character.id else COLORS["cream"]
            draw_text(surface, f"{index + 1}. {character.name}", (60, y), self.app.assets.font(15, True), color)
            draw_text(surface, f"{character.stars} stars | {character.relationship} | {character.smartness}/10", (60, y + 25), self.app.assets.font(11), COLORS["muted"])
        for index, character in enumerate(self.engine.roster(self.engine.opponent_team)):
            y = 160 + index * 62
            color = COLORS["gold"] if self.engine.current and self.engine.current.opponent.character.id == character.id else COLORS["cream"]
            draw_text(surface, f"{index + 1}. {character.name}", (442, y), self.app.assets.font(15, True), color)
            draw_text(surface, f"{character.stars} stars | {character.relationship} | {character.smartness}/10", (442, y + 25), self.app.assets.font(11), COLORS["muted"])
        if self.engine.current:
            draw_text(surface, f"{self.engine.current.player.name}  vs  {self.engine.current.opponent.name}", (400, 480), self.app.assets.font(16, True), COLORS["gold"], "center")
        for index, event in enumerate(self.engine.events[-4:]): draw_text(surface, event, (400, 505 + index * 16), self.app.assets.font(10), COLORS["cream"], "center")
        self.draw_buttons(surface, 12)
        if self.engine.finished:
            rounded(surface, (210, 185, 380, 150), COLORS["panel"], COLORS["gold"], 10, 2)
            title = "TEAM DRAW" if self.engine.winner is None else f"{self.engine.winner.name.upper()} WINS"
            draw_text(surface, "TEAM DUEL COMPLETE", (400, 220), self.app.assets.font(22, True), COLORS["gold"], "center")
            draw_text(surface, title, (400, 265), self.app.assets.font(20, True), COLORS["cyan"] if self.engine.winner is self.engine.player_team else COLORS["red"] if self.engine.winner else COLORS["gold"], "center")
            draw_text(surface, f"Rounds recorded: {len(self.engine.results)}", (400, 300), self.app.assets.font(12), COLORS["cream"], "center")


class TeamMakerScene(Scene):
    def enter(self):
        self.name = TextInput((90, 150, 300, 34), "New Team")
        self.place = TextInput((90, 215, 300, 34), self.app.store.role_config()["default_place"])
        self.member_inputs = [TextInput((430, 150 + index * 65, 280, 34), "") for index in range(3)]
        self.buttons = [Button((90, 355, 230, 44), "CREATE TEAM", lambda: self.create(), COLORS["green"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def handle(self, event):
        self.name.handle(event)
        self.place.handle(event)
        for field in self.member_inputs: field.handle(event)
        super().handle(event)

    def create(self):
        members = [field.value.strip() for field in self.member_inputs if field.value.strip()]
        team = self.app.store.create_team(self.name.value, members, self.place.value)
        if team:
            self.app.store.load()
            self.app.notify("Team saved with the selected members and preferred place.")
        else: self.app.notify("Choose at least one registered non-player character.")

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "TEAM MAKER", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, "Create a team from explicit registered character ids; no hidden auto-selection is used.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (42, 112, 720, 320), "TEAM DEFINITION", COLORS["violet"])
        self.name.draw(surface, self.app.assets.font(13), "Team name")
        self.place.draw(surface, self.app.assets.font(13), "Preferred place id")
        for index, field in enumerate(self.member_inputs): field.draw(surface, self.app.assets.font(13), f"Member {index + 1} character id")
        draw_text(surface, "Use ids from the Characters screen. Up to three distinct members are stored; the first is leader.", (90, 312), self.app.assets.font(11), COLORS["muted"])
        self.draw_buttons(surface, 12)
        self.app.draw_notice(surface)


class PlacesScene(Scene):
    def enter(self):
        self.query = TextInput((420, 28, 220, 30), "")
        self.sort_mode = "name"
        self.row_buttons = []
        self.buttons = [Button((34, 530, 142, 38), "PLACE MAKER", lambda: self.app.push(PlaceMakerScene(self.app)), COLORS["green"]), Button((490, 530, 142, 38), "SORT: NAME", lambda: self.toggle_sort()), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def toggle_sort(self):
        self.sort_mode = "rank" if self.sort_mode == "name" else "name"
        self.buttons[1].label = "SORT: " + self.sort_mode.upper()

    def handle(self, event):
        self.query.handle(event)
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in self.row_buttons:
                if button.rect.collidepoint(event.pos): button.callback(); return

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "PLACES", (34, 28), self.app.assets.font(28, True), COLORS["green"])
        draw_text(surface, "Fields can carry background media, music, occupancy, day/night variants, and effects.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.query.draw(surface, self.app.assets.font(11), "Search places")
        self.row_buttons = []
        for index, place in enumerate(query_entities(self.app.store.places.values(), self.query.value, self.sort_mode)[:3]):
            y = 124 + index * 130
            rounded(surface, (40, y, 720, 104), (13, 26, 57), COLORS["green"], 10, 2)
            image = self.app.assets.image(place.background, (160, 92)) if place.background else None
            if image: ui_blit(surface, image, (54, y + 6))
            draw_text(surface, place.name, (238, y + 18), self.app.assets.font(17, True), COLORS["cream"])
            draw_text(surface, f"Active duels: {place.current_duels}/{place.capacity}", (238, y + 48), self.app.assets.font(12), COLORS["cyan"])
            draw_text(surface, "Day/night: " + ("enabled" if place.day_night else "disabled") + "  |  media: " + ("scaffolded" if place.media_folder else "legacy"), (238, y + 75), self.app.assets.font(10), COLORS["muted"])
            button = Button((650, y + 34, 92, 34), "DETAIL", lambda place_id=place.id: self.app.push(EntityDetailScene(self.app, "places", place_id)), COLORS["green"])
            self.row_buttons.append(button)
            button.draw(surface, self.app.assets.font(10, True))
        self.draw_buttons(surface, 11)


class PlaceMakerScene(Scene):

    def enter(self):
        self.name = TextInput((90, 150, 300, 34), "New Place")
        self.capacity = TextInput((90, 215, 300, 34), "3")
        self.background = TextInput((430, 150, 280, 34), "")
        self.day_night = True
        self.buttons = [Button((430, 215, 180, 34), "DAY/NIGHT: ON", lambda: self.toggle_day_night(), COLORS["cyan"]), Button((90, 300, 220, 44), "CREATE PLACE", lambda: self.create(), COLORS["green"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def handle(self, event):
        self.name.handle(event)
        self.capacity.handle(event)
        self.background.handle(event)
        super().handle(event)

    def toggle_day_night(self):
        self.day_night = not self.day_night
        self.buttons[0].label = "DAY/NIGHT: " + ("ON" if self.day_night else "OFF")

    def create(self):
        try: capacity = int(self.capacity.value)
        except ValueError: capacity = 3
        if not self.background.value.strip(): self.app.notify("Choose an authored background asset key."); return
        self.app.store.create_place(self.name.value, capacity, self.background.value.strip(), self.day_night)
        self.app.store.load()
        self.app.notify("Place saved with explicit capacity, background, day/night, and media folders.")

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "PLACE MAKER", (34, 28), self.app.assets.font(28, True), COLORS["green"])
        draw_text(surface, "Create a location from explicit capacity and media routing choices.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (42, 112, 720, 300), "PLACE DEFINITION", COLORS["green"])
        self.name.draw(surface, self.app.assets.font(13), "Place name")
        self.capacity.draw(surface, self.app.assets.font(13), "Capacity, 1 to 10")
        self.background.draw(surface, self.app.assets.font(13), "Background asset key")
        draw_text(surface, "Media folders are scaffolded for day/night, event animation, and music variants.", (90, 270), self.app.assets.font(11), COLORS["muted"])
        self.draw_buttons(surface, 12)
        self.app.draw_notice(surface)


class SettingsScene(Scene):
    def enter(self):
        self.scroll = 0
        self.option_rows = [("GRAPHICS", "WINDOW SIZE", lambda: self.app.cycle_resolution()), ("GRAPHICS", "FULLSCREEN", lambda: self.app.toggle_fullscreen()), ("AUDIO", "MUSIC", lambda: self.app.toggle_music()), ("AUDIO", "SFX", lambda: self.app.toggle_sfx()), ("AUDIO", "VOICE", lambda: self.app.toggle_vocals()), ("GAMEPLAY", "DIFFICULTY", lambda: self.app.cycle_difficulty())]
        self.refresh_buttons()

    def refresh_buttons(self):
        self.buttons = []
        for index, (_, label, action) in enumerate(self.option_rows):
            y = 138 + index * 54 - self.scroll * 54
            if 118 <= y <= 460: self.buttons.append(Button((66, y, 300, 40), label, action, COLORS["line"]))
        self.buttons.append(Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"]))

    def handle(self, event):
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = clamp(self.scroll - event.y, 0, max(0, len(self.option_rows) - 5))
            self.refresh_buttons()
            return
        super().handle(event)

    def setting_value(self, label):
        data = self.app.store.save_data
        keys = {"WINDOW SIZE": "resolution", "FULLSCREEN": "fullscreen", "MUSIC": "music", "SFX": "sfx", "VOICE": "vocals", "DIFFICULTY": "difficulty"}
        value = data.get(keys[label], "")
        return str(value).upper()

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "SETTINGS", (34, 28), self.app.assets.font(28, True), COLORS["cream"])
        draw_text(surface, "One compact list for graphics and audio. Scroll for every option.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (42, 108, 338, 382), "OPTIONS", COLORS["gold"])
        self.draw_panel(surface, (408, 108, 350, 382), "CURRENT PROFILE", COLORS["cyan"])
        for index, (category, label, _) in enumerate(self.option_rows):
            y = 160 + index * 54 - self.scroll * 54
            if 136 <= y <= 466:
                draw_text(surface, category, (430, y + 4), self.app.assets.font(10, True), COLORS["muted"])
                draw_text(surface, label, (430, y + 22), self.app.assets.font(14, True), COLORS["cream"])
                draw_text(surface, self.setting_value(label), (730, y + 14), self.app.assets.font(13, True), COLORS["gold"], "topright")
        ui_draw_rect(surface, COLORS["line"], (370, 124, 5, 342), border_radius=2)
        thumb_h = max(48, 342 * 5 / max(5, len(self.option_rows)))
        thumb_y = 124 + (342 - thumb_h) * self.scroll / max(1, len(self.option_rows) - 5)
        ui_draw_rect(surface, COLORS["gold"], (370, thumb_y, 5, thumb_h), border_radius=2)
        self.draw_buttons(surface, 13)


class TradingScene(Scene):
    def enter(self):
        self.selected_id = ""
        self.refresh()

    def refresh(self):
        self.deals = self.app.store.trade_list()
        self.buttons = [Button((34, 530, 160, 38), "NEW TYPE OFFER", lambda: self.new_offer(), COLORS["orange"]), Button((204, 530, 112, 38), "ACCEPT", lambda: self.accept(), COLORS["green"]), Button((326, 530, 112, 38), "COUNTER", lambda: self.counter(), COLORS["gold"]), Button((448, 530, 112, 38), "CANCEL", lambda: self.cancel(), COLORS["red"]), Button((570, 530, 150, 38), "ESCALATE TO DUEL", lambda: self.escalate(), COLORS["violet"]), Button((650, 575, 110, 24), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def selected(self):
        return self.app.store.get_trade(self.selected_id) if self.selected_id else None

    def new_offer(self):
        roles = self.app.store.role_config()
        library = self.app.store.characters[roles["player_character"]].library_cards
        if not library:
            self.app.notify("The player library has no cards to offer.")
            return
        trade = self.app.store.create_trade(roles["player_character"], roles["default_opponent_character"], [library[0]], requested_family="aqua")
        self.selected_id = trade["id"] if trade else ""
        recipient_name = self.app.store.characters[roles["default_opponent_character"]].name
        self.app.notify(f"A three-hour type-based offer was created for {recipient_name}.")
        self.refresh()

    def accept(self):
        trade = self.selected()
        if trade and self.app.store.accept_trade(trade["id"], trade["recipient"]): self.app.notify("Trade accepted and card ownership transferred.")
        else: self.app.notify("This trade cannot be accepted: cards may be unavailable or the request is unsatisfied.")
        self.refresh()

    def counter(self):
        trade = self.selected()
        if not trade: self.app.notify("Select an open trade first."); return
        library = self.app.store.characters[trade["recipient"]].library_cards
        if not library:
            self.app.notify("The recipient has no card available for a counteroffer.")
            return
        counter = self.app.store.counter_trade(trade["id"], trade["recipient"], [library[0]], requested_family="warrior")
        self.selected_id = counter["id"] if counter else self.selected_id
        self.app.notify("A persistent counteroffer was created." if counter else "Counteroffer rejected by the trade rules.")
        self.refresh()

    def cancel(self):
        trade = self.selected()
        success = bool(trade and self.app.store.cancel_trade(trade["id"], self.app.store.role_config()["player_character"]))
        self.app.notify("Trade canceled." if success else "Only an active trade can be canceled.")
        self.refresh()

    def escalate(self):
        trade = self.selected()
        request_id = self.app.store.escalate_trade(trade["id"], self.app.store.role_config()["player_character"]) if trade else None
        if request_id and trade:
            self.app.notify(f"Trade escalated into duel request {request_id}.")
            self.app.push(PreDuelScene(self.app, trade["recipient"]))
        else:
            self.app.notify("This trade cannot be escalated.")
        self.refresh()

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, trade in enumerate(self.deals[-4:]):
                if pygame.Rect(46, 125 + index * 90, 708, 68).collidepoint(event.pos): self.selected_id = trade["id"]

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "TRADING", (34, 28), self.app.assets.font(28, True), COLORS["orange"])
        draw_text(surface, "Persistent three-hour offers with type requests, counters, transfer, cancellation, and duel escalation.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        visible = self.deals[-4:]
        for index, trade in enumerate(visible):
            y = 125 + index * 90
            accent = COLORS["gold"] if trade["id"] == self.selected_id else COLORS["orange"]
            rounded(surface, (46, y, 708, 68), (15, 28, 58), accent, 8, 2 if trade["id"] == self.selected_id else 1)
            creator = self.app.store.characters.get(trade["creator"])
            recipient = self.app.store.characters.get(trade["recipient"])
            draw_text(surface, f"{creator.name if creator else trade['creator']} -> {recipient.name if recipient else trade['recipient']}  |  {trade['state'].upper()}", (64, y + 13), self.app.assets.font(13, True), COLORS["cream"])
            requested = self.app.store.card_names(trade.get("requested_cards", [])) if trade.get("requested_cards") else "family: " + (trade.get("requested_family") or "any")
            draw_text(surface, f"Gives: {self.app.store.card_names(trade.get('offered_cards', []))}    Wants: {requested}", (64, y + 39), self.app.assets.font(11), COLORS["muted"])
        selected = self.selected()
        if selected:
            history = selected.get("history", [])[-2:]
            draw_text(surface, "NEGOTIATION: " + "  |  ".join(item.get("action", "event") for item in history), (400, 505), self.app.assets.font(11), COLORS["cyan"], "center")
        else:
            draw_text(surface, "Select a trade row to negotiate.", (400, 505), self.app.assets.font(11), COLORS["muted"], "center")
        self.draw_buttons(surface, 11)
        self.app.draw_notice(surface)


class ImportExportScene(Scene):
    def enter(self):
        self.buttons = [Button((54, 150, 250, 44), "EXPORT WORLD .CBP", lambda: self.export_world(), COLORS["cyan"]), Button((54, 210, 250, 44), "SCAN EXPORT FOLDER", lambda: self.scan(), COLORS["violet"]), Button((54, 270, 250, 44), "IMPORT LATEST ALL", lambda: self.import_latest()), Button((54, 330, 250, 44), "IMPORT CONTENT ONLY", lambda: self.import_latest(["cards", "characters", "decks", "places", "teams", "logic"]), COLORS["gold"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]
        self.files = list((DATA / "exports").glob("*.cbp"))

    def import_latest(self, include=None):
        self.scan()
        if not self.files:
            self.app.notify("No .cbp package is available in data/exports/.")
            return
        manifest = self.app.store.inspect_cbp(self.files[-1])
        result = self.app.store.import_cbp(self.files[-1], include)
        self.app.notify(f"Imported {manifest.get('kind', 'content')} package: {', '.join(result['imported'])}.")

    def export_world(self):
        path = self.app.store.export_cbp("world", "cbp_world")
        self.files = list((DATA / "exports").glob("*.cbp"))
        self.app.notify(f"Exported {path.name} with manifest and data registries.")

    def scan(self): self.files = list((DATA / "exports").glob("*.cbp"))

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "IMPORT / EXPORT", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, "The .cbp package is a zip with a manifest and selected dependencies.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (370, 120, 386, 322), "MANIFEST PREVIEW", COLORS["violet"])
        latest_manifest = self.app.store.inspect_cbp(self.files[-1]) if self.files else {}
        draw_text(surface, f"Schema {latest_manifest.get('schema', 3)}  |  Scope: {latest_manifest.get('kind', 'world').upper()}", (400, 175), self.app.assets.font(14, True), COLORS["cream"])
        draw_text(surface, f"Cards: {len(self.app.store.cards)}", (400, 215), self.app.assets.font(13), COLORS["cyan"])
        draw_text(surface, f"Characters: {len(self.app.store.characters)}", (400, 245), self.app.assets.font(13), COLORS["cyan"])
        draw_text(surface, f"Decks: {len(self.app.store.decks)}", (400, 275), self.app.assets.font(13), COLORS["cyan"])
        draw_text(surface, f"Places: {len(self.app.store.places)}", (400, 305), self.app.assets.font(13), COLORS["cyan"])
        draw_text(surface, "Exports", (400, 345), self.app.assets.font(14, True), COLORS["gold"])
        for index, path in enumerate(self.files[-3:]): draw_text(surface, path.name, (400, 372 + index * 20), self.app.assets.font(11), COLORS["muted"])
        self.draw_buttons(surface, 12)
        self.app.draw_notice(surface)


class WatchScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.buttons = []
        self.battle_rows = []

    def enter(self): self.refresh()

    def active_battles(self): return [entry for entry in self.app.store.world.setdefault("active_battles", []) if entry.get("status") == "active"]

    def refresh(self):
        self.battle_rows = self.active_battles()
        self.buttons = []
        for index, battle in enumerate(self.battle_rows[:4]):
            self.buttons.append(Button((600, 142 + index * 76, 130, 38), "WATCH LIVE", lambda battle=battle: self.open_watch(battle), COLORS["gold"]))
        self.buttons.extend([Button((38, 530, 130, 38), "ADVANCE 1 SEC", lambda: self.advance(1), COLORS["cyan"]), Button((180, 530, 130, 38), "ADVANCE 5 SEC", lambda: self.advance(5), COLORS["gold"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])])

    def advance(self, seconds):
        self.app.store.advance_world(seconds)
        self.refresh()
        self.app.notify(f"World advanced by {seconds} real-time simulation seconds.")

    def battle_participant(self, battle, key):
        identifier = battle.get(key) or battle.get("to" if key == "house" else "from", "unknown")
        return self.app.store.characters.get(identifier)

    def open_watch(self, battle):
        session = self.app.store._world_session(battle)
        if not session:
            self.app.notify("This live battle has no valid engine checkpoint.")
            return
        house = battle.get("house") or battle.get("accepted_by") or battle.get("to") or battle.get("from")
        guest = battle.get("guest") or (battle.get("to") if house == battle.get("from") else battle.get("from"))
        battle["house"], battle["guest"] = house, guest
        self.app.push(DuelScene(self.app, guest, "player", battle.get("place"), False, battle, session))

    def draw(self, surface):
        place = self.app.store.places.get(self.app.store.role_config()["default_place"])
        self.draw_background(surface, place.background if place else "")
        overlay = ui_surface((W, H), pygame.SRCALPHA); overlay.fill((247, 227, 177, 42)); ui_blit(surface, overlay, (0, 0))
        draw_text(surface, "LIVE DUEL WATCHING", (34, 30), self.app.assets.font(27, True), COLORS["gold"])
        draw_text(surface, "Choose an active duel to watch live from the house player’s perspective.", (36, 66), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (38, 112, 724, 370), "ACTIVE LIVE DUELS", COLORS["violet"])
        if not self.battle_rows:
            draw_text(surface, "No active duels are currently available to watch.", (400, 280), self.app.assets.font(15), COLORS["muted"], "center")
        for index, battle in enumerate(self.battle_rows[:4]):
            y = 142 + index * 76
            house = self.battle_participant(battle, "house")
            guest = self.battle_participant(battle, "guest")
            house_name = house.name if house else battle.get("house", "unknown")
            guest_name = guest.name if guest else battle.get("guest", "unknown")
            rounded(surface, (58, y, 520, 54), (132, 94, 73), COLORS["line"], 7, 1)
            draw_text(surface, f"HOUSE  {house_name}  VS  {guest_name}", (74, y + 10), self.app.assets.font(13, True), COLORS["cream"])
            draw_text(surface, f"Turn {battle.get('turn', 1)}  |  {str(battle.get('phase', 'duel')).upper()}  |  {len(battle.get('actions', []))} live engine steps", (74, y + 33), self.app.assets.font(10), COLORS["muted"])
        self.draw_buttons(surface, 10)
        self.app.draw_notice(surface)


class Application:
    def __init__(self):
        ensure_dirs()
        pygame.init()
        try: pygame.mixer.init()
        except pygame.error: pass
        pygame.display.set_caption("Cards Battlers Playgrounds")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.store = ContentStore()
        self.screen = pygame.display.set_mode(self.window_size(), pygame.FULLSCREEN if self.store.save_data.get("fullscreen", False) else pygame.RESIZABLE)
        self.render_surface = pygame.Surface((RENDER_W, RENDER_H))
        self.assets = AssetBank()
        self.assets.load_images()
        self.assets.load_sounds()
        self.scenes = []
        self.running = True
        self.notice = ""
        self.notice_time = 0
        self.simulation_accumulator = 0.0
        self.replace(SplashScene(self))

    def clock_text(self): return time.strftime("%H:%M")

    def push(self, scene):
        self.scenes.append(scene)
        scene.enter()

    def pop(self):
        if len(self.scenes) > 1:
            self.scenes.pop()
            self.scenes[-1].enter()

    def replace(self, scene):
        self.scenes = [scene]
        scene.enter()

    def open_target(self, target):
        mapping = {"battle": BattleScene, "cards": CardsScene, "characters": CharactersScene, "places": PlacesScene, "settings": SettingsScene}
        self.push(mapping[target](self))

    def notify(self, message):
        self.notice = message
        self.notice_time = 3.5

    def draw_notice(self, surface):
        if self.notice_time > 0:
            rounded(surface, (172, 476, 456, 42), (9, 18, 39), COLORS["gold"], 8, 2)
            draw_text(surface, self.notice, (400, 497), self.assets.font(11), COLORS["cream"], "center")

    def window_size(self):
        width, height = (800, 600) if self.store.save_data.get("resolution") == "800x600" else (1280, 720)
        return (width, height)

    def internal_size(self):
        return (RENDER_W, RENDER_H)
    def presentation_view(self):
        width, height = self.screen.get_size()
        scale = min(width / RENDER_W, height / RENDER_H)
        view_size = (max(1, int(RENDER_W * scale)), max(1, int(RENDER_H * scale)))
        view_position = ((width - view_size[0]) // 2, (height - view_size[1]) // 2)
        return view_position, view_size
    def window_to_scene(self, position):
        view_position, view_size = self.presentation_view()
        x, y = position
        if x < view_position[0] or y < view_position[1] or x >= view_position[0] + view_size[0] or y >= view_position[1] + view_size[1]: return (-1, -1)
        return (int((x - view_position[0]) * SCENE_W / view_size[0]), int((y - view_position[1]) * SCENE_H / view_size[1]))

    def cycle_resolution(self):
        self.store.save_data["resolution"] = "800x600" if self.store.save_data.get("resolution") == "1280x720" else "1280x720"
        flags = pygame.FULLSCREEN if self.store.save_data.get("fullscreen", False) else pygame.RESIZABLE
        self.screen = pygame.display.set_mode(self.window_size(), flags)
        self.store.save()

    def toggle_fullscreen(self):
        self.store.save_data["fullscreen"] = not self.store.save_data.get("fullscreen", False)
        flags = pygame.FULLSCREEN if self.store.save_data["fullscreen"] else pygame.RESIZABLE
        self.screen = pygame.display.set_mode(self.window_size(), flags)
        self.store.save()

    def toggle_music(self):
        self.store.save_data["music"] = not self.store.save_data.get("music", True)
        self.assets.play_music(self.store.save_data["music"], 0.35)
        self.store.save()

    def toggle_vocals(self):
        self.store.save_data["vocals"] = not self.store.save_data.get("vocals", True)
        self.store.save()

    def toggle_sfx(self):
        self.store.save_data["sfx"] = not self.store.save_data.get("sfx", True)
        self.store.save()

    def cycle_difficulty(self):
        levels = ["normal", "hard", "extreme"]
        current = self.store.save_data.get("difficulty", "normal")
        self.store.save_data["difficulty"] = levels[(levels.index(current) + 1) % len(levels)]
        self.store.save()

    def quit(self): self.running = False

    def run(self):
        self.assets.play_music(self.store.save_data.get("music", True), 0.35)
        while self.running:
            dt = self.clock.tick(FPS) / 1000
            if self.notice_time > 0: self.notice_time -= dt
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.quit()
                elif self.scenes:
                    if hasattr(event, "pos") and self.screen.get_width() and self.screen.get_height():
                        event = pygame.event.Event(event.type, {**event.dict, "pos": self.window_to_scene(event.pos)})
                    self.scenes[-1].handle(event)
            self.simulation_accumulator += dt
            if self.simulation_accumulator >= 1.0:
                elapsed = min(1.0, self.simulation_accumulator)
                self.simulation_accumulator -= elapsed
                self.store.advance_world(elapsed)
            if self.scenes: self.scenes[-1].update(dt)
            render_surface = self.render_surface
            render_surface.fill((0, 0, 0))
            if self.scenes: self.scenes[-1].draw(render_surface)
            scene_mouse = self.window_to_scene(pygame.mouse.get_pos())
            if scene_mouse != (-1, -1):
                cursor, hotspot = self.assets.cursor(cursor_pressed(pygame.mouse.get_pressed()))
                if cursor: ui_blit(render_surface, cursor, (scene_mouse[0] - hotspot[0], scene_mouse[1] - hotspot[1]))
            view_position, view_size = self.presentation_view()
            scaled = pygame.transform.smoothscale(render_surface, view_size)
            self.screen.fill((0, 0, 0))
            self.screen.blit(scaled, view_position)
            pygame.display.flip()
        self.store.save()
        pygame.quit()


if __name__ == "__main__":
    Application().run()
