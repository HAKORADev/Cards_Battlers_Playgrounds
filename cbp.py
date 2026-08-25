import os
import io
import json
import math
import random
import time
import zipfile
import re
import shutil
import subprocess
import wave
import hashlib
import struct
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
UNIVERSAL_ASSETS = DATA / "universal_assets"
UNIVERSAL_MAIN = UNIVERSAL_ASSETS / "main"
UNIVERSAL_PLACEHOLDER = UNIVERSAL_ASSETS / "placeholder"
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
DUEL_MODES = ["current", "timed", "gamble"]
DUEL_MODE_FORMATS = {"current": ["1v1", "1vTEAM", "TEAMv1", "TEAMvTEAM"], "timed": ["1v1"], "gamble": ["1v1"]}
CHARACTER_RUNTIME_FIELDS = {"mood", "mood_state", "allies", "enemies", "history", "relationship_history", "library_cards", "borrowed_cards", "rank", "relationship", "availability", "current_place", "destination", "movement_progress", "activity", "cooldown_until", "out_of_game_until", "world_status", "behavior_weights", "learned_cards", "learned_opponents", "knowledge_state", "learning_state", "experience", "goals", "memories", "persona_state", "idle_elapsed", "idle_cue_count"}
TEAM_RUNTIME_FIELDS = {"relationship", "team_effect", "rank", "history", "effect_locked", "behavior_weights", "knowledge_state", "learning_state", "experience", "formation_state", "formation_requests"}


def ensure_dirs():
    paths = [DATA, UNIVERSAL_ASSETS, UNIVERSAL_MAIN, UNIVERSAL_PLACEHOLDER, SCHEMAS, DATA / "cards", DATA / "characters", DATA / "teams", DATA / "places", DATA / "decks", DATA / "exports", RUNTIME_DIR, RUNTIME_CHARACTERS, RUNTIME_TEAMS, RUNTIME_WORLD, RUNTIME_WORLD_COLLECTIONS]
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
        source = font.render(str(text), True, color)
        image = pygame.transform.scale(source, size) if source.get_size() != size else source
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
        image = assets.image("placeholder/card_back") or assets.critical_image(layout_rect.size)
        if defense_position: image = pygame.transform.rotate(image, 90)
        blit_aspect(surface, image, layout_rect)
        return
    field_mode = not compact and layout_rect.width <= 100 and layout_rect.height <= 110
    template_kind = card_template_kind(card)
    template = assets.card_template(template_kind) or assets.critical_image(rect.size)
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
        art = assets.image("placeholder/card_art", art_rect.size)
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
            star_image = assets.image("card_frames/badges/star_level", native_star_size)
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
        self.media_images = {}
        self.media_sounds = {}
        self.media_video_frames = {}
        self.media_scopes = {}
        self.current_music_path = ""
        self.card_templates = {}
        self.card_badges = {}
        self.dice_faces = {}
        self.splash_names = []
        self.external_manifest = self.load_external_manifest()
        self.load_images()
        self.load_dice_faces()
        self.load_card_templates()
        self.load_sounds()

    def cursor(self, pressed=False):
        key = "cursor/click" if pressed else "cursor/normal"
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
        roots.extend([UNIVERSAL_MAIN, UNIVERSAL_PLACEHOLDER])
        return list(dict.fromkeys(roots))

    def manifest_path(self, role):
        external_root = os.environ.get("CBP_EXTERNAL_ASSET_ROOT", "").strip()
        relative = self.external_manifest.get("roles", {}).get(role, "")
        if not external_root or not relative: return None
        path = Path(external_root) / str(relative)
        return path if path.exists() else None

    def critical_image(self, size):
        key = ("critical", tuple(size))
        if key not in self.sized_images:
            image = pygame.Surface((max(1, int(size[0])), max(1, int(size[1]))), pygame.SRCALPHA)
            image.fill((255, 255, 255, 255))
            self.sized_images[key] = image
        return self.sized_images[key]

    def role_image(self, role, size=None, critical=False):
        image = self.role_images.get(role)
        if image is None and role not in self.role_images:
            path = self.manifest_path(role)
            image = None
            if path and path.exists():
                try: image = pygame.image.load(str(path)).convert_alpha()
                except pygame.error: image = None
            fallback_roles = {"place_ground": "duel/place_ground", "duel_environment": "duel/duel_environment", "table_frame": "duel/surfaces/table_frame", "duel_frame": "duel/surfaces/duel_frame", "field_surface": "duel/surfaces/field_surface"}
            if image is None: image = self.images.get(fallback_roles.get(role, role)) or self.images.get("placeholder/" + role)
            self.role_images[role] = image
        if image is None: return self.critical_image(size) if critical and size else None
        if size and image.get_size() != size:
            key = (role, tuple(size))
            if key not in self.sized_images: self.sized_images[key] = scaled_image(image, size)
            return self.sized_images[key]
        return image

    def load_dice_faces(self):
        self.dice_faces = {}
        for base in self.asset_roots():
            root = base / "dice" / "faces"
            for value in range(1, 7):
                path = root / f"{value}.png"
                if path.exists():
                    try: self.dice_faces[value] = pygame.image.load(str(path)).convert_alpha()
                    except pygame.error: pass
            if len(self.dice_faces) == 6: break

    def dice_face(self, value, size=None):
        image = self.dice_faces.get(max(1, min(6, int(value))))
        if image is None: return None
        return scaled_image(image, size) if size and image.get_size() != tuple(size) else image

    def load_card_templates(self):
        kinds = ["normal", "effect", "spell", "trap", "fusion", "ritual", "legendary"]
        for kind in kinds:
            for base in self.asset_roots():
                template_path = base / "card_frames" / f"{kind}_card_transparent.png"
                badge_path = base / "card_frames" / "badges" / f"{kind}.png"
                if kind not in self.card_templates and template_path.exists():
                    try: self.card_templates[kind] = pygame.image.load(str(template_path)).convert_alpha()
                    except pygame.error: pass
                if kind not in self.card_badges and badge_path.exists():
                    try: self.card_badges[kind] = pygame.image.load(str(badge_path)).convert_alpha()
                    except pygame.error: pass
                if kind in self.card_templates and kind in self.card_badges: break
    def card_template(self, kind):
        return self.card_templates.get("spell" if kind == "field" else kind) or self.card_templates.get("normal")
    def card_badge(self, kind):
        return self.card_badges.get("spell" if kind == "field" else kind)

    def load_images(self):
        self.splash_names = []
        for base in self.asset_roots():
            prefix = "placeholder/" if base == UNIVERSAL_PLACEHOLDER else ""
            for path in sorted(base.rglob("*.png")):
                relative = path.relative_to(base).with_suffix("")
                name = prefix + str(relative).replace(os.sep, "/")
                if name in self.images: continue
                try: self.images[name] = pygame.image.load(str(path)).convert_alpha()
                except pygame.error: continue
                if name.startswith("menu/splash/"): self.splash_names.append(name)
        self.splash_names = sorted(set(self.splash_names))

    def menu_layer(self, name, size=None):
        key = (name, tuple(size) if size else None)
        if key in self.menu_layers: return self.menu_layers[key]
        candidates = [UNIVERSAL_MAIN / "menu" / f"{name}.png", UNIVERSAL_MAIN / f"{name}.png"]
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
        sound_roots = {"menu_music": UNIVERSAL_MAIN / "audio" / "menu", "music_duel": UNIVERSAL_MAIN / "audio" / "duel"}
        root = sound_roots.get(name)
        if root:
            candidates.extend(sorted(path for path in root.glob("*") if path.is_file() and path.suffix.lower() in MediaRegistry.audio_extensions))
        return candidates

    def load_sounds(self):
        for name in ["menu_music", "music_duel"]:
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
            try: self.fonts[key] = pygame.font.SysFont(family, size, bold=bold)
            except pygame.error: self.fonts[key] = pygame.font.Font(None, max(1, int(size)))
        return self.fonts[key]

    def display_font(self, size, bold=True):
        key = ("display", size, bold)
        if key not in self.fonts:
            try: self.fonts[key] = pygame.font.SysFont("Noto Serif Display", size, bold=bold)
            except pygame.error: self.fonts[key] = pygame.font.Font(None, max(1, int(size)))
        return self.fonts[key]

    def fallback_sine(self, key="required"):
        cache_key = "__sine__" + str(key)
        if cache_key in self.sounds: return self.sounds[cache_key]
        if not pygame.mixer.get_init(): return None
        try:
            rate = 22050
            samples = int(rate * 0.18)
            raw = b"".join(struct.pack("<h", int(9000 * math.sin(2.0 * math.pi * 440.0 * index / rate))) for index in range(samples))
            sound = pygame.mixer.Sound(buffer=raw)
            self.sounds[cache_key] = sound
            return sound
        except (pygame.error, ValueError):
            return None

    def loop_music(self, path, enabled, volume, required=False):
        if not pygame.mixer.get_init():
            self.current_music_path = ""
            return False
        try:
            if not enabled:
                pygame.mixer.music.stop()
                self.current_music_path = ""
                return False
            if not path or not path.exists():
                if not required: return False
                fallback = self.fallback_sine("music")
                if fallback is None: return False
                fallback.set_volume(volume)
                fallback.play(-1)
                self.current_music_path = "__fallback_music__"
                return True
            if pygame.mixer.music.get_busy() and self.current_music_path == str(path):
                pygame.mixer.music.set_volume(volume)
                return True
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(-1)
            self.current_music_path = str(path)
            return True
        except pygame.error:
            self.current_music_path = ""
            return False
    def play_music(self, enabled, volume):
        candidates = self.sound_candidates("menu_music")
        path = next((item for item in candidates if item.exists()), None)
        self.loop_music(path, enabled, volume, True)
    def place_music_paths(self, place_id, state="duel", night=False):
        folder_candidates = [DATA / "places" / str(place_id)]
        period = "night" if night else "day"
        state_key = slug(state).replace("_", "-")
        aliases = {"duel": ["duel", "in-duel", "normal"], "in-duel": ["in-duel", "duel", "normal"], "pre-duel": ["pre-duel", "pre_duel"], "post-duel-win": ["post-duel-win", "post_duel/win", "win"], "post-duel-lose": ["post-duel-lose", "post_duel/lose", "lose"]}
        state_names = aliases.get(state_key, [state_key])
        roots = []
        for folder in folder_candidates:
            for state_name in state_names:
                roots.extend([folder / "music" / period / state_name, folder / "music" / state_name / period, folder / "music" / state_name])
            roots.append(folder / "music" / period)
            roots.append(folder / "music")
        for root in roots:
            tracks = sorted(path for path in root.glob("*") if path.is_file() and path.suffix.lower() in MediaRegistry.audio_extensions and self._numeric_media_index(path) is not None)
            if not tracks: tracks = sorted(path for path in root.glob("*") if path.is_file() and path.suffix.lower() in MediaRegistry.audio_extensions)
            if tracks: return tracks[:10]
        universal_roots = [UNIVERSAL_MAIN / "audio" / "duel" / period / state_key, UNIVERSAL_MAIN / "audio" / "duel" / state_key, UNIVERSAL_MAIN / "audio" / "duel"]
        for root in universal_roots:
            tracks = sorted(path for path in root.glob("*") if path.is_file() and path.suffix.lower() in MediaRegistry.audio_extensions)
            if tracks: return tracks[:10]
        return []

    def _numeric_media_index(self, path):
        match = re.fullmatch(r"(10|[1-9])", Path(path).stem)
        return int(match.group(1)) if match else None

    def place_music_path(self, place_id, night=False, state="duel", variant=None):
        paths = self.place_music_paths(place_id, state, night)
        if not paths: return None
        if variant is not None:
            return paths[max(0, int(variant) - 1) % len(paths)]
        return random.choice(paths)

    def play_duel_music(self, place_id, enabled, volume=0.35, night=False, state="duel", variant=None):
        return self.loop_music(self.place_music_path(place_id, night, state, variant), enabled, volume, False)

    def place_media_roots(self, place_id):
        direct = DATA / "places" / str(place_id)
        return [direct] if direct.exists() else []

    def place_visual_path(self, place_id, kind="background", night=False):
        period = "night" if night else "day"
        roots = []
        for folder in self.place_media_roots(place_id):
            roots.extend([folder / kind / period, folder / kind])
        for root in roots:
            files = sorted(path for path in root.glob("*") if path.is_file() and path.suffix.lower() in (MediaRegistry.image_extensions | MediaRegistry.video_extensions))
            if files: return files[0]
        return None

    def place_visual(self, place_id, kind="background", night=False, clock=0.0, size=None, scope="scene"):
        path = self.place_visual_path(place_id, kind, night)
        if not path: return None
        if path.suffix.lower() in MediaRegistry.video_extensions: return self.media_video_frame(path, clock, size, scope)
        return self.media_image(path, size, scope)

    def media_image(self, path, size=None, scope="scene"):
        if not path or not Path(path).exists(): return None
        key = str(path)
        image = self.media_images.get(key)
        if image is None:
            try: image = pygame.image.load(key).convert_alpha()
            except pygame.error: return None
            if len(self.media_images) >= 256: self.media_images.pop(next(iter(self.media_images)))
            self.media_images[key] = image
        if scope: self.media_scopes.setdefault(scope, set()).add(key)
        return scaled_image(image, size) if size and image.get_size() != tuple(size) else image

    def media_video_frame(self, path, clock=0.0, size=None, scope="scene"):
        if not path or not Path(path).exists(): return None
        key = (str(path), int(max(0.0, float(clock)) * FPS))
        image = self.media_video_frames.get(key)
        if image is None:
            try:
                result = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(max(0.0, float(clock))), "-i", str(path), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"], capture_output=True, timeout=3)
                if result.returncode != 0 or not result.stdout: return None
                image = pygame.image.load(io.BytesIO(result.stdout)).convert_alpha()
            except (OSError, pygame.error, subprocess.SubprocessError): return None
            if len(self.media_video_frames) >= 128: self.media_video_frames.pop(next(iter(self.media_video_frames)))
            self.media_video_frames[key] = image
        if scope: self.media_scopes.setdefault(scope, set()).add(str(path))
        return scaled_image(image, size) if size and image.get_size() != tuple(size) else image

    def media_sound(self, path, scope="scene"):
        if not path or not Path(path).exists(): return None
        key = str(path)
        sound = self.media_sounds.get(key)
        if sound is None:
            try: sound = pygame.mixer.Sound(key)
            except pygame.error: return None
            if len(self.media_sounds) >= 128: self.media_sounds.pop(next(iter(self.media_sounds)))
            self.media_sounds[key] = sound
        if scope: self.media_scopes.setdefault(scope, set()).add(key)
        return sound

    def character_portrait(self, character, size=None):
        root = DATA / getattr(character, "media_folder", "")
        candidates = [root / "pfp" / "variants" / f"1{extension}" for extension in MediaRegistry.image_extensions] + [root / "pfp" / f"1{extension}" for extension in MediaRegistry.image_extensions]
        image = None
        for path in candidates:
            image = self.media_image(path, size, "portrait")
            if image is not None: break
        if image is None: image = self.image("placeholder/character_pfp", size)
        return image

    def team_portrait(self, team, size=None):
        root = DATA / getattr(team, "media_folder", "")
        candidates = [root / "pfp" / "variants" / f"1{extension}" for extension in MediaRegistry.image_extensions] + [root / "pfp" / f"1{extension}" for extension in MediaRegistry.image_extensions]
        image = None
        for path in candidates:
            image = self.media_image(path, size, "portrait")
            if image is not None: break
        return image or self.image("placeholder/deck_pfp", size) or self.image("placeholder/character_pfp", size)

    def deck_portrait(self, deck, size=None):
        folder = deck.get("media_folder", "") if isinstance(deck, dict) else ""
        root = DATA / folder
        for path in [root / "pfp" / "variants" / "1.png", root / "pfp" / "1.png"]:
            image = self.media_image(path, size, "portrait")
            if image is not None: return image
        return self.image("placeholder/deck_pfp", size) or self.image("placeholder/character_pfp", size)

    def release_media_scope(self, scope):
        keys = self.media_scopes.pop(scope, set())
        for key in keys:
            self.media_images.pop(key, None)
            self.media_sounds.pop(key, None)
            self.reaction_sounds.pop(key, None)
            for frame_key in [item for item in self.media_video_frames if item[0] == key]: self.media_video_frames.pop(frame_key, None)
            FILE_IMAGE_CACHE.pop(key, None)

    def play_reaction_audio(self, path, enabled=True, volume=0.8, scope="scene"):
        if not enabled or not path or not Path(path).exists(): return False
        try:
            sound = self.media_sound(path, scope) or self.reaction_sounds.get(str(path))
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
    subtypes: list = field(default_factory=list)
    legendary_type: str = ""
    non_removable: bool = False
    distribution: dict = field(default_factory=dict)


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
    description: str = ""
    preferred_card_kinds: list = field(default_factory=list)
    preferred_subtypes: list = field(default_factory=list)
    preferred_cards: list = field(default_factory=list)
    preferred_places: list = field(default_factory=list)
    technique_profile: dict = field(default_factory=dict)
    cognition: dict = field(default_factory=dict)
    learning_policy: dict = field(default_factory=dict)
    state_rules: dict = field(default_factory=dict)
    relationship_history: list = field(default_factory=list)
    mood_state: dict = field(default_factory=dict)
    knowledge_state: dict = field(default_factory=dict)
    learning_state: dict = field(default_factory=dict)
    experience: dict = field(default_factory=dict)
    logic_graph: str = ""
    out_of_game_until: float = 0.0
    world_status: str = "in_playground"
    goals: list = field(default_factory=list)
    memories: list = field(default_factory=list)
    persona_state: dict = field(default_factory=dict)
    idle_elapsed: float = 0.0
    idle_cue_count: int = 0


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
    logic_graph: str = ""
    description: str = ""
    history: list = field(default_factory=list)
    linked_teams: list = field(default_factory=list)


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
    portrait: str = ""
    description: str = ""
    preferred_families: list = field(default_factory=list)
    preferred_card_kinds: list = field(default_factory=list)
    preferred_cards: list = field(default_factory=list)
    behavior_weights: dict = field(default_factory=dict)
    knowledge_state: dict = field(default_factory=dict)
    learning_state: dict = field(default_factory=dict)
    experience: dict = field(default_factory=dict)
    logic_graph: str = ""
    formation_state: str = "complete"
    formation_requests: list = field(default_factory=list)
    distribution: dict = field(default_factory=dict)


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


@dataclass
class MediaVariant:
    variant: int
    frames: list = field(default_factory=list)
    audio: str = ""
    video: str = ""
    duration: float = 0.0
    animation_duration: float = 0.0
    source: str = ""


class MediaRegistry:
    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    audio_extensions = {".wav", ".ogg", ".mp3", ".flac", ".m4a"}
    video_extensions = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".gif"}
    variant_pattern = re.compile(r"(10|[1-9])$")

    def __init__(self, root):
        self.root = Path(root)
        self.data_root = self.root / "data" if (self.root / "data").exists() else self.root
        self.catalog = {"images": [], "audio": [], "video": [], "timelines": []}
        self.variant_cache = {}
        self.duration_cache = {}
        self.scan()

    def scan(self):
        self.catalog = {"images": [], "audio": [], "video": [], "timelines": []}
        for path in self.data_root.rglob("*"):
            if not path.is_file(): continue
            suffix = path.suffix.lower()
            if suffix in self.image_extensions: self.catalog["images"].append(str(path))
            elif suffix in self.audio_extensions: self.catalog["audio"].append(str(path))
            elif suffix in self.video_extensions: self.catalog["video"].append(str(path))
            elif path.name.endswith("timeline.json"): self.catalog["timelines"].append(str(path))
        for values in self.catalog.values(): values[:] = sorted(set(values))
        self.variant_cache.clear()
        return self.catalog

    def entity_path(self, entity_type, entity_id):
        base = self.data_root / entity_type
        direct = base / entity_id
        if direct.exists(): return direct
        for folder in base.glob("*"):
            manifest = folder / "manifest.json"
            if manifest.exists():
                try:
                    if json.loads(manifest.read_text(encoding="utf-8")).get("id") == entity_id: return folder
                except (OSError, ValueError): pass
        return direct

    def entity_files(self, entity_id, category):
        return [path for path in self.catalog.get(category, []) if entity_id in Path(path).parts or entity_id in Path(path).stem]

    def card_art(self, card, variant=1):
        root = self.data_root / (card.media_folder or card.art_folder)
        candidates = [root / "art" / "variants" / f"{int(variant)}.png", root / "art" / "variants" / f"{int(variant)}.jpg", root / "images" / f"{int(variant)}.png", root / "images" / f"{int(variant)}.jpg"]
        for candidate in candidates:
            if candidate.exists(): return str(candidate)
        return ""

    def _numeric_files(self, folder, extensions):
        found = {}
        folder = Path(folder)
        if not folder.exists(): return found
        for path in folder.iterdir():
            if not path.is_file() or path.suffix.lower() not in extensions: continue
            match = self.variant_pattern.fullmatch(path.stem)
            if match: found[int(match.group(1))] = str(path)
        return found

    def _variant_ids(self, animation_root, audio_root):
        ids = set()
        for root in [Path(animation_root), Path(audio_root)]:
            if not root.exists(): continue
            for path in root.iterdir():
                if path.is_dir() and self.variant_pattern.fullmatch(path.name): ids.add(int(path.name))
                elif path.is_file() and self.variant_pattern.fullmatch(path.stem): ids.add(int(path.stem))
        return sorted(ids)

    def media_duration(self, path):
        if not path: return 0.0
        path = str(path)
        if path in self.duration_cache: return self.duration_cache[path]
        duration = 0.0
        try:
            if pygame.mixer.get_init(): duration = float(pygame.mixer.Sound(path).get_length())
        except (pygame.error, OSError): duration = 0.0
        if duration <= 0 and Path(path).suffix.lower() == ".wav":
            try:
                with wave.open(path, "rb") as stream: duration = stream.getnframes() / max(1, stream.getframerate())
            except (EOFError, OSError, wave.Error): duration = 0.0
        if duration <= 0 and Path(path).suffix.lower() in self.video_extensions:
            try:
                result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True, timeout=2)
                duration = float(result.stdout.strip() or 0.0)
            except (OSError, ValueError, subprocess.SubprocessError): duration = 0.0
        self.duration_cache[path] = max(0.0, duration)
        return self.duration_cache[path]

    def variants(self, animation_root, audio_root=None):
        animation_root = Path(animation_root)
        audio_root = Path(audio_root or animation_root)
        key = (str(animation_root), str(audio_root))
        if key in self.variant_cache: return self.variant_cache[key]
        variants = []
        flat_frames = self._numeric_files(animation_root, self.image_extensions)
        flat_audio = self._numeric_files(audio_root, self.audio_extensions)
        if audio_root != animation_root: flat_audio.update(self._numeric_files(animation_root, self.audio_extensions))
        flat_sequence = bool(flat_frames and flat_audio)
        for variant_id in self._variant_ids(animation_root, audio_root):
            animation_folder = animation_root / str(variant_id) if (animation_root / str(variant_id)).is_dir() else animation_root
            frames = [path for _, path in sorted(self._numeric_files(animation_folder, self.image_extensions).items())]
            if animation_folder == animation_root:
                direct = [path for index, path in flat_frames.items() if index == variant_id]
                frames = list(flat_frames.values()) if flat_sequence else direct or frames
            video_files = [path for path in [animation_root / f"{variant_id}{suffix}" for suffix in self.video_extensions] if path.exists()]
            if not video_files and animation_folder != animation_root:
                video_files = [str(path) for path in animation_folder.iterdir() if path.is_file() and path.suffix.lower() in self.video_extensions and not self.variant_pattern.fullmatch(path.stem)]
            if video_files: frames = []
            audio = flat_audio.get(variant_id, "")
            if not audio and animation_folder != animation_root:
                nested_audio = [str(path) for path in animation_folder.iterdir() if path.is_file() and path.suffix.lower() in self.audio_extensions]
                audio = nested_audio[0] if nested_audio else ""
            if not frames and not video_files and not audio: continue
            duration = self.media_duration(audio) if audio else self.media_duration(video_files[0]) if video_files else 0.0
            variants.append(MediaVariant(variant_id, frames, audio, str(video_files[0]) if video_files else "", duration, len(frames) / FPS if frames else duration, str(animation_root)))
        self.variant_cache[key] = variants[:10]
        return self.variant_cache[key]

    def _pairs(self, animation_root, audio_root):
        pairs = []
        for pair in [(animation_root, audio_root)]:
            animation_root, audio_root = Path(pair[0]), Path(pair[1])
            if animation_root.exists() or audio_root.exists(): pairs.append((animation_root, audio_root))
        return pairs

    def event_aliases(self, event):
        raw = str(event or "idle").strip().lower().replace(" ", "-").replace("_", "-")
        return [raw]

    def candidate_pairs(self, event, relation, entity_type, entity_id, place_id, actor_id=""):
        pairs = []
        events = self.event_aliases(event)
        for event_name in events:
            pairs.extend(self._candidate_pairs_for_event(event_name, relation, entity_type, entity_id, place_id, actor_id))
        return list(dict.fromkeys(pairs))

    def _candidate_pairs_for_event(self, event, relation, entity_type, entity_id, place_id, actor_id=""):
        pairs = []
        alias_event = str(event).replace("_", "-")
        if alias_event != str(event): pairs.extend(self._candidate_pairs_for_event(alias_event, relation, entity_type, entity_id, place_id, actor_id))
        def add(animation_root, audio_root=None):
            for pair in self._pairs(animation_root, audio_root or animation_root):
                if pair not in pairs: pairs.append(pair)
        if entity_type == "characters" and entity_id:
            root = self.entity_path("characters", entity_id)
            relation_names = dict.fromkeys([relation, "opponent" if relation == "stranger" else "stranger", "neutral"])
            for relation_name in relation_names:
                add(root / "duel" / "reactions" / relation_name / event, root / "duel" / "reactions" / relation_name / event / "audio")
                add(root / "duel" / "reactions" / relation_name / event / "animations", root / "duel" / "reactions" / relation_name / event / "audio")
                add(root / "duel" / relation_name / event / "animations", root / "duel" / relation_name / event / "audio")
                add(root / "animations" / event / relation_name, root / "audio" / event / relation_name)
                add(root / "animations" / "battle" / event / relation_name, root / "audio" / "battle" / event / relation_name)
            add(root / "animations" / event, root / "audio" / event)
            add(root / "animations" / "battle" / event, root / "audio" / "battle" / event)
            add(root / "duel" / event / "animations", root / "duel" / event / "audio")
            add(root / "duel" / "interactions" / event / "animations", root / "duel" / "interactions" / event / "audio")
            add(root / "animations" / "left" / event, root / "audio" / "left" / event)
            add(root / "animations" / "right" / event, root / "audio" / "right" / event)
        if entity_type == "cards" and actor_id:
            character_root = self.entity_path("characters", actor_id)
            card_root = self.entity_path("cards", entity_id) if entity_id else self.data_root / "cards"
            card_folder = card_root.name
            relation_names = dict.fromkeys([relation, "opponent" if relation == "stranger" else "stranger", "neutral"])
            for relation_name in relation_names:
                add(character_root / "duel" / "reactions" / relation_name / event, character_root / "duel" / "reactions" / relation_name / event / "audio")
                add(character_root / "cards" / card_folder / relation_name / event / "animations", character_root / "cards" / card_folder / relation_name / event / "audio")
            add(character_root / "cards" / card_folder / event / "animations", character_root / "cards" / card_folder / event / "audio")
            add(character_root / "animations" / event, character_root / "audio" / event)
        if entity_type == "cards" and entity_id:
            root = self.entity_path("cards", entity_id)
            add(root / "interactions" / event / "animations", root / "interactions" / event / "audio")
            add(root / "animations" / event, root / "audio" / event)
        if entity_type == "places" and entity_id:
            root = self.entity_path("places", entity_id)
            add(root / "presentation" / event / "animations", root / "presentation" / event / "audio")
            add(root / "animations" / event, root / "audio" / event)
        if place_id:
            root = self.entity_path("places", place_id)
            add(root / "presentation" / event / "animations", root / "presentation" / event / "audio")
            add(root / "animations" / event, root / "audio" / event)
        add(self.data_root / "universal_assets" / "main" / "duel" / event, self.data_root / "universal_assets" / "main" / "duel" / event / "audio")
        return list(dict.fromkeys(pairs))

    def vfx_path(self, effect="attack", card_id="", actor_id=""):
        effect = str(effect or "attack").strip().lower().replace(" ", "-").replace("_", "-")
        candidates = []
        if card_id:
            card_root = self.entity_path("cards", card_id)
            candidates.extend([card_root / "interactions" / effect / "vfx.png", card_root / "interactions" / effect / "animations" / "vfx.png", card_root / "effects" / effect / "vfx.png"])
            for suffix in self.image_extensions:
                candidates.extend([card_root / "interactions" / effect / ("effect" + suffix), card_root / "interactions" / effect / "vfx" / ("effect" + suffix), card_root / "interactions" / effect / "vfx" / ("vfx" + suffix)])
        if actor_id:
            actor_root = self.entity_path("characters", actor_id)
            candidates.extend([actor_root / "duel" / "vfx" / effect / "1.png", actor_root / "duel" / "effects" / effect / "1.png"])
        candidates.extend([self.data_root / "universal_assets" / "main" / "duel" / effect / "sword.png", self.data_root / "universal_assets" / "main" / "duel" / effect / "1.png", self.data_root / "universal_assets" / "main" / "duel" / effect / "universal.png"])
        for path in candidates:
            if path.exists() and path.is_file() and path.suffix.lower() in self.image_extensions: return str(path)
        return ""

    def resolve(self, event, actor_id="", target_id="", relation="opponent", entity_type="characters", entity_id="", place_id="", mode="hang", variant=None, metadata=None):
        entity_id = entity_id or actor_id
        base_pairs = self.candidate_pairs(event, relation, entity_type, entity_id, place_id, actor_id if entity_type == "cards" else "")
        pairs = []
        amount = (metadata or {}).get("amount") if isinstance(metadata, dict) else None
        if amount is not None:
            try: amount_key = ("+" if float(amount) >= 0 else "-") + str(abs(int(float(amount))))
            except (TypeError, ValueError): amount_key = ""
            if amount_key:
                for animation_root, audio_root in base_pairs:
                    pairs.append((Path(animation_root) / amount_key, Path(audio_root) / amount_key))
        pairs.extend(base_pairs)
        for animation_root, audio_root in pairs:
            options = self.variants(animation_root, audio_root)
            if not options: continue
            selected = next((item for item in options if item.variant == int(variant)), None) if variant is not None else None
            if selected is None:
                paired = [item for item in options if item.audio and (item.frames or item.video)]
                selected = random.choice(paired or options)
            direct_images = self._numeric_files(Path(selected.source), self.image_extensions)
            preview = direct_images.get(selected.variant, selected.frames[0] if selected.frames else "")
            return ReactionSelection(event, actor_id, target_id, relation, selected.source, selected.variant, preview, selected.audio, mode, False, selected.frames, selected.video, selected.duration, selected.animation_duration, FPS, mode)
        return ReactionSelection(event, actor_id, target_id, relation, "placeholder", 0, "", "", mode, True)

    def timed_media(self, root, now=None):
        root = Path(root)
        current = now or time.localtime()
        month, day, hour = int(current.tm_mon), int(current.tm_mday), int(current.tm_hour)
        candidates = []
        for path in root.rglob("*") if root.exists() else []:
            if not path.is_file() or path.suffix.lower() not in (self.image_extensions | self.audio_extensions | self.video_extensions): continue
            relative = str(path.relative_to(root)).replace("\\", "/").lower()
            score = 0
            date_tokens = [f"{month}/{day}", f"{month:02d}/{day:02d}", f"{month}-{day}", f"{month:02d}-{day:02d}"]
            if any(token in relative for token in date_tokens): score = max(score, 100)
            for token in re.findall(r"(?:^|/)(\d{1,2})-(\d{1,2})(?:\.|/|$)", relative):
                start, finish = map(int, token)
                active = start <= hour <= finish if start <= finish else hour >= start or hour <= finish
                if active: score = max(score, 80)
            if any(token in relative for token in [f"/{hour}/", f"/{hour:02d}/", f"/{hour}-", f"/{hour:02d}-"]): score = max(score, 60)
            if any(token in relative for token in ["default", "any", "idle"]): score = max(score, 1)
            candidates.append((score, relative, path))
        matching = [item for item in candidates if item[0] > 0]
        return [item[2] for item in sorted(matching or candidates, key=lambda item: (-item[0], item[1]))]

    def summary(self):
        return {key: len(value) for key, value in self.catalog.items()}


class ReactionResolver:
    image_extensions = MediaRegistry.image_extensions
    audio_extensions = MediaRegistry.audio_extensions

    def __init__(self, registry):
        self.registry = registry

    def numbered(self, folder, extensions):
        return self.registry._numeric_files(folder, extensions)

    def resolve(self, event, actor_id="", target_id="", relation="opponent", entity_type="characters", entity_id="", place_id="", mode="hang", variant=None, metadata=None):
        mode = mode if mode in ["loop", "hang", "strict-sync"] else "hang"
        return self.registry.resolve(event, actor_id, target_id, relation, entity_type, entity_id, place_id, mode, variant, metadata)


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
    frames: list = field(default_factory=list)
    video: str = ""
    duration: float = 0.0
    animation_duration: float = 0.0
    frame_rate: float = FPS
    sync: str = "hang"
    presentation: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw):
        fields = {"event", "actor_id", "target_id", "relation", "source", "variant", "image", "audio", "mode", "placeholder", "frames", "video", "duration", "animation_duration", "frame_rate", "sync", "presentation", "metadata"}
        data = {key: raw[key] for key in fields if key in raw}
        data.setdefault("event", raw.get("cue", "media"))
        data.setdefault("actor_id", "")
        data.setdefault("target_id", "")
        data.setdefault("relation", "opponent")
        data.setdefault("source", "effect")
        data.setdefault("variant", 0)
        return cls(**data)

    def to_dict(self):
        return self.__dict__.copy()


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
        self.frame_count = max(1, len(selection.frames) or (1 if selection.image or selection.video else 0))
        audio_duration = max(0.0, float(selection.duration or 0.0))
        animation_duration = max(0.0, float(selection.animation_duration or 0.0))
        if selection.frames and animation_duration <= 0: animation_duration = len(selection.frames) / max(1.0, float(selection.frame_rate or FPS))
        fallback_duration = 0.35 if selection.placeholder else float(duration or 2.0)
        self.duration = max(0.05, audio_duration, animation_duration) if audio_duration or animation_duration else max(0.05, fallback_duration)
        self.finished = False

    def update(self, dt):
        if not self.selection or self.finished: return
        self.clock += max(0.0, float(dt))
        if self.clock >= self.duration: self.finished = True

    def frame_index(self):
        if not self.selection or self.frame_count <= 1: return 0
        if self.selection.sync == "strict-sync": return min(self.frame_count - 1, int(self.clock / max(0.01, self.duration) * self.frame_count))
        frame_clock = self.clock * max(1.0, float(self.selection.frame_rate or FPS))
        if self.selection.mode == "loop": return int(frame_clock) % self.frame_count
        return min(self.frame_count - 1, int(frame_clock))

    def state(self):
        if not self.selection: return {"active": False}
        index = self.frame_index()
        frame_path = self.selection.frames[index] if self.selection.frames and index < len(self.selection.frames) else self.selection.image
        return {"active": not self.finished, "event": self.selection.event, "variant": self.selection.variant, "image": frame_path, "frames": list(self.selection.frames), "video": self.selection.video, "mode": self.selection.mode, "sync": self.selection.sync, "placeholder": self.selection.placeholder, "clock": round(self.clock, 3), "duration": round(self.duration, 3), "frame_count": self.frame_count, "frame_index": index, "audio": self.selection.audio, "sync_ratio": round(self.frame_count / max(0.01, self.duration), 3)}


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
    optional: bool = False

    action_names = {"boost_attack", "boost_defense", "damage", "heal", "draw", "discard", "grant_normal_summon", "banish", "send_to_graveyard", "return_to_hand", "set_face_up", "set_face_down", "switch_position", "destroy", "control", "summon", "special_summon", "fusion_summon", "ritual_summon", "negate_chain", "shuffle"}
    implemented_actions = {"boost_attack", "boost_defense", "damage", "heal", "draw", "discard", "grant_normal_summon", "banish", "send_to_graveyard", "return_to_hand", "set_face_up", "set_face_down", "switch_position", "destroy", "control", "summon", "special_summon", "fusion_summon", "ritual_summon", "negate_chain", "shuffle"}
    phases = {"draw", "standby", "main", "battle", "end", "any"}
    once_policies = {"", "once", "once_per_duel", "once_per_turn", "per_turn"}

    @classmethod
    def from_dict(cls, data, fallback_id="effect"):
        raw = dict(data or {})
        trigger = str(raw.get("trigger", ""))
        window = dict(raw.get("window") or {})
        actions = []
        for action in raw.get("actions", []) or []:
            item = dict(action) if isinstance(action, dict) else {"name": ""}
            item["name"] = str(item.get("name", "")).strip().lower()
            item["valid"] = item["name"] in cls.action_names
            actions.append(item)
        selector = dict(raw.get("selector") or {})
        targets = list(raw.get("targets") or [])
        target_policy = dict(raw.get("target_policy") or {})
        response = dict(raw.get("response") or {})
        speed = int(raw.get("speed", 1) or 0)
        modifier = dict(raw.get("modifier") or {})
        return cls(str(raw.get("id", "")), trigger, window, list(raw.get("conditions", []) or []), list(raw.get("cost", []) or []), selector, targets, actions, modifier, str(raw.get("once", "")), int(raw.get("priority", 0) or 0), dict(raw.get("notify") or {}), dict(raw.get("media") or {}), target_policy, speed, response, bool(raw.get("optional", False)))

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
        return {"id": self.effect_id, "trigger": self.trigger, "window": self.window, "conditions": self.conditions, "cost": self.costs, "selector": self.selector, "targets": self.targets, "actions": self.actions, "modifier": self.modifier, "optional": self.optional, "once": self.once, "priority": self.priority, "notify": self.notify, "media": self.media, "target_policy": self.target_policy, "speed": self.speed, "response": self.response}


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
    enabler: dict = field(default_factory=dict)
    source_zones: list = field(default_factory=list)

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
        source_zones = list(raw.get("source_zones", ["extra"] if kind == "fusion" else ["hand"]) or [])
        enabler = dict(raw.get("enabler") or {})
        return cls(kind, selector, required, minimum, locations, exact, destination, source_selector, source_method, required_count, list(costs), bool(raw.get("special", False)), enabler, source_zones)


class LogicRuntime:
    action_names = {"boost_attack", "boost_defense", "damage", "heal", "draw", "banish", "send_to_graveyard", "return_to_hand"}
    node_kinds = {"trigger", "condition", "action"}

    def __init__(self, graphs):
        self.graphs = graphs

    @classmethod
    def normalize_action(cls, value):
        text = str(value or "").strip().lower()
        match = re.fullmatch(r"([a-z_]+)\s*([+-]?\d+)?", text)
        if not match: return {"name": "", "amount": 0, "raw": text, "valid": False}
        name, amount = match.groups()
        return {"name": name, "amount": int(amount or 0), "raw": text, "valid": name in cls.action_names}

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
    def __init__(self, epoch=None):
        self.epoch = float(epoch if epoch is not None else time.time())

    def now(self, simulation_time=None):
        current = time.localtime() if simulation_time is None else time.localtime(self.epoch + max(0.0, float(simulation_time)))
        return {"year": current.tm_year, "month": current.tm_mon, "day": current.tm_mday, "hour": current.tm_hour, "minute": current.tm_min}

    def period(self, simulation_time=None):
        hour = self.now(simulation_time)["hour"]
        return "night" if hour < 6 or hour >= 18 else "day"

    def label(self, simulation_time=None):
        if simulation_time is None: return time.strftime("%Y-%m-%d %H:%M")
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.epoch + max(0.0, float(simulation_time))))


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
        self.narrator_data = {"states": {}}
        for narrator_path in sorted((DATA / "characters" / "narrator" / "catalogs").glob("*.json")):
            catalog = read_json(narrator_path, {})
            if isinstance(catalog, dict) and isinstance(catalog.get("states"), dict): self.narrator_data["states"].update(catalog["states"])
        self.narrator_sequence = 0
        self.clock = WorldClock()
        self.dirty_domains = set()
        self.world_tick_active = False
        self.world_checkpoint_elapsed = 0.0
        self.world_checkpoint_interval = 15.0
        self.world_sessions = {}
        self.world_team_sessions = {}
        self.rules = read_json(DATA / "rules.json", {})
        DeckRules.configure(self.rules)
        self.world = {}
        self.load()

    def spin_dice_result(self, launcher_id, requester_id):
        sequence = int(self.world.get("dice_sequence", 0)) + 1
        self.world["dice_sequence"] = sequence
        seed = int(self.world.get("simulation_time", 0.0) * 1000) + sequence * 104729 + sum(ord(char) for char in str(launcher_id) + str(requester_id))
        value = random.Random(seed).randint(1, 6)
        first_id = launcher_id if value <= 3 else requester_id
        result = {"type": "spin_dice_result", "sequence": sequence, "launcher": launcher_id, "requester": requester_id, "value": value, "range": "launcher" if value <= 3 else "requester", "first": first_id, "sim_time": float(self.world.get("simulation_time", 0.0))}
        self.world.setdefault("simulation_events", []).append(result)
        return result

    def narrator_cue(self, state, actor_id="", target_id="", context=None):
        states = self.narrator_data.get("states", {}) if isinstance(self.narrator_data, dict) else {}
        entry = states.get(str(state), {}) if isinstance(states, dict) else {}
        texts = list(entry.get("texts", [])) if isinstance(entry, dict) else []
        self.narrator_sequence += 1
        index = (self.narrator_sequence - 1) % len(texts) if texts else 0
        text = texts[index] if texts else str(state).replace("_", " ").title()
        audio_root = str(entry.get("audio_root", "")) if isinstance(entry, dict) else ""
        audio_paths = []
        if audio_root:
            root = DATA / "characters" / "narrator" / audio_root
            audio_paths = sorted(path for path in root.glob("*") if path.is_file() and path.suffix.lower() in MediaRegistry.audio_extensions)
        audio = str(audio_paths[index % len(audio_paths)]) if audio_paths else ""
        cue = {"type": "narrator_cue", "state": str(state), "text": text, "audio": audio, "variant": index + 1, "actor": actor_id, "target": target_id, "context": dict(context or {}), "sim_time": float(self.world.get("simulation_time", 0.0))}
        self.world.setdefault("simulation_events", []).append(cue)
        return cue

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

    def load_world_state(self):
        stored = read_json(RUNTIME_WORLD_INDEX, {}) if RUNTIME_WORLD_INDEX.exists() else {}
        state = stored.get("state", stored) if isinstance(stored, dict) else {}
        state = dict(state) if isinstance(state, dict) else {}
        for key in ["requests", "orders", "team_requests", "team_effect_requests", "place_effects", "championships", "trades", "borrows", "interactions", "achievements", "histories", "card_discoveries", "ranks", "simulation_time", "active_battles", "simulation_events", "last_ai_request_time", "last_ai_trade_time", "last_ai_borrow_time", "out_of_game", "dice_sequence", "duel_sequence", "distribution_sequence", "request_sequence", "order_sequence", "team_request_sequence", "last_wall_time", "clock_mode"]:
            path = RUNTIME_WORLD_COLLECTIONS / f"{key}.json"
            if not path.exists(): continue
            payload = read_json(path, {})
            value = payload.get("value", payload.get("state", payload)) if isinstance(payload, dict) else payload
            state[key] = value
        state["roles"] = dict(state.get("roles", {}) or {})
        return state

    def authored_entry(self, entity, runtime_fields):
        return {key: value for key, value in entity.__dict__.items() if key not in runtime_fields}

    def runtime_entry(self, entity, runtime_fields):
        return {key: getattr(entity, key) for key in runtime_fields if hasattr(entity, key)}

    def place_from_entry(self, entry):
        values = dict(entry)
        current_duels = int(values.pop("current_duels", 0) or 0)
        values.pop("history", None)
        return PlaceDef(current_duels=current_duels, **values)

    def sync_place_runtime(self):
        self.world["place_occupancy"] = {place.id: int(place.current_duels) for place in self.places.values()}

    def load(self):
        cards_data = read_json(DATA / "cards.json", [])
        character_data = read_json(DATA / "characters.json", [])
        team_data = read_json(DATA / "teams.json", [])
        fresh_character_ids = {entry.get("id") for entry in character_data if entry.get("id") and not self.runtime_path("characters", entry.get("id")).exists()}
        self.migrate_runtime_state(character_data, "characters", CHARACTER_RUNTIME_FIELDS)
        self.migrate_runtime_state(team_data, "teams", TEAM_RUNTIME_FIELDS)
        self.cards = {entry["id"]: CardDef(**entry) for entry in cards_data}
        for card in self.cards.values(): card.subtypes = self.normalize_profile_list(getattr(card, "subtypes", []), limit=2)
        self.characters = {entry["id"]: CharacterDef(**self.overlay_runtime_state({**entry, "relationship": entry.get("relationship", "stranger")}, "characters", CHARACTER_RUNTIME_FIELDS)) for entry in character_data}
        self.decks = read_json(DATA / "decks.json", {})
        for character in self.characters.values():
            owned_deck_cards = [card_id for deck in self.decks.values() if deck.get("owner_id") == character.id for card_id in DeckRules.all_cards(deck)]
            if character.id in fresh_character_ids and owned_deck_cards: character.library_cards = owned_deck_cards
            elif not character.library_cards: character.library_cards = DeckRules.all_cards(self.decks.get(character.deck_id, {}))
        for deck_id, deck in self.decks.items():
            deck = dict(deck or {})
            deck.setdefault("name", str(deck_id))
            deck.setdefault("description", "")
            deck.setdefault("portrait", "")
            deck.setdefault("owner_id", "")
            deck.setdefault("best_cards", [])
            deck.setdefault("preferred_families", [])
            deck.setdefault("preferred_card_kinds", [])
            deck.setdefault("experience", {})
            deck.setdefault("schema", 2)
            deck["main_cards"] = DeckRules.normalized(deck.get("main_cards", []), self.cards)
            deck["fusion_cards"] = DeckRules.normalized_fusion(deck.get("fusion_cards", []), self.cards)
            self.decks[deck_id] = deck
        self.places = {entry["id"]: self.place_from_entry(entry) for entry in read_json(DATA / "places.json", [])}
        self.teams = {entry["id"]: TeamDef(**self.overlay_runtime_state(entry, "teams", TEAM_RUNTIME_FIELDS)) for entry in team_data}
        self.ensure_behavior_weights()
        self.world = self.load_world_state()
        self.world.setdefault("clock_epoch", int(time.time()))
        try: self.clock.epoch = float(self.world.get("clock_epoch", time.time()))
        except (TypeError, ValueError): self.clock.epoch = time.time(); self.world["clock_epoch"] = int(self.clock.epoch)
        try: self.world["last_wall_time"] = float(self.world.get("last_wall_time", 0.0) or 0.0)
        except (TypeError, ValueError): self.world["last_wall_time"] = 0.0
        if self.world["last_wall_time"] <= 0.0: self.world["last_wall_time"] = time.time()
        self.world["clock_mode"] = "wall_clock"
        for key, default in [("requests", []), ("orders", []), ("team_requests", []), ("team_effect_requests", []), ("place_effects", {}), ("championships", []), ("trades", []), ("borrows", []), ("achievements", []), ("histories", []), ("card_discoveries", []), ("ranks", {}), ("simulation_time", 0.0), ("active_battles", []), ("simulation_events", []), ("last_ai_request_time", 0.0), ("last_ai_trade_time", 0.0), ("last_ai_borrow_time", 0.0), ("place_occupancy", {}), ("out_of_game", []), ("dice_sequence", 0), ("duel_sequence", 0), ("distribution_sequence", 0), ("request_sequence", 0), ("order_sequence", 0), ("team_request_sequence", 0), ("last_wall_time", 0.0), ("clock_mode", "wall_clock")]: self.world.setdefault(key, default)
        occupancy = self.world.get("place_occupancy", {}) if isinstance(self.world, dict) else {}
        for place in self.places.values(): place.current_duels = int(occupancy.get(place.id, place.current_duels) or 0)
        self.sync_place_runtime()
        if not isinstance(self.world.get("last_ai_request_time"), (int, float)): self.world["last_ai_request_time"] = 0.0
        self.rules = read_json(DATA / "rules.json", self.rules if isinstance(self.rules, dict) else {})
        DeckRules.configure(self.rules)
        self.card_registry_errors = self.validate_card_registry()
        if self.card_registry_errors: raise ValueError("Card registry invalid: " + "; ".join(self.card_registry_errors))
        self.logic = {}
        self.logic_owners = {}
        for category, registry in [("cards", self.cards), ("characters", self.characters), ("teams", self.teams), ("places", self.places), ("decks", self.decks)]:
            for entity_id, entity in registry.items():
                media_folder = entity.get("media_folder", "") if isinstance(entity, dict) else getattr(entity, "media_folder", "")
                logic_root = DATA / media_folder / "logic" if media_folder else None
                if not logic_root: continue
                for path in logic_root.glob("*.json"):
                    self.logic[path.stem] = LogicGraph.from_dict(read_json(path, {}))
                    self.logic_owners[path.stem] = logic_root
        self.ensure_entity_scaffolds()
        self.media.scan()
        self.world_sessions = {}
        self.world_team_sessions = {}
        self.dirty_domains.clear()
        self.world_checkpoint_elapsed = 0.0

    def normalize_profile_list(self, values, allowed=None, limit=20):
        values = values if isinstance(values, list) else [values] if values else []
        result = []
        for value in values:
            key = str(value).strip().lower()
            if not key or (allowed is not None and key not in allowed): continue
            if key not in result: result.append(key)
        return result[:limit]

    def normalize_number_map(self, values, defaults, minimum=0.0, maximum=10.0):
        result = dict(defaults)
        if isinstance(values, dict):
            for key, value in values.items():
                try: result[str(key)] = max(minimum, min(maximum, float(value)))
                except (TypeError, ValueError): pass
        return result

    def normalize_character_profile(self, character):
        character.preferred_families = self.normalize_profile_list(character.preferred_families, limit=20) or ["warrior"]
        character.preferred_card_kinds = self.normalize_profile_list(getattr(character, "preferred_card_kinds", []), {"normal", "effect", "spell", "field", "trap", "fusion", "ritual", "legendary"}, 10)
        character.preferred_subtypes = self.normalize_profile_list(getattr(character, "preferred_subtypes", []), limit=2)
        character.preferred_cards = [str(item) for item in self.normalize_profile_list(getattr(character, "preferred_cards", []) or getattr(character, "best_cards", []), set(self.cards), 20)]
        character.best_cards = [str(item) for item in self.normalize_profile_list(getattr(character, "best_cards", []), set(self.cards), 20)]
        character.preferred_places = [str(item) for item in self.normalize_profile_list(getattr(character, "preferred_places", []), set(self.places), 20)]
        character.technique_profile = self.normalize_number_map(getattr(character, "technique_profile", {}), {"aggression": 5.0, "defense": 5.0, "control": 5.0, "combo": 5.0, "resource": 5.0, "bluff": 5.0, "risk": 5.0, "adaptation": 5.0})
        character.cognition = self.normalize_number_map(getattr(character, "cognition", {}), {"smartness": float(character.smartness), "memory": 5.0, "inference": 5.0, "planning": 5.0, "uncertainty": 5.0})
        character.cognition["smartness"] = float(character.smartness)
        character.learning_policy = self.normalize_number_map(getattr(character, "learning_policy", {}), {"observation_rate": 5.0, "retention": 5.0, "adaptation_rate": 5.0, "decay": 1.0, "history_limit": 10.0}, 0.0, 100.0)
        character.state_rules = dict(getattr(character, "state_rules", {}) or {})
        character.state_rules.setdefault("deck_ranges", {"stranger": [1, 10], "ally": [1, 10], "enemy": [1, 10]})
        character.state_rules.setdefault("preferred_state", "stranger")
        character.relationship_history = list(getattr(character, "relationship_history", []) or [])[-100:]
        character.mood_state = dict(getattr(character, "mood_state", {}) or {})
        character.mood_state.setdefault("current", character.mood or "neutral")
        character.mood_state.setdefault("intensity", 0.0)
        character.knowledge_state = dict(getattr(character, "knowledge_state", {}) or {})
        character.knowledge_state.setdefault("cards", {})
        character.knowledge_state.setdefault("opponents", {})
        character.knowledge_state.setdefault("effects", {})
        character.learning_state = dict(getattr(character, "learning_state", {}) or {})
        character.learning_state.setdefault("observations", 0)
        character.learning_state.setdefault("updates", 0)
        character.learning_state.setdefault("last_update", 0.0)
        character.experience = dict(getattr(character, "experience", {}) or {})
        character.experience.setdefault("duels", 0)
        character.experience.setdefault("wins", 0)
        character.experience.setdefault("losses", 0)
        character.experience.setdefault("draws", 0)
        character.experience.setdefault("techniques", {})
        character.out_of_game_until = float(getattr(character, "out_of_game_until", 0.0) or 0.0)
        character.world_status = str(getattr(character, "world_status", "in_playground") or "in_playground")
        if character.world_status not in ["in_playground", "out_of_game"]: character.world_status = "in_playground"

    def normalize_team_profile(self, team):
        team.members = [str(item) for item in self.normalize_profile_list(team.members, set(self.characters), 3)]
        if team.leader not in team.members and team.members: team.leader = team.members[0]
        team.preferred_places = [str(item) for item in self.normalize_profile_list(team.preferred_places, set(self.places), 20)]
        team.preferred_families = self.normalize_profile_list(getattr(team, "preferred_families", []), limit=20)
        team.preferred_card_kinds = self.normalize_profile_list(getattr(team, "preferred_card_kinds", []), {"normal", "effect", "spell", "field", "trap", "fusion", "ritual", "legendary"}, 10)
        team.preferred_cards = [str(item) for item in self.normalize_profile_list(getattr(team, "preferred_cards", []), set(self.cards), 20)]
        team.behavior_weights = self.normalize_number_map(getattr(team, "behavior_weights", {}), {"coordination": 5.0, "risk": 5.0, "resource": 5.0, "switching": 5.0, "adaptation": 5.0})
        team.knowledge_state = dict(getattr(team, "knowledge_state", {}) or {})
        team.learning_state = dict(getattr(team, "learning_state", {}) or {})
        team.experience = dict(getattr(team, "experience", {}) or {})
        team.formation_state = str(getattr(team, "formation_state", "complete") or "complete")
        if team.formation_state not in ["in_making", "complete", "broken"]: team.formation_state = "complete" if len(team.members) == 3 else "in_making"
        team.formation_requests = list(getattr(team, "formation_requests", []) or [])[-50:]
        for key, value in {"duels": 0, "wins": 0, "losses": 0, "draws": 0}.items(): team.experience.setdefault(key, value)

    def ensure_behavior_weights(self):
        defaults = {"risk_tolerance": 3.0, "learning_value": 5.0, "rematch_desire": 4.0, "reward_value": 5.0, "place_preference": 5.0, "ally_bias": 4.0, "enemy_bias": 6.0, "adaptation": 1.0, "memory": 5.0, "inference": 5.0, "planning": 5.0}
        for character in self.characters.values():
            self.normalize_character_profile(character)
            for key, value in defaults.items(): character.behavior_weights.setdefault(key, value)
            family_weights = character.behavior_weights.setdefault("family_weights", {})
            for family in [card.family.lower() for card in self.cards.values()]: family_weights.setdefault(family, 2.0 if family in character.preferred_families else 0.0)
            character.behavior_weights.setdefault("card_kind_weights", {kind: 2.0 if kind in character.preferred_card_kinds else 0.0 for kind in ["normal", "effect", "spell", "field", "trap", "fusion", "ritual", "legendary"]})
            character.behavior_weights.setdefault("subtype_weights", {item: 2.0 for item in character.preferred_subtypes})
            character.behavior_weights.setdefault("state_weights", {"stranger": 1.0, "ally": 0.5, "enemy": 2.0, "opponent": 1.0})
            character.behavior_weights.setdefault("phase_weights", {"MAIN 1": 1.0, "MAIN 2": 1.0, "BATTLE": 1.0})
            character.behavior_weights.setdefault("duel", {"summon_bias": 1.0, "set_bias": 1.0, "activation_bias": 1.0, "removal_bias": 1.0, "defense_bias": 1.0, "attack_bias": 1.0, "trap_threshold": 0.0})
            character.learned_cards = {str(key): max(0, int(value)) for key, value in character.learned_cards.items() if str(key) in self.cards}
            character.learned_opponents = {str(key): max(0, int(value)) for key, value in character.learned_opponents.items() if str(key) in self.characters}
            character.goals = list(getattr(character, "goals", []) or [])[-20:]
            if not character.goals:
                family = character.preferred_families[0] if character.preferred_families else "warrior"
                character.goals = [{"id": "master_" + family, "kind": "master_family", "target": family, "progress": 0.0, "priority": 1.0}, {"id": "build_trust", "kind": "build_relationship", "target": "ally", "progress": 0.0, "priority": 0.8}, {"id": "earn_rank", "kind": "reach_rank", "target": max(2, min(10, int(character.rank) + 1)), "progress": float(character.rank), "priority": 0.7}, {"id": "challenge_enemy", "kind": "challenge_enemy", "target": "enemy", "progress": 0.0, "priority": 0.4}]
            character.memories = list(getattr(character, "memories", []) or [])[-100:]
            character.persona_state = dict(getattr(character, "persona_state", {}) or {})
            character.persona_state.setdefault("reputation", 0.0)
            character.persona_state.setdefault("trust", {})
            character.persona_state.setdefault("confidence", 0.0)
        for team in self.teams.values(): self.normalize_team_profile(team)

    def relationship_for(self, character_id, other_id):
        character = self.characters.get(character_id)
        if not character or character_id == other_id: return "stranger"
        if other_id in character.enemies: return "enemy"
        if other_id in character.allies: return "ally"
        recent = [item for item in character.relationship_history if item.get("other") == other_id]
        return str(recent[-1].get("relation", "stranger")) if recent else "stranger"

    def set_relationship(self, character_id, other_id, relation, reason=""):
        character = self.characters.get(character_id)
        other = self.characters.get(other_id)
        relation = str(relation or "stranger").lower()
        if not character or not other or character_id == other_id or relation not in ["stranger", "ally", "enemy"]: return False
        character.allies = [item for item in character.allies if item != other_id]
        character.enemies = [item for item in character.enemies if item != other_id]
        if relation == "ally": character.allies.append(other_id)
        if relation == "enemy": character.enemies.append(other_id)
        character.relationship = relation
        character.relationship_history.append({"other": other_id, "relation": relation, "reason": reason, "time": time.time()})
        character.relationship_history = character.relationship_history[-100:]
        return True

    def _relationship_score(self, character, other):
        relation = self.relationship_for(character.id, other.id)
        score = float(character.behavior_weights.get("enemy_bias", 6.0)) if relation == "enemy" else float(character.behavior_weights.get("ally_bias", 4.0)) if relation == "ally" else 5.0
        score += float(character.persona_state.get("trust", {}).get(other.id, 0.0)) * 0.35
        score += float(character.behavior_weights.get("state_weights", {}).get(relation, 1.0))
        return score

    def active_goal(self, character):
        goals = [goal for goal in getattr(character, "goals", []) if float(goal.get("progress", 0.0)) < 100.0]
        return max(goals, key=lambda goal: (float(goal.get("priority", 0.0)), str(goal.get("id", "")))) if goals else {}

    def choose_ai_opponent(self, character_id):
        character = self.characters.get(character_id)
        player_id = self.role_config()["player_character"]
        candidates = [other for other in self.characters.values() if other.id != character_id and self.social_available(other.id) and float(other.cooldown_until) <= float(self.world.get("simulation_time", 0.0))]
        if not character or not candidates: return None
        def score(other):
            history = [event for event in character.history if event.get("opponent") == other.id]
            losses = sum(1 for event in history if event.get("result") == "loss")
            wins = sum(1 for event in history if event.get("result") == "win")
            known = float(character.learned_opponents.get(other.id, 0))
            challenge = abs(int(other.stars) - int(character.stars)) * float(character.behavior_weights.get("learning_value", 5.0))
            rematch = losses * float(character.behavior_weights.get("rematch_desire", 4.0)) - wins
            goal = self.active_goal(character)
            goal_score = 0.0
            if goal.get("kind") == "master_family":
                goal_score += 3.0 if any(card.family == goal.get("target") for card in self.cards.values()) else 0.0
            if goal.get("kind") == "build_relationship": goal_score += 4.0 if self.relationship_for(character.id, other.id) == goal.get("target") else 0.0
            place_score = 2.0 if self.role_config().get("default_place") in character.preferred_places else 0.0
            return self._relationship_score(character, other) + challenge + rematch + goal_score + place_score - known * float(character.behavior_weights.get("adaptation", 1.0))
        return max(candidates, key=lambda other: (score(other), other.id))

    def schedule_ai_request(self, character_id):
        character = self.characters.get(character_id)
        target = self.choose_ai_opponent(character_id)
        if not character or not target or character.availability != "free": return None
        if any(entry.get("status") in ["open", "queued", "active"] and entry.get("from") == character_id for entry in self.world.setdefault("requests", [])): return None
        goal = self.active_goal(character)
        reason = "goal pursuit: " + str(goal.get("kind")) if goal else "rematch study" if character.learned_opponents.get(target.id, 0) else "study duel"
        intent = "ally" if goal.get("kind") == "build_relationship" and self.relationship_for(character_id, target.id) == "stranger" else "enemy" if goal.get("kind") == "challenge_enemy" else "stranger"
        return self.add_request(character_id, target.id, reason, kind="learning", format_name="1v1", preferred_place=character.preferred_places[0] if character.preferred_places and character.preferred_places[0] in self.places else self.role_config()["default_place"], relationship_intent=intent, expires_in=10800)

    def _ai_request_tick(self):
        if float(self.world.get("simulation_time", 0.0)) < float(self.world.get("last_ai_request_time", 0.0)) + 10.0: return
        self.world["last_ai_request_time"] = float(self.world.get("simulation_time", 0.0))
        for character in sorted(self.characters.values(), key=lambda item: item.id):
            if character.id == self.role_config()["player_character"] or character.world_status != "in_playground" or character.availability != "free": continue
            order = self.choose_ai_order(character.id)
            if order and self.respond_order(order.get("id", ""), character.id, "accept"): continue
            self.schedule_ai_request(character.id)


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
            write_json(DATA / "places.json", [self.authored_entry(place, {"current_duels", "history"}) for place in self.places.values()])
            write_json(DATA / "teams.json", [self.authored_entry(team, TEAM_RUNTIME_FIELDS) for team in self.teams.values()])
        if "runtime_characters" in requested:
            for char in self.characters.values(): write_json(self.runtime_path("characters", char.id), {"schema": 2, "id": char.id, "category": "characters", "state": self.runtime_entry(char, CHARACTER_RUNTIME_FIELDS)})
        if "runtime_teams" in requested:
            for team in self.teams.values(): write_json(self.runtime_path("teams", team.id), {"schema": 2, "id": team.id, "category": "teams", "state": self.runtime_entry(team, TEAM_RUNTIME_FIELDS)})
        if "runtime_world" in requested:
            self.sync_place_runtime()
            world_keys = ["requests", "orders", "team_requests", "team_effect_requests", "place_effects", "championships", "trades", "borrows", "interactions", "achievements", "histories", "card_discoveries", "ranks", "simulation_time", "active_battles", "simulation_events", "last_ai_request_time", "last_ai_trade_time", "last_ai_borrow_time", "out_of_game", "dice_sequence", "duel_sequence", "distribution_sequence", "request_sequence", "order_sequence", "team_request_sequence", "last_wall_time", "clock_mode"]
            defaults = {"requests": [], "orders": [], "team_requests": [], "team_effect_requests": [], "place_effects": {}, "championships": [], "trades": [], "borrows": [], "interactions": [], "achievements": [], "histories": [], "card_discoveries": [], "ranks": {}, "simulation_time": 0.0, "active_battles": [], "simulation_events": [], "last_ai_request_time": 0.0, "last_ai_trade_time": 0.0, "last_ai_borrow_time": 0.0, "out_of_game": [], "dice_sequence": 0, "duel_sequence": 0, "distribution_sequence": 0, "request_sequence": 0, "order_sequence": 0, "team_request_sequence": 0, "last_wall_time": time.time(), "clock_mode": "wall_clock"}
            for key in world_keys: write_json(RUNTIME_WORLD_COLLECTIONS / f"{key}.json", {"schema": 2, "category": "world_collection", "id": key, "value": self.world.get(key, defaults[key])})
            write_json(RUNTIME_WORLD_INDEX, {"schema": 3, "category": "world_index", "roles": self.world.get("roles", {}), "place_occupancy": self.world.get("place_occupancy", {}), "clock_epoch": self.world.get("clock_epoch", int(self.clock.epoch)), "last_wall_time": float(self.world.get("last_wall_time", time.time())), "clock_mode": "wall_clock", "collections": world_keys})
        if "profile" in requested: write_json(SAVE, self.save_data)
        if "logic" in requested:
            for key, graph in self.logic.items():
                owner = self.logic_owners.get(key)
                if owner: write_json(owner / f"{key}.json", graph.to_dict())
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
        simulation_time = float(self.world.get("simulation_time", 0.0))
        return {"clock": self.clock.now(simulation_time), "period": self.clock.period(simulation_time), "label": self.clock.label(simulation_time), "simulation_time": simulation_time, "places": {place.id: {"current": place.current_duels, "capacity": place.capacity} for place in self.places.values()}, "characters": {character.id: {"availability": character.availability, "place": character.current_place, "destination": character.destination, "progress": character.movement_progress, "activity": character.activity} for character in self.characters.values()}, "active_battles": len([battle for battle in self.world.setdefault("active_battles", []) if battle.get("status") == "active"])}

    def interaction_by_id(self, interaction_id):
        return next((item for item in self.world.setdefault("interactions", []) if item.get("id") == interaction_id), None)

    def queue_interaction_media(self, family, event, actor_id="", target_id="", relation="opponent", entity_type="characters", entity_id="", metadata=None):
        place_id = self.role_config().get("default_place", "")
        if relation == "opponent" and actor_id and target_id: relation = self.relationship_for(actor_id, target_id)
        selection = self.media.resolve(event, actor_id, target_id, relation, entity_type, entity_id or actor_id, place_id, "hang")
        record = {"type": "interaction_media", "family": family, "event": event, "actor": actor_id, "target": target_id, "relation": relation, "selection": selection.to_dict(), "metadata": dict(metadata or {}), "sim_time": float(self.world.get("simulation_time", 0.0))}
        events = self.world.setdefault("simulation_events", [])
        events.append(record)
        self.world["simulation_events"] = events[-200:]
        return selection

    def register_interaction(self, family, record):
        interaction_id = record.get("id", "")
        if not interaction_id: return None
        catalog = self.world.setdefault("interactions", [])
        existing = self.interaction_by_id(interaction_id)
        participants = [record.get(key, "") for key in ["from", "to", "creator", "recipient", "placer", "taker", "lender", "borrower"]]
        envelope = {"id": interaction_id, "family": family, "from": record.get("from") or record.get("creator") or record.get("placer") or record.get("lender", ""), "to": record.get("to") or record.get("recipient") or record.get("taker") or record.get("borrower", ""), "participants": list(dict.fromkeys(item for item in participants if item)), "intent": record.get("relationship_intent", record.get("intent", family)), "status": record.get("status", record.get("state", "open")), "created_sim_time": record.get("created_sim_time", record.get("created", float(self.world.get("simulation_time", 0.0)))), "expires_sim_time": record.get("expires_sim_time", record.get("expires", 0.0)), "payload": {key: value for key, value in record.items() if key not in ["events", "history", "id", "status", "state"]}, "events": list(record.get("events", record.get("history", [])))}
        if existing is None: catalog.append(envelope)
        else: existing.update(envelope)
        return envelope

    def transition_interaction(self, family, record, status, actor, action=None, metadata=None):
        now = float(self.world.get("simulation_time", 0.0))
        if "status" in record: record["status"] = status
        if "state" in record: record["state"] = status
        event = {"status": status, "actor": actor, "action": action or status, "sim_time": now}
        if metadata: event.update(dict(metadata))
        events = record.setdefault("events", record.setdefault("history", []))
        events.append(event)
        envelope = self.register_interaction(family, record)
        if envelope is not None: envelope["events"] = list(events); envelope["status"] = status
        return event

    def evolve_persona(self, character_id, event, payload=None):
        character = self.characters.get(character_id)
        if not character: return
        payload = dict(payload or {})
        character.memories.append({"event": str(event), "payload": payload, "sim_time": float(self.world.get("simulation_time", 0.0))})
        character.memories = character.memories[-100:]
        state = character.persona_state
        state["reputation"] = max(-100.0, min(100.0, float(state.get("reputation", 0.0)) + (1.0 if event in ["trade_completed", "borrow_accepted", "championship_won"] else -0.5 if event in ["trade_canceled", "borrow_denied"] else 0.2 if event in ["duel_completed", "team_duel_completed"] else 0.0)))
        other_id = payload.get("with") or payload.get("to") or payload.get("from") or payload.get("opponent")
        if other_id and other_id in self.characters:
            trust = state.setdefault("trust", {})
            trust[other_id] = max(-10.0, min(10.0, float(trust.get(other_id, 0.0)) + (1.0 if event in ["trade_completed", "borrow_accepted"] else -1.0 if event in ["trade_canceled", "borrow_denied"] else 0.25)))
        if event in ["duel_completed", "team_duel_completed"]:
            result = payload.get("result", payload.get("winner", ""))
            delta = 0.4 if result in [character_id, "win"] or payload.get("winner") == character_id else -0.25 if result in ["loss"] or payload.get("loser") == character_id else 0.0
            state["confidence"] = max(-10.0, min(10.0, float(state.get("confidence", 0.0)) + delta))
            character.behavior_weights["adaptation"] = min(10.0, float(character.behavior_weights.get("adaptation", 1.0)) + 0.05)
        for goal in character.goals:
            if goal.get("kind") == "reach_rank": goal["progress"] = float(character.rank)
            if goal.get("kind") == "build_relationship" and event in ["trade_completed", "borrow_accepted"]: goal["progress"] = min(100.0, float(goal.get("progress", 0.0)) + 1.0)
            if goal.get("kind") == "master_family" and payload.get("family") == goal.get("target"): goal["progress"] = min(100.0, float(goal.get("progress", 0.0)) + 1.0)

    def record_history(self, scope, entity_id, event, payload=None):
        if scope == "character" and entity_id in self.characters:
            self.characters[entity_id].idle_elapsed = 0.0
            self.characters[entity_id].idle_cue_count = 0
        record = {"scope": str(scope), "entity_id": str(entity_id), "event": str(event), "payload": dict(payload or {}), "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()}
        self.world.setdefault("histories", []).append(record)
        self.world["histories"] = self.world["histories"][-1000:]
        entity = self.characters.get(entity_id) or self.teams.get(entity_id) or self.places.get(entity_id)
        if entity is not None and hasattr(entity, "history"):
            item = {"event": event, "scope": scope, **dict(payload or {}), "sim_time": record["sim_time"], "time": record["time"]}
            entity.history.append(item)
            entity.history = entity.history[-100:]
        if scope == "character": self.evolve_persona(entity_id, event, payload)
        return record

    def distribute_trio_cards(self, team, trigger, context=None):
        config = dict(getattr(team, "distribution", {}) or {})
        rules = dict((self.rules or {}).get("trio_distribution") or {})
        if not config.get("enabled") or not bool(rules.get("enabled", True)): return []
        pool_id = str(config.get("pool", rules.get("pool", "")) or "")
        opportunity = float(config.get("opportunity", rules.get("opportunity", 0.60)) or 0.60)
        if trigger not in list(config.get("triggers", rules.get("trigger_events", ["duel_completed", "team_win"])) or []): return []
        recipients = [character for character in self.characters.values() if character.id not in team.members and character.world_status == "in_playground"]
        if not recipients: recipients = [character for character in self.characters.values() if character.id not in team.members]
        if not recipients: return []
        grants = []
        sequence = int(self.world.get("distribution_sequence", 0))
        for member_id in list(team.members):
            sequence += 1
            member = self.characters.get(member_id)
            if not member: continue
            candidates = [card for card in self.cards.values() if isinstance(getattr(card, "distribution", {}), dict) and card.distribution.get("eligible") and card.distribution.get("pool") == pool_id and card.distribution.get("unowned_at_start") and not any(card.id in character.library_cards for character in self.characters.values())]
            candidates.sort(key=lambda card: (sum(1 for character in self.characters.values() if card.id in character.knowledge_state.setdefault("cards", {})), card.id))
            if not candidates: continue
            card = candidates[sequence % len(candidates)]
            digest = hashlib.sha256(f"{sequence}:{team.id}:{member_id}:{card.id}".encode("utf-8")).hexdigest()
            roll = int(digest[:8], 16) / 4294967295.0
            attempt = {"type": "trio_distribution_attempt", "team": team.id, "giver": member_id, "card": card.id, "recipient": "", "trigger": trigger, "roll": roll, "opportunity": opportunity, "granted": False, "sequence": sequence, "sim_time": float(self.world.get("simulation_time", 0.0))}
            if roll >= opportunity:
                self.world.setdefault("simulation_events", []).append(attempt)
                continue
            recipients.sort(key=lambda character: (len(character.library_cards), character.id))
            recipient = recipients[0]
            if card.id in recipient.library_cards:
                self.world.setdefault("simulation_events", []).append(attempt)
                continue
            recipient.library_cards.append(card.id)
            recipient.library_cards = list(dict.fromkeys(recipient.library_cards))
            self.discover_card(recipient.id, card.id, "trio_mysterio", member_id, {"team": team.id, "trigger": trigger, "distribution_sequence": sequence})
            self.record_history("character", recipient.id, "trio_card_received", {"card": card.id, "giver": member_id, "team": team.id, "trigger": trigger})
            self.record_history("character", member_id, "trio_card_given", {"card": card.id, "recipient": recipient.id, "team": team.id, "trigger": trigger})
            grants.append({"card": card.id, "giver": member_id, "recipient": recipient.id, "team": team.id, "trigger": trigger, "roll": roll, "opportunity": opportunity, "sequence": sequence})
            attempt.update({"recipient": recipient.id, "granted": True})
            self.world.setdefault("simulation_events", []).append(attempt)
            self.world.setdefault("simulation_events", []).append({"type": "trio_distribution_grant", **grants[-1], "sim_time": float(self.world.get("simulation_time", 0.0))})
        self.world["distribution_sequence"] = sequence
        return grants

    def discover_card(self, viewer_id, card_id, source="observed", owner_id="", context=None):
        if viewer_id not in self.characters or card_id not in self.cards: return False
        character = self.characters[viewer_id]
        cards = character.knowledge_state.setdefault("cards", {})
        entry = cards.setdefault(card_id, {"sources": [], "sightings": 0, "owners": [], "contexts": []})
        if not isinstance(entry, dict): entry = {"sources": [], "sightings": 0, "owners": [], "contexts": []}; cards[card_id] = entry
        entry["sources"] = list(entry.get("sources", []) or [])
        entry["owners"] = list(entry.get("owners", []) or [])
        entry["contexts"] = list(entry.get("contexts", []) or [])
        source = str(source or "observed")
        if source not in entry["sources"]: entry["sources"].append(source)
        entry["sightings"] = int(entry.get("sightings", 0)) + 1
        if owner_id and owner_id not in entry.setdefault("owners", []): entry["owners"].append(owner_id)
        if context: entry.setdefault("contexts", []).append(dict(context))
        entry["contexts"] = entry.get("contexts", [])[-10:]
        self.world.setdefault("card_discoveries", []).append({"viewer": viewer_id, "card": card_id, "source": source, "owner": owner_id, "context": dict(context or {}), "sim_time": float(self.world.get("simulation_time", 0.0))})
        self.world["card_discoveries"] = self.world["card_discoveries"][-1000:]
        return True

    def card_visibility(self, viewer_id, card_id):
        if card_id not in self.cards: return {"card_id": card_id, "state": "unknown", "owned": 0, "known": False}
        character = self.characters.get(viewer_id)
        if not character: return {"card_id": card_id, "state": "unknown", "owned": 0, "known": False}
        owned = character.library_cards.count(card_id)
        if owned:
            return {"card_id": card_id, "state": "owned", "owned": owned, "known": True, "sources": ["library"]}
        entry = character.knowledge_state.setdefault("cards", {}).get(card_id, {})
        sources = list(entry.get("sources", [])) if isinstance(entry, dict) else []
        state = "team_proprietary" if "team" in sources else "observed" if sources else "unknown"
        return {"card_id": card_id, "state": state, "owned": 0, "known": bool(sources), "sources": sources}

    def card_catalog(self, viewer_id):
        return [{"card": card, "visibility": self.card_visibility(viewer_id, card.id)} for card in sorted(self.cards.values(), key=lambda item: item.name.lower())]

    def journal_for(self, scope, entity_id, limit=20):
        return [dict(item) for item in self.world.setdefault("histories", []) if item.get("scope") == scope and item.get("entity_id") == entity_id][-max(1, int(limit)):]

    def character_summary(self, character_id):
        character = self.characters.get(character_id)
        if not character: return None
        active_battles = [battle for battle in self.world.setdefault("active_battles", []) if battle.get("status") == "active" and character_id in [battle.get("from"), battle.get("to")]]
        persona = dict(getattr(character, "persona_state", {}) or {})
        public_persona = {"reputation": float(persona.get("reputation", 0.0)), "confidence": float(persona.get("confidence", 0.0)), "active_goal": self.active_goal(character), "preferred_families": list(character.preferred_families), "preferred_card_kinds": list(character.preferred_card_kinds), "preferred_places": list(character.preferred_places)}
        return {"id": character.id, "name": character.name, "gender": character.gender, "portrait": character.portrait, "relationship": character.relationship, "relationship_history": list(character.relationship_history), "mood": character.mood, "world_status": character.world_status, "availability": character.availability, "activity": character.activity, "current_place": character.current_place, "team_ids": [team.id for team in self.teams.values() if character_id in team.members], "active_battle_ids": [battle.get("id") for battle in active_battles], "active_trade_ids": [trade.get("id") for trade in self.world.setdefault("trades", []) if trade.get("state") in ["open", "countered", "deferred"] and character_id in [trade.get("creator"), trade.get("recipient")]], "borrow_ids": [record.get("id") for record in self.world.setdefault("borrows", []) if record.get("state") in ["requested", "deferred", "active"] and character_id in [record.get("lender"), record.get("borrower")]], "history": self.journal_for("character", character_id), "experience": dict(character.experience), "known_cards": len(character.knowledge_state.get("cards", {})), "goals": list(getattr(character, "goals", [])), "memories": list(getattr(character, "memories", []))[-20:], "persona": public_persona}

    def team_summary(self, team_id):
        team = self.teams.get(team_id)
        if not team: return None
        return {"id": team.id, "name": team.name, "leader": team.leader, "members": list(team.members), "relationship": team.relationship, "formation_state": team.formation_state, "effect_locked": bool(team.effect_locked), "preferred_places": list(team.preferred_places), "formation_requests": list(getattr(team, "formation_requests", []))[-20:], "active_championships": [item.get("id") for item in self.world.setdefault("championships", []) if team_id in item.get("teams", []) or team_id in item.get("enrolled", [])], "history": self.journal_for("team", team_id)}

    def place_summary(self, place_id):
        snapshot = self.place_snapshot(place_id)
        if not snapshot: return None
        snapshot["history"] = self.journal_for("place", place_id)
        return snapshot

    def set_character_out_of_game(self, character_id, duration=3600.0, reason=""):
        character = self.characters.get(character_id)
        if not character or character.availability == "active" or any(battle.get("status") == "active" and character_id in [battle.get("from"), battle.get("to")] for battle in self.world.setdefault("active_battles", [])): return False
        now = float(self.world.get("simulation_time", 0.0))
        until = now + max(1.0, float(duration))
        character.out_of_game_until = until
        character.world_status = "out_of_game"
        character.availability = "out_of_game"
        character.activity = "out_of_game"
        record = {"character": character_id, "until": until, "reason": str(reason), "started": now}
        self.world.setdefault("out_of_game", []).append(record)
        self.record_history("character", character_id, "left_playground", record)
        self.save()
        return record

    def _advance_out_of_game(self):
        now = float(self.world.get("simulation_time", 0.0))
        for character in self.characters.values():
            if character.world_status == "out_of_game" and now >= float(character.out_of_game_until):
                character.world_status = "in_playground"
                character.out_of_game_until = 0.0
                character.availability = "free"
                character.activity = "idle"
                self.record_history("character", character.id, "returned_to_playground", {})

    def place_snapshot(self, place_id):
        place = self.places.get(place_id)
        if not place: return None
        occupants = [character.id for character in self.characters.values() if character.current_place == place_id and character.world_status == "in_playground"]
        teams = [team.id for team in self.teams.values() if place_id in team.preferred_places]
        return {"id": place.id, "name": place.name, "description": getattr(place, "description", ""), "background": place.background, "capacity": place.capacity, "current_duels": place.current_duels, "day_night": place.day_night, "effects": list(place.effects), "team_effect": dict(self.world.setdefault("place_effects", {}).get(place_id, {})), "occupants": occupants, "linked_teams": teams, "history": list(getattr(place, "history", []))[-20:]}

    def craft_place_effect(self, team_id, place_id, sacrifices):
        team = self.teams.get(team_id)
        place = self.places.get(place_id)
        sacrifices = [str(item) for item in list(sacrifices or [])]
        if not team or not place or place_id not in team.preferred_places and team_id not in getattr(place, "linked_teams", []): return None
        if len(sacrifices) != 3 or len(set(sacrifices)) != 3: return None
        owners = []
        for card_id in sacrifices:
            owner = next((character for character in self.characters.values() if character.id in team.members and card_id in character.library_cards), None)
            if not owner: return None
            owners.append(owner)
        current = self.world.setdefault("place_effects", {}).get(place_id, {})
        if current.get("locked") or current.get("candidates"): return None
        for owner, card_id in zip(owners, sacrifices): owner.library_cards.remove(card_id)
        families = [self.cards[card_id].family for card_id in sacrifices if card_id in self.cards]
        family = max(set(families), key=families.count) if families else "any"
        effect = {"team_id": team_id, "place_id": place_id, "candidates": [{"kind": "place_family_boost", "family": family, "atk": 300, "target": "team_members"}, {"kind": "place_opponent_debuff", "amount": 300, "target": "opponents"}, {"kind": "place_heal", "amount": 500, "target": "team_members"}], "selected": None, "sacrifices": sacrifices, "locked": False, "created_sim_time": float(self.world.get("simulation_time", 0.0))}
        self.world.setdefault("place_effects", {})[place_id] = effect
        self.record_history("place", place_id, "effect_candidates_created", {"team_id": team_id, "sacrifices": sacrifices})
        self.record_history("team", team_id, "place_effect_candidates_created", {"place_id": place_id, "sacrifices": sacrifices})
        self.save()
        return effect

    def choose_place_effect(self, place_id, index):
        effect = self.world.setdefault("place_effects", {}).get(place_id)
        if not effect or effect.get("locked") or index not in range(len(effect.get("candidates", []))): return False
        effect["selected"] = dict(effect["candidates"][index])
        effect["locked"] = True
        self.record_history("place", place_id, "effect_locked", {"team_id": effect.get("team_id", ""), "effect": effect["selected"]})
        self.save()
        return True

    def create_team_effect_request(self, team_id, requester_id, effect, target_id=""):
        team = self.teams.get(team_id)
        effect = dict(effect or {})
        if not team or requester_id not in team.members or not effect.get("kind"): return None
        target_id = target_id or team.leader
        if target_id not in team.members or target_id == requester_id: return None
        sequence = int(self.world.get("team_request_sequence", 0)) + 1
        self.world["team_request_sequence"] = sequence
        request_id = "team_effect_request_" + str(int(time.time() * 1000)) + "_" + str(sequence)
        now = float(self.world.get("simulation_time", 0.0))
        request = {"id": request_id, "team_id": team_id, "requester": requester_id, "target": target_id, "effect": effect, "approvals": {requester_id: True, target_id: False}, "state": "open", "created_sim_time": now, "events": [{"status": "open", "actor": requester_id, "action": "opened", "sim_time": now}]}
        self.world.setdefault("team_effect_requests", []).append(request)
        self.register_interaction("team_effect_request", request)
        self.record_history("team", team_id, "effect_request_opened", {"request_id": request_id, "requester": requester_id, "target": target_id, "effect": effect})
        self.save()
        return request_id

    def respond_team_effect_request(self, request_id, actor_id, decision):
        request = next((item for item in self.world.setdefault("team_effect_requests", []) if item.get("id") == request_id), None)
        if not request or request.get("state") != "open" or actor_id != request.get("target"): return False
        decision = str(decision or "").lower()
        now = float(self.world.get("simulation_time", 0.0))
        if decision in ["deny", "ignore"]:
            request["state"] = "denied"
            request.setdefault("events", []).append({"status": "denied", "actor": actor_id, "action": decision, "sim_time": now})
            self.transition_interaction("team_effect_request", request, "denied", actor_id, decision)
            self.record_history("team", request.get("team_id", ""), "effect_request_denied", {"request_id": request_id, "actor": actor_id})
            self.save()
            return True
        if decision != "accept": return False
        request.setdefault("approvals", {})[actor_id] = True
        team = self.teams.get(request.get("team_id", ""))
        if not team: return False
        team.team_effect = dict(request.get("effect", {}))
        team.effect_locked = True
        request["state"] = "accepted"
        request.setdefault("events", []).append({"status": "accepted", "actor": actor_id, "action": "accept", "sim_time": now})
        self.transition_interaction("team_effect_request", request, "accepted", actor_id, "accept", {"team_id": team.id, "effect": dict(team.team_effect)})
        self.record_history("team", team.id, "effect_activated", {"request_id": request_id, "effect": dict(team.team_effect)})
        for member_id in team.members: self.record_history("character", member_id, "team_effect_activated", {"team_id": team.id, "request_id": request_id, "effect": dict(team.team_effect)})
        self.save()
        return True

    def create_team_request(self, leader_id, invitee_ids, name="", preferred_place="", reason="ally_team"):
        participants = [str(leader_id)] + [str(item) for item in list(invitee_ids or [])]
        participants = list(dict.fromkeys(participants))
        if leader_id not in self.characters or len(participants) != 3 or any(item not in self.characters for item in participants): return None
        if any(self.characters[item].availability != "free" or self.characters[item].world_status != "in_playground" for item in participants): return None
        if any(item != leader_id and (self.relationship_for(leader_id, item) != "ally" or self.relationship_for(item, leader_id) != "ally") for item in participants): return None
        if preferred_place and preferred_place not in self.places: return None
        sequence = int(self.world.get("team_request_sequence", 0)) + 1
        self.world["team_request_sequence"] = sequence
        request_id = "team_request_" + str(int(time.time() * 1000)) + "_" + str(sequence)
        now = float(self.world.get("simulation_time", 0.0))
        request = {"id": request_id, "leader": leader_id, "participants": participants, "name": str(name or "New Team").strip() or "New Team", "preferred_place": preferred_place, "reason": str(reason or "ally_team"), "approvals": {leader_id: True, **{item: False for item in participants if item != leader_id}}, "state": "in_making", "created_sim_time": now, "events": [{"status": "in_making", "actor": leader_id, "action": "opened", "sim_time": now}]}
        self.world.setdefault("team_requests", []).append(request)
        self.register_interaction("team_request", request)
        self.record_history("character", leader_id, "team_request_opened", {"request_id": request_id, "participants": participants})
        self.save()
        return request_id

    def respond_team_request(self, request_id, actor_id, decision):
        request = next((item for item in self.world.setdefault("team_requests", []) if item.get("id") == request_id), None)
        decision = str(decision or "").lower()
        if not request or request.get("state") not in ["in_making", "open"] or actor_id not in request.get("participants", []): return False
        if decision in ["deny", "cancel"]:
            if decision == "cancel" and actor_id != request.get("leader"): return False
            request["state"] = "denied" if decision == "deny" else "canceled"
            request.setdefault("events", []).append({"status": request["state"], "actor": actor_id, "action": decision, "sim_time": float(self.world.get("simulation_time", 0.0))})
            self.transition_interaction("team_request", request, request["state"], actor_id, decision)
            self.record_history("character", actor_id, "team_request_decision", {"request_id": request_id, "decision": decision})
            self.save()
            return True
        if decision != "accept" or actor_id == request.get("leader"): return False
        actor = self.characters.get(actor_id)
        if not actor or actor.availability != "free" or actor.world_status != "in_playground": return False
        request.setdefault("approvals", {})[actor_id] = True
        request.setdefault("events", []).append({"status": "in_making", "actor": actor_id, "action": "accept", "sim_time": float(self.world.get("simulation_time", 0.0))})
        if all(bool(request["approvals"].get(item)) for item in request.get("participants", [])):
            team = self.create_team(request.get("name", "New Team"), request["participants"], request.get("preferred_place", ""), "", "", request.get("leader", ""), [request.get("preferred_place", "")] if request.get("preferred_place") else [])
            if not team: return False
            request["team_id"] = team.id
            request["state"] = "complete"
            team.formation_state = "complete"
            self.record_history("team", team.id, "formed", {"request_id": request_id, "participants": list(request["participants"])})
            for member_id in request["participants"]: self.record_history("character", member_id, "joined_team", {"team_id": team.id, "request_id": request_id})
        else:
            request["state"] = "in_making"
        self.transition_interaction("team_request", request, request["state"], actor_id, "accept", {"team_id": request.get("team_id", "")})
        self.save()
        return True

    def leave_team(self, team_id, member_id, reason="member_left"):
        team = self.teams.get(team_id)
        if not team or member_id not in team.members: return False
        team.members = [item for item in team.members if item != member_id]
        team.formation_state = "complete" if len(team.members) == 3 else "broken"
        if team.leader == member_id and team.members: team.leader = team.members[0]
        team.formation_requests.append({"kind": "departure", "member": member_id, "reason": reason, "sim_time": float(self.world.get("simulation_time", 0.0))})
        team.formation_requests = team.formation_requests[-50:]
        self.record_history("team", team_id, "member_left", {"member": member_id, "reason": reason, "formation_state": team.formation_state})
        self.record_history("character", member_id, "left_team", {"team_id": team_id, "reason": reason})
        self.save()
        return True

    def create_team_reshape_request(self, team_id, requester_id, add_members=None, remove_members=None, name=""):
        team = self.teams.get(team_id)
        if not team or requester_id != team.leader or team.formation_state not in ["complete", "broken"]: return None
        current = list(team.members)
        removed = [item for item in dict.fromkeys(remove_members or []) if item in current]
        desired = [item for item in current if item not in removed]
        for item in dict.fromkeys(add_members or []):
            if item in self.characters and item not in desired and len(desired) < 3: desired.append(item)
        if len(desired) != 3 or any(item not in self.characters for item in desired): return None
        if any(self.characters[item].availability != "free" or self.characters[item].world_status != "in_playground" for item in desired): return None
        if any(left != right and (self.relationship_for(left, right) != "ally" or self.relationship_for(right, left) != "ally") for left in desired for right in desired): return None
        sequence = int(self.world.get("team_request_sequence", 0)) + 1
        self.world["team_request_sequence"] = sequence
        request_id = "team_reshape_request_" + str(int(time.time() * 1000)) + "_" + str(sequence)
        now = float(self.world.get("simulation_time", 0.0))
        approvers = [item for item in desired if item != requester_id]
        request = {"id": request_id, "kind": "reshape", "team_id": team_id, "leader": requester_id, "current_members": current, "desired_members": desired, "add_members": [item for item in desired if item not in current], "remove_members": removed, "name": str(name or team.name).strip() or team.name, "approvals": {requester_id: True, **{item: False for item in approvers}}, "state": "reshaping", "created_sim_time": now, "events": [{"status": "reshaping", "actor": requester_id, "action": "opened", "sim_time": now}]}
        self.world.setdefault("team_requests", []).append(request)
        self.register_interaction("team_request", request)
        self.record_history("team", team_id, "reshape_request_opened", {"request_id": request_id, "current_members": current, "desired_members": desired})
        self.save()
        return request_id

    def respond_team_reshape_request(self, request_id, actor_id, decision):
        request = next((item for item in self.world.setdefault("team_requests", []) if item.get("id") == request_id and item.get("kind") == "reshape"), None)
        if not request or request.get("state") != "reshaping" or actor_id not in request.get("desired_members", []): return False
        decision = str(decision or "").lower()
        now = float(self.world.get("simulation_time", 0.0))
        if decision in ["deny", "cancel"]:
            if decision == "cancel" and actor_id != request.get("leader"): return False
            request["state"] = "denied" if decision == "deny" else "canceled"
            request.setdefault("events", []).append({"status": request["state"], "actor": actor_id, "action": decision, "sim_time": now})
            self.transition_interaction("team_request", request, request["state"], actor_id, decision)
            self.record_history("team", request.get("team_id", ""), "reshape_request_" + request["state"], {"request_id": request_id, "actor": actor_id})
            self.save()
            return True
        if decision != "accept": return False
        actor = self.characters.get(actor_id)
        if not actor or actor.availability != "free" or actor.world_status != "in_playground": return False
        request.setdefault("approvals", {})[actor_id] = True
        request.setdefault("events", []).append({"status": "reshaping", "actor": actor_id, "action": "accept", "sim_time": now})
        if not all(bool(request["approvals"].get(item)) for item in request.get("desired_members", [])): self.save(); return True
        team = self.teams.get(request.get("team_id", ""))
        if not team: return False
        team.members = list(request["desired_members"])
        team.leader = request.get("leader") if request.get("leader") in team.members else team.members[0]
        team.name = request.get("name", team.name)
        team.formation_state = "complete"
        request["state"] = "accepted"
        request["team_id"] = team.id
        self.transition_interaction("team_request", request, "accepted", actor_id, "accepted")
        self.record_history("team", team.id, "team_reshaped", {"request_id": request_id, "members": list(team.members)})
        for member_id in team.members: self.record_history("character", member_id, "team_reshaped", {"team_id": team.id, "members": list(team.members)})
        self.save()
        return True

    def normalize_duel_reward(self, policy="random_card", reward=None):
        raw = reward if isinstance(reward, dict) else policy if isinstance(policy, dict) else {"mode": str(policy or "random_card")}
        key = str(raw.get("mode", raw.get("policy", "random_card"))).lower().replace("-", "_").replace(" ", "_")
        aliases = {"random_card": "random", "random": "random", "deck_random": "random", "library_random": "random", "preset": "preset", "preselected": "preset", "none": "none", "no_reward": "none"}
        mode = aliases.get(key, "random")
        source = str(raw.get("source", "deck" if key == "deck_random" else "library")).lower()
        if source not in ["library", "deck"]: source = "library"
        card_ids = [str(item) for item in list(raw.get("card_ids", []) or []) if str(item) in self.cards][:3]
        count = max(0, min(3, int(raw.get("count", 1) or 0)))
        card_kind = str(raw.get("card_kind", raw.get("kind", ""))).lower()
        family = str(raw.get("family", "")).lower()
        return {"mode": mode, "source": source, "card_ids": card_ids, "count": count, "card_kind": card_kind, "family": family, "giver_id": str(raw.get("giver_id", "")), "trigger": str(raw.get("trigger", "loser_to_winner")), "duel_required": bool(raw.get("duel_required", False)), "label": str(raw.get("label", ""))}

    def reward_policy_key(self, policy):
        return self.normalize_duel_reward(policy).get("mode", "random")

    def select_duel_reward_cards(self, loser_id, policy, sequence=0):
        reward = self.normalize_duel_reward(policy)
        source_id = reward.get("giver_id") or loser_id
        if reward["mode"] == "none" or source_id not in self.characters or source_id == "": return []
        if reward.get("trigger") in ["loser_to_winner", "placer_loss"] and source_id != loser_id: return []
        loser = self.characters[source_id]
        owned = list(loser.library_cards)
        if reward["source"] == "deck":
            deck = self.decks.get(loser.deck_id, {}) if loser.deck_id else {}
            deck_ids = DeckRules.all_cards(deck) if isinstance(deck, dict) else []
            owned = [card_id for card_id in deck_ids if card_id in owned]
        candidates = []
        for card_id in owned:
            card = self.cards.get(card_id)
            if not card: continue
            if reward["card_kind"] and card.kind.lower() != reward["card_kind"]: continue
            if reward["family"] and card.family.lower() != reward["family"]: continue
            candidates.append(card_id)
        selected = []
        if reward["mode"] == "preset":
            for card_id in reward["card_ids"]:
                if card_id in candidates and card_id not in selected: selected.append(card_id)
        else:
            randomizer = random.Random(int(self.world.get("simulation_time", 0.0) * 1000) + int(sequence or 0) + len(candidates) * 17)
            randomizer.shuffle(candidates)
            selected = candidates[:reward["count"] or 1]
        return selected[:3]

    def transfer_duel_reward(self, winner_id, loser_id, policy, sequence=0):
        if not winner_id or not loser_id or winner_id not in self.characters or loser_id not in self.characters: return []
        reward = self.normalize_duel_reward(policy)
        source_id = reward.get("giver_id") or loser_id
        if source_id == winner_id or reward.get("trigger") == "placer_loss" and source_id != loser_id: return []
        selected = self.select_duel_reward_cards(loser_id, reward, sequence)
        winner, loser = self.characters[winner_id], self.characters[source_id]
        transferred = []
        for card_id in selected:
            if card_id in loser.library_cards:
                loser.library_cards.remove(card_id)
                winner.library_cards.append(card_id)
                transferred.append(card_id)
        if transferred:
            self.world.setdefault("simulation_events", []).append({"type": "duel_reward_transfer", "winner": winner_id, "loser": loser_id, "cards": list(transferred), "policy": reward, "sim_time": float(self.world.get("simulation_time", 0.0))})
            self.queue_interaction_media("duel_reward", "reward_transfer", winner_id, loser_id, self.relationship_for(winner_id, loser_id), "characters", winner_id, {"cards": list(transferred)})
        return transferred

    def choose_ai_order(self, character_id):
        character = self.characters.get(character_id)
        if not character: return None
        candidates = [item for item in self.world.setdefault("orders", []) if item.get("status") == "open" and item.get("placer") != character_id and (not item.get("taker") or item.get("taker") == character_id) and (not item.get("place") or item.get("place") in self.places) and (not item.get("deck_id") or item.get("deck_id") in self.decks) and (not item.get("preferred_deck_id") or item.get("preferred_deck_id") in self.decks)]
        if not candidates: return None
        def score(order):
            reward = self.normalize_duel_reward(order.get("reward", order.get("reward_policy", "random_card")))
            relation = self.relationship_for(character_id, order.get("placer", ""))
            relation_score = self._relationship_score(character, self.characters[order.get("placer")]) if order.get("placer") in self.characters else 0.0
            place_score = float(character.behavior_weights.get("place_preference", 5.0)) if order.get("place") in character.preferred_places else 0.0
            reward_score = float(character.behavior_weights.get("reward_value", 5.0)) * (len(reward.get("card_ids", [])) + (1 if reward.get("mode") != "none" else 0))
            enemy_pressure = float(character.behavior_weights.get("enemy_bias", 6.0)) if relation == "enemy" else 0.0
            return reward_score + place_score + relation_score + enemy_pressure
        return max(candidates, key=lambda item: (score(item), item.get("id", "")))

    def normalize_duel_terms(self, format_name="1v1", duel_mode="current", time_limit=180.0, wager_count=0, house_cards=None, guest_cards=None):
        key = str(duel_mode or "current").lower().replace("-", "_").replace(" ", "_")
        aliases = {"current": "current", "classic": "current", "standard": "current", "timed": "timed", "time": "timed", "gamble": "gamble", "wager": "gamble"}
        mode = aliases.get(key, "current")
        format_name = str(format_name or "1v1")
        valid = format_name in DUEL_MODE_FORMATS.get(mode, [])
        try: limit = float(time_limit)
        except (TypeError, ValueError): limit = 180.0
        limit = max(1.0, min(3600.0, limit)) if mode == "timed" else 0.0
        def clean(items): return [str(item) for item in list(items or []) if str(item) in self.cards][:10]
        house_cards = clean(house_cards)
        guest_cards = clean(guest_cards)
        try: count = max(0, min(10, int(wager_count or 0)))
        except (TypeError, ValueError): count = 0
        if mode == "gamble":
            count = max(count, len(house_cards), len(guest_cards))
            if count == 0: count = 1
            valid = valid and len(house_cards) in [0, count] and len(guest_cards) in [0, count]
        else:
            count, house_cards, guest_cards = 0, [], []
        return {"mode": mode, "format": format_name, "valid": bool(valid), "time_limit": limit, "wager_count": count, "house_cards": house_cards, "guest_cards": guest_cards, "selection": "winner_selects_one" if mode == "gamble" else "none", "state": "unprepared"}

    def reserve_gamble_terms(self, house_id, guest_id, terms):
        terms = dict(terms or {})
        if terms.get("mode") != "gamble" or terms.get("format", "1v1") != "1v1": return None
        house = self.characters.get(house_id)
        guest = self.characters.get(guest_id)
        count = int(terms.get("wager_count", 0) or 0)
        if not house or not guest or count < 1 or count > 10: return None
        def choose(character, requested, seed):
            requested = list(requested or [])
            if requested:
                if len(requested) != count or any(character.library_cards.count(card_id) < requested.count(card_id) for card_id in set(requested)): return None
                return requested
            candidates = list(dict.fromkeys(card_id for card_id in character.library_cards if card_id in self.cards))
            randomizer = random.Random(seed + sum(ord(item) for item in character.id))
            randomizer.shuffle(candidates)
            selected = candidates[:count]
            return selected if len(selected) == count else None
        seed = int(self.world.get("simulation_time", 0.0) * 1000) + int(self.world.get("duel_sequence", 0)) + count * 97
        house_cards = choose(house, terms.get("house_cards"), seed)
        guest_cards = choose(guest, terms.get("guest_cards"), seed + 31)
        if house_cards is None or guest_cards is None: return None
        for card_id in house_cards: house.library_cards.remove(card_id)
        for card_id in guest_cards: guest.library_cards.remove(card_id)
        prepared = {"mode": "gamble", "format": "1v1", "wager_count": count, "pools": {house_id: list(house_cards), guest_id: list(guest_cards)}, "house": house_id, "guest": guest_id, "selected_card": "", "revealed": [], "returned": [], "state": "reserved", "settled": False}
        return prepared

    def settle_gamble_terms(self, winner_id, loser_id, state, selected_card=""):
        state = dict(state or {})
        pools = {str(key): list(value or []) for key, value in dict(state.get("pools", {})).items()}
        house_id, guest_id = state.get("house", ""), state.get("guest", "")
        house, guest = self.characters.get(house_id), self.characters.get(guest_id)
        winner, loser = self.characters.get(winner_id), self.characters.get(loser_id)
        if not house or not guest or not winner or not loser or set(pools) != {house_id, guest_id} or state.get("settled"): return None
        chosen = str(selected_card or "")
        loser_pool = pools.get(loser_id, [])
        if chosen not in loser_pool: chosen = ""
        for card_id in pools.get(house_id, []): house.library_cards.append(card_id)
        for card_id in pools.get(guest_id, []): guest.library_cards.append(card_id)
        transferred = []
        if chosen:
            if chosen not in loser.library_cards: return None
            loser.library_cards.remove(chosen)
            winner.library_cards.append(chosen)
            transferred.append(chosen)
        state.update({"selected_card": chosen, "revealed": list(dict.fromkeys(pools.get(house_id, []) + pools.get(guest_id, []))), "returned": [card_id for pool in pools.values() for card_id in pool if card_id != chosen], "transferred": transferred, "state": "settled", "settled": True})
        if chosen:
            self.world.setdefault("simulation_events", []).append({"type": "gamble_card_selected", "winner": winner_id, "loser": loser_id, "card": chosen, "sim_time": float(self.world.get("simulation_time", 0.0))})
        return state

    def choose_ai_gamble_card(self, winner_id, loser_id, state):
        winner = self.characters.get(winner_id)
        if not winner: return ""
        pool = list(dict.fromkeys(dict(state or {}).get("pools", {}).get(loser_id, [])))
        if not pool: return ""
        risk = float(winner.behavior_weights.get("risk_tolerance", 5.0))
        known = winner.knowledge_state.setdefault("cards", {})
        def score(card_id):
            card = self.cards.get(card_id)
            if not card: return -1.0
            base = float(card.atk + card.defense) if card.kind in ["normal", "effect", "fusion", "ritual", "legendary"] else 500.0
            familiarity = float(known.get(card_id, {}).get("sightings", 0)) if isinstance(known.get(card_id, {}), dict) else 0.0
            preference = 50.0 if card.family.lower() in winner.preferred_families else 0.0
            return base + familiarity * risk + preference
        return max(pool, key=lambda card_id: (score(card_id), card_id))

    def return_gamble_terms(self, state):
        state = dict(state or {})
        if state.get("settled"): return state
        pools = dict(state.get("pools", {}))
        for owner_id, cards in pools.items():
            owner = self.characters.get(owner_id)
            if owner:
                for card_id in cards: owner.library_cards.append(card_id)
        state.update({"revealed": [card_id for cards in pools.values() for card_id in cards], "returned": [card_id for cards in pools.values() for card_id in cards], "state": "returned", "settled": True})
        return state

    def add_request(self, from_id, to_id, reason, kind="duel", format_name="1v1", preferred_place=None, relationship_intent="stranger", deck_id="", reward_policy="random_card", expires_in=10800, reward=None, duel_mode="current", time_limit=180.0, wager_count=0, house_cards=None, guest_cards=None):
        preferred_place = preferred_place or self.role_config()["default_place"]
        relationship_intent = str(relationship_intent or "stranger").lower()
        if from_id not in self.characters or to_id not in self.characters or from_id == to_id or preferred_place not in self.places: return None
        if relationship_intent not in ["stranger", "ally", "enemy"]: relationship_intent = "stranger"
        if format_name not in ["1v1", "1vTEAM", "TEAMv1", "TEAMvTEAM"]: return None
        duel_terms = self.normalize_duel_terms(format_name, duel_mode, time_limit, wager_count, house_cards, guest_cards)
        if not duel_terms.get("valid"): return None
        sequence = int(self.world.get("request_sequence", 0)) + 1
        self.world["request_sequence"] = sequence
        request_id = "request_" + str(int(time.time() * 1000)) + "_" + str(sequence)
        now = float(self.world.get("simulation_time", 0.0))
        normalized_reward = self.normalize_duel_reward(reward_policy, reward)
        request = {"id": request_id, "title": f"{from_id} requests a {reason}", "from": from_id, "to": to_id, "kind": kind, "reason": reason, "relationship_intent": relationship_intent, "intent": relationship_intent, "format": format_name, "preferred_place": preferred_place, "deck_id": deck_id if deck_id in self.decks else "", "reward_policy": normalized_reward["mode"], "reward": normalized_reward, "duel_mode": duel_terms["mode"], "duel_terms": duel_terms, "status": "open", "created_sim_time": now, "expires_sim_time": now + max(1, float(expires_in)), "events": [{"status": "open", "actor": from_id, "action": "open", "sim_time": now}]}
        self.world.setdefault("requests", []).append(request)
        self.register_interaction("request", request)
        self.queue_interaction_media("request", "request_open", from_id, to_id, relationship_intent, "characters", from_id, {"request_id": request_id, "reason": reason})
        sender = self.characters[from_id]
        sender.history.append({"event": "request_sent", "request_id": request_id, "to": to_id, "intent": relationship_intent, "reason": reason, "time": time.time()})
        sender.history = sender.history[-100:]
        self.save()
        return request_id

    def request_by_id(self, request_id):
        return next((request for request in self.world.setdefault("requests", []) if request.get("id") == request_id), None)

    def respond_request(self, request_id, actor_id, decision):
        request = self.request_by_id(request_id)
        decision = str(decision or "").lower()
        if not request or request.get("status") != "open" or actor_id not in [request.get("from"), request.get("to")]: return False
        sender_id, recipient_id = request.get("from"), request.get("to")
        if decision == "cancel":
            if actor_id != sender_id: return False
            status = "canceled"
        elif decision in ["accept", "deny", "ignore"]:
            if actor_id != recipient_id: return False
            status = {"accept": "queued", "deny": "denied", "ignore": "ignored"}[decision]
        else: return False
        now = float(self.world.get("simulation_time", 0.0))
        self.transition_interaction("request", request, status, actor_id, decision)
        self.queue_interaction_media("request", "request_" + status, actor_id, recipient_id if actor_id == sender_id else sender_id, request.get("relationship_intent", "stranger"), "characters", actor_id, {"request_id": request_id, "decision": decision})
        request["status"] = status
        actor = self.characters.get(actor_id)
        other = self.characters.get(recipient_id if actor_id == sender_id else sender_id)
        if actor:
            actor.history.append({"event": "request_response", "request_id": request_id, "decision": decision, "other": other.id if other else "", "time": time.time()})
            actor.history = actor.history[-100:]
        if other:
            other.history.append({"event": "request_received", "request_id": request_id, "decision": decision, "other": actor_id, "time": time.time()})
            other.history = other.history[-100:]
        if status == "queued":
            request["queued_sim_time"] = now
            request["accepted_by"] = actor_id
            request["house_player"] = actor_id
            request["guest_player"] = request.get("to") if actor_id == request.get("from") else request.get("from")
            intent = request.get("relationship_intent", "stranger")
            if intent in ["ally", "enemy"]:
                self.set_relationship(sender_id, recipient_id, intent, "request accepted")
                self.set_relationship(recipient_id, sender_id, intent, "request accepted")
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
        if not sender or not recipient or sender.world_status != "in_playground" or recipient.world_status != "in_playground" or sender.availability not in ["free", "traveling"] or recipient.availability not in ["free", "traveling"]: return False
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
            house = self.characters.get(house_id)
            relation = self.relationship_for(house_id, guest_id)
            acceptance_score = float((house.behavior_weights if house else {}).get("accept_first", 0.0)) + (2.0 if relation == "ally" else -1.0 if relation == "enemy" else 0.0)
            accepts_first = acceptance_score >= 8.0
            request_cue = self.narrator_cue("request_first", guest_id, house_id, {"format": request.get("format", "1v1"), "launcher": house_id})
            decision_cue = self.narrator_cue("ready" if accepts_first else "dice_intro", guest_id, house_id, {"format": request.get("format", "1v1"), "launcher": house_id})
            duel_terms = self.normalize_duel_terms(request.get("format", "1v1"), request.get("duel_mode", "current"), request.get("duel_terms", {}).get("time_limit", 180.0) if isinstance(request.get("duel_terms", {}), dict) else 180.0, request.get("duel_terms", {}).get("wager_count", 0) if isinstance(request.get("duel_terms", {}), dict) else 0, request.get("duel_terms", {}).get("house_cards", []) if isinstance(request.get("duel_terms", {}), dict) else [], request.get("duel_terms", {}).get("guest_cards", []) if isinstance(request.get("duel_terms", {}), dict) else [])
            prepared_terms = duel_terms
            if duel_terms.get("mode") == "gamble":
                prepared_terms = self.reserve_gamble_terms(house_id, guest_id, duel_terms)
                if not prepared_terms:
                    request["status"] = "denied"
                    request.setdefault("events", []).append({"status": "denied", "actor": "world", "action": "gamble_unavailable", "sim_time": float(self.world.get("simulation_time", 0.0))})
                    self.release_place(place_id)
                    for character_id in [request.get("from"), request.get("to")]:
                        character = self.characters.get(character_id)
                        if character: character.availability, character.activity = "free", "idle"
                    continue
            if accepts_first:
                dice = {"type": "spin_dice_result", "skipped": True, "launcher": house_id, "requester": guest_id, "value": None, "range": "requester", "first": guest_id, "sim_time": float(self.world.get("simulation_time", 0.0))}
                first_side = "opponent"
            else:
                dice = self.spin_dice_result(house_id, guest_id)
                first_side = "player" if dice["first"] == house_id else "opponent"
                result_cue = self.narrator_cue("result_launcher" if dice["value"] <= 3 else "result_requester", guest_id, house_id, {"format": request.get("format", "1v1"), "launcher": house_id, "value": dice["value"]})
            engine = DuelEngine(self, house_id, guest_id, place_id, True, first_side=first_side, duel_mode=duel_terms.get("mode", "current"), time_limit=duel_terms.get("time_limit", 0.0), duel_terms=prepared_terms)
            engine.match_recorded = True
            battle_id = "sim_battle_" + str(int(time.time() * 1000))
            battle = {"id": battle_id, "request_id": request["id"], "from": request["from"], "to": request["to"], "house": house_id, "guest": guest_id, "accepted_by": request.get("accepted_by", house_id), "format": request.get("format", "1v1"), "place": place_id, "status": "active", "phase": "pre_duel", "elapsed": 0.0, "next_action": 3.0, "actions": [], "turn": engine.turn, "first_side": first_side, "spin_dice": dice, "duel_mode": duel_terms.get("mode", "current"), "time_limit": duel_terms.get("time_limit", 0.0), "duel_terms": prepared_terms, "pre_duel": {"requester": guest_id, "acceptor": house_id, "decision": "accept" if accepts_first else "deny", "acceptance_score": acceptance_score, "narrator_states": [request_cue["state"], decision_cue["state"]] + ([] if accepts_first else [result_cue["state"]])}, "reward": dict(request.get("reward", {})), "hp": {house_id: engine.player.hp, guest_id: engine.opponent.hp}, "started_sim_time": float(self.world.get("simulation_time", 0.0)), "result": "", "engine_checkpoint": engine.state_checkpoint()}
            self.world_sessions[battle_id] = engine
            self.world.setdefault("active_battles", []).append(battle)
            self.world.setdefault("simulation_events", []).append({"type": "battle_activated", "battle": battle["id"], "request": request["id"], "sim_time": float(self.world.get("simulation_time", 0.0))})

    def _world_session(self, battle):
        session = self.world_sessions.get(battle["id"])
        if session: return session
        house_id = battle.get("house") or battle.get("accepted_by") or battle.get("to") or battle.get("from")
        guest_id = battle.get("guest") or (battle.get("to") if house_id == battle.get("from") else battle.get("from"))
        battle["house"], battle["guest"] = house_id, guest_id
        first_side = battle.get("first_side") if battle.get("first_side") in ["player", "opponent"] else "opponent"
        duel_mode = battle.get("duel_mode", "current")
        time_limit = float(battle.get("time_limit", 0.0) or 0.0)
        duel_terms = battle.get("duel_terms") if isinstance(battle.get("duel_terms"), dict) else None
        session = DuelEngine(self, house_id, guest_id, battle["place"], True, first_side=first_side, duel_mode=duel_mode, time_limit=time_limit, duel_terms=duel_terms)
        session.match_recorded = True
        checkpoint = battle.get("engine_checkpoint")
        if checkpoint and not session.restore_state_checkpoint(checkpoint): return None
        session.set_watchers(list(battle.get("watchers", [])))
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
        reward = battle.get("reward", {})
        if request:
            request["status"] = "completed"
            request.setdefault("events", []).append({"status": "completed", "actor": winner_id or "world", "sim_time": float(self.world.get("simulation_time", 0.0))})
            reward = request.get("reward", reward)
            self.transition_interaction("request", request, "completed", winner_id or "world", "completed", {"winner": winner_id, "loser": loser_id, "reward": reward})
        if session.gamble_selection_pending and winner_id and loser_id:
            selected = self.choose_ai_gamble_card(winner_id, loser_id, session.gamble_state)
            session.resolve_gamble_selection(selected)
        elif session.gamble_state and not session.gamble_state.get("settled"):
            session.gamble_state = self.return_gamble_terms(session.gamble_state)
        battle["duel_terms"] = dict(session.gamble_state) if session.gamble_state else battle.get("duel_terms", {})
        settled_cards = list(session.gamble_state.get("transferred", [])) if session.gamble_state else []
        record_reward = {"mode": "none"} if battle.get("duel_mode") == "gamble" else reward
        self.record_duel(winner_id, loser_id, session.turn, session.reason or "engine_simulation", record_reward, {"mode": battle.get("duel_mode", "current"), "place": battle.get("place", ""), "finisher": session.reason or "engine_simulation", "deck_ids": {battle.get("house", ""): battle.get("house_deck_id", ""), battle.get("guest", ""): battle.get("guest_deck_id", "")}, "transferred_cards": settled_cards})
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
        battle.setdefault("actions", [])
        battle.setdefault("first_side", "opponent")
        battle.setdefault("spin_dice", {})
        battle.setdefault("reward", {})
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

    def _world_team_session(self, battle):
        session = self.world_team_sessions.get(battle.get("id", ""))
        if session: return session
        player_team = self.teams.get(battle.get("player_team", ""))
        opponent_team = self.teams.get(battle.get("opponent_team", ""))
        if not player_team or not opponent_team or battle.get("place", "") not in self.places: return None
        session = TeamDuelEngine(self, player_team_id=player_team.id, opponent_team_id=opponent_team.id, place_id=battle.get("place", ""), player_team=player_team, opponent_team=opponent_team, format_name="TEAMvTEAM", starter=battle.get("starter", "opponent"), reserved=True)
        self.world_team_sessions[battle["id"]] = session
        return session

    def _complete_world_team_battle(self, battle, session):
        winner_id = session.winner.id if session.winner else ""
        loser_id = session.opponent_team.id if session.winner is session.player_team else session.player_team.id if session.winner else ""
        battle.update({"status": "completed", "phase": "post_duel", "result": winner_id, "turn": session.round, "rounds": list(session.results), "completed_sim_time": float(self.world.get("simulation_time", 0.0))})
        championship_id = battle.get("championship_id", "")
        championship = self.championship_by_id(championship_id) if championship_id else None
        if championship:
            championship["active_battle_ids"] = [item for item in championship.get("active_battle_ids", []) if item != battle.get("id", "")]
        if championship_id and winner_id:
            self.resolve_championship_match(championship_id, int(battle.get("championship_round", 0)), int(battle.get("championship_pair", 0)), winner_id)
        for team_id in [battle.get("player_team", ""), battle.get("opponent_team", "")]:
            team = self.teams.get(team_id)
            if team:
                for member_id in team.members:
                    character = self.characters.get(member_id)
                    if character:
                        character.availability = "free"
                        character.activity = "idle"
                        character.cooldown_until = float(self.world.get("simulation_time", 0.0)) + 5.0
        self.release_place(battle.get("place", ""))
        self.world_team_sessions.pop(battle.get("id", ""), None)
        completion_event = {"type": "team_battle_completed", "battle": battle.get("id", ""), "winner": winner_id or "draw", "loser": loser_id, "championship": championship_id, "watchers": list(battle.get("watchers", [])), "sim_time": float(self.world.get("simulation_time", 0.0))}
        self.world.setdefault("simulation_events", []).append(completion_event)

    def _advance_team_battles(self, seconds):
        for battle in list(self.world.setdefault("active_battles", [])):
            if battle.get("status") != "active" or battle.get("engine_type") != "team": continue
            previous_elapsed = float(battle.get("elapsed", 0.0))
            battle["elapsed"] = previous_elapsed + seconds
            if battle.get("phase") == "pre_duel" and battle["elapsed"] >= 3.0: battle["phase"] = "duel"
            session = self._world_team_session(battle)
            if not session: continue
            steps = 0
            while battle["elapsed"] >= float(battle.get("next_action", 3.0)) and battle.get("status") == "active" and steps < 3:
                session.step()
                battle["round"] = session.round
                battle["rounds"] = list(session.results)
                battle["next_action"] = float(battle.get("next_action", 3.0)) + 2.0
                steps += 1
                if session.finished:
                    self._complete_world_team_battle(battle, session)
                    break

    def _advance_battles(self, seconds):
        for battle in list(self.world.setdefault("active_battles", [])):
            if battle.get("status") != "active" or battle.get("engine_type") == "team": continue
            previous_elapsed = float(battle.get("elapsed", 0.0))
            battle["elapsed"] = previous_elapsed + seconds
            duel_seconds = max(0.0, battle["elapsed"] - max(previous_elapsed, 3.0))
            if battle["phase"] == "pre_duel" and battle["elapsed"] >= 3.0: battle["phase"] = "duel"
            if duel_seconds > 0.0 and battle.get("phase") not in ["pre_duel", "post_duel"]:
                session = self._world_session(battle)
                if session: session.advance_clock(duel_seconds)
                if session and session.finished:
                    self._complete_world_battle(battle, session)
                    continue
            actions = 0
            while battle["elapsed"] >= battle.get("next_action", 3.0) and actions < 3 and battle.get("status") == "active":
                self._simulation_action(battle)
                battle["next_action"] = float(battle.get("next_action", 3.0)) + 2.0
                actions += 1

    def advance_character_idle(self, seconds):
        threshold = float(self.rules.get("narrator", {}).get("idle_seconds", {}).get("character", 30.0) or 30.0)
        for character in self.characters.values():
            if character.world_status != "in_playground" or character.availability != "free" or character.activity != "idle":
                character.idle_elapsed = 0.0
                character.idle_cue_count = 0
                continue
            character.idle_elapsed += max(0.0, float(seconds))
            while character.idle_elapsed >= threshold:
                character.idle_elapsed -= threshold
                character.idle_cue_count = int(getattr(character, "idle_cue_count", 0)) + 1
                self.world.setdefault("simulation_events", []).append({"type": "character_idle", "state": "character_idle", "character": character.id, "cadence": character.idle_cue_count, "sim_time": float(self.world.get("simulation_time", 0.0))})

    def advance_world(self, seconds=None):
        if seconds is None:
            current_wall_time = time.time()
            try: previous_wall_time = float(self.world.get("last_wall_time", current_wall_time) or current_wall_time)
            except (TypeError, ValueError): previous_wall_time = current_wall_time
            seconds = max(0.0, current_wall_time - previous_wall_time)
            self.world["last_wall_time"] = current_wall_time
        else:
            seconds = max(0.0, float(seconds))
        checkpoint = False
        self.world_tick_active = True
        try:
            self.world["simulation_time"] = float(self.world.get("simulation_time", 0.0)) + seconds
            self.advance_character_idle(seconds)
            self._advance_movement(seconds)
            self._advance_out_of_game()
            for request in self.world.setdefault("requests", []):
                if request.get("status") in ["open", "queued"] and self.world["simulation_time"] >= float(request.get("expires_sim_time", 0.0)):
                    self.transition_interaction("request", request, "expired", "world", "expired")
            for order in self.world.setdefault("orders", []):
                if order.get("status") == "open" and float(order.get("expires_sim_time", 0.0)) > 0 and self.world["simulation_time"] >= float(order.get("expires_sim_time", 0.0)):
                    self.transition_interaction("order", order, "expired", "world", "expired")
            self._advance_battles(seconds)
            self._advance_team_battles(seconds)
            self._advance_trades()
            self._advance_borrow_requests()
            self._advance_championships()
            self._activate_queued_requests()
            self._ai_request_tick()
            self._ai_trade_tick()
            self._ai_borrow_tick()
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

    def place_order(self, placer, taker, give, deck_id="", place_id="", reward_policy="random_card", expires_in=10800, intent="duel_order", reward=None, preferred_deck_id="", duel_mode="current", time_limit=180.0, wager_count=0, house_cards=None, guest_cards=None):
        normalized_reward = self.normalize_duel_reward(reward_policy, reward)
        duel_terms = self.normalize_duel_terms("1v1", duel_mode, time_limit, wager_count, house_cards, guest_cards)
        if not duel_terms.get("valid") or placer not in self.characters or taker and taker not in self.characters: return None
        sequence = int(self.world.get("order_sequence", 0)) + 1
        self.world["order_sequence"] = sequence
        order_id = "order_" + str(int(time.time() * 1000)) + "_" + str(sequence)
        now = float(self.world.get("simulation_time", 0.0))
        order = {"id": order_id, "title": f"Order by {placer}: {give}", "placer": placer, "taker": taker or "", "give": give, "deck_id": deck_id if deck_id in self.decks else "", "preferred_deck_id": preferred_deck_id if preferred_deck_id in self.decks else "", "place": place_id if place_id in self.places else "", "reward_policy": normalized_reward["mode"], "reward": normalized_reward, "duel_mode": duel_terms["mode"], "duel_terms": duel_terms, "intent": intent, "status": "open", "created_sim_time": now, "expires_sim_time": now + max(1.0, float(expires_in)), "events": [{"status": "open", "actor": placer, "action": "open", "sim_time": now}]}
        self.world.setdefault("orders", []).append(order)
        self.register_interaction("order", order)
        self.queue_interaction_media("order", "order_open", placer, taker or "", "opponent", "characters", placer, {"order_id": order_id, "give": give})
        self.save()
        return order_id

    def interaction_list(self, family="", status=""):
        records = list(self.world.setdefault("interactions", []))
        if family: records = [item for item in records if item.get("family") == family]
        if status: records = [item for item in records if item.get("status") == status]
        return sorted(records, key=lambda item: (float(item.get("created_sim_time", 0.0)), item.get("id", "")), reverse=True)

    def world_battle_by_id(self, battle_id):
        return next((item for item in self.world.setdefault("active_battles", []) if item.get("id") == battle_id), None)

    def add_battle_watcher(self, battle_id, watcher_id):
        battle = self.world_battle_by_id(battle_id)
        if not battle or battle.get("status") != "active" or watcher_id not in self.characters: return False
        house_id = battle.get("house") or battle.get("accepted_by") or battle.get("to") or battle.get("from")
        guest_id = battle.get("guest") or (battle.get("to") if house_id == battle.get("from") else battle.get("from"))
        if watcher_id in [house_id, guest_id]: return False
        watchers = list(battle.setdefault("watchers", []))
        if watcher_id not in watchers and len(watchers) >= 6: return False
        if watcher_id not in watchers: watchers.append(watcher_id)
        battle["watchers"] = watchers[:6]
        character = self.characters[watcher_id]
        character.availability = "watching"
        character.activity = "watching"
        character.current_place = battle.get("place", character.current_place)
        relation = self.relationship_for(watcher_id, house_id)
        self.queue_interaction_media("watching", "watching_in", watcher_id, house_id, relation, "characters", watcher_id, {"battle_id": battle_id, "side": "left" if len(watchers) % 2 else "right"})
        session = self.world_sessions.get(battle_id) or self._world_session(battle)
        if session: session.set_watchers(watchers)
        self.save()
        return True

    def remove_battle_watcher(self, battle_id, watcher_id):
        battle = self.world_battle_by_id(battle_id)
        if not battle: return False
        watchers = list(battle.setdefault("watchers", []))
        if watcher_id not in watchers: return False
        watchers.remove(watcher_id)
        battle["watchers"] = watchers
        character = self.characters.get(watcher_id)
        if character and character.activity == "watching":
            character.activity = "idle"
            character.availability = "free"
        house_id = battle.get("house") or battle.get("accepted_by") or battle.get("to") or battle.get("from")
        relation = self.relationship_for(watcher_id, house_id)
        self.queue_interaction_media("watching", "watching_out", watcher_id, house_id, relation, "characters", watcher_id, {"battle_id": battle_id})
        session = self.world_sessions.get(battle_id)
        if session: session.set_watchers(watchers)
        self.save()
        return True

    def respond_order(self, order_id, actor_id, decision):
        order = next((item for item in self.world.setdefault("orders", []) if item.get("id") == order_id), None)
        decision = str(decision or "").lower()
        if not order or order.get("status") != "open": return False
        placer = order.get("placer", "")
        taker = order.get("taker", "")
        original_taker = taker
        if decision == "cancel":
            if actor_id != placer: return False
            status = "canceled"
        elif decision in ["accept", "deny", "ignore"]:
            if actor_id == placer or taker and actor_id != taker: return False
            status = {"accept": "accepted", "deny": "denied", "ignore": "ignored"}[decision]
            if decision == "accept" and not taker: order["taker"] = actor_id
        else: return False
        if status == "accepted":
            previous_taker = original_taker
            order_terms = order.get("duel_terms", {}) if isinstance(order.get("duel_terms", {}), dict) else {}
            request_id = self.add_request(placer, actor_id, "duel order: " + str(order.get("give", "reward")), kind="duel_order", format_name="1v1", preferred_place=order.get("place") or self.role_config()["default_place"], deck_id=order.get("preferred_deck_id") or order.get("deck_id", ""), relationship_intent="stranger", reward_policy=order.get("reward", order.get("reward_policy", "random_card")), expires_in=max(1.0, float(order.get("expires_sim_time", 0.0)) - float(self.world.get("simulation_time", 0.0))), duel_mode=order.get("duel_mode", "current"), time_limit=order_terms.get("time_limit", 180.0), wager_count=order_terms.get("wager_count", 0), house_cards=order_terms.get("house_cards", []), guest_cards=order_terms.get("guest_cards", []))
            if not request_id:
                order["taker"] = previous_taker
                order.pop("accepted_by", None)
                order["duel_request_id"] = ""
                self.transition_interaction("order", order, "open", actor_id, "accept_failed")
                self.save()
                return False
            order["accepted_by"] = actor_id
            order["duel_request_id"] = request_id
            self.transition_interaction("order", order, "fulfilled", actor_id, "accepted", {"duel_request_id": request_id})
        else:
            self.transition_interaction("order", order, status, actor_id, decision)
        self.queue_interaction_media("order", "order_" + status, actor_id, placer, "opponent", "characters", actor_id, {"order_id": order_id, "decision": decision})
        self.save()
        return True

    def close_world_entry(self, collection, entry_id):
        family = {"orders": "order", "requests": "request", "trades": "trade", "borrows": "borrow"}.get(collection, collection.rstrip("s"))
        for entry in self.world.setdefault(collection, []):
            if entry.get("id") == entry_id:
                actor = entry.get("taker") or entry.get("recipient") or entry.get("to") or entry.get("placer") or entry.get("creator") or entry.get("borrower") or "world"
                self.transition_interaction(family, entry, "accepted", actor, "accept")
                self.save()
                return entry
        return None

    def trade_list(self):
        self._advance_trades()
        return list(self.world.setdefault("trades", []))

    def borrow_list(self):
        self._advance_borrow_requests()
        return list(self.world.setdefault("borrows", []))

    def card_names(self, card_ids):
        return ", ".join(self.cards[card_id].name for card_id in card_ids if card_id in self.cards) or "none"

    def owned_counts(self, character_id):
        character = self.characters.get(character_id)
        counts = {}
        if character:
            for card_id in character.library_cards: counts[card_id] = counts.get(card_id, 0) + 1
        return counts

    def social_available(self, character_id):
        character = self.characters.get(character_id)
        if not character or character.world_status != "in_playground" or character.availability != "free": return False
        return not any(item.get("status") == "active" and character_id in [item.get("from"), item.get("to")] for item in self.world.setdefault("active_battles", []))

    def shared_team(self, first_id, second_id):
        return any(first_id in team.members and second_id in team.members and team.formation_state == "complete" for team in self.teams.values())

    def reserved_trade_counts(self, owner_id, exclude_id=""):
        counts = {}
        for trade in self.world.setdefault("trades", []):
            if trade.get("id") == exclude_id or trade.get("creator") != owner_id or trade.get("state") not in ["open", "countered", "deferred"]: continue
            for card_id in trade.get("offered_cards", []): counts[card_id] = counts.get(card_id, 0) + 1
        return counts

    def available_card_counts(self, character_id, exclude_trade_id=""):
        counts = self.owned_counts(character_id)
        for card_id, amount in self.reserved_trade_counts(character_id, exclude_trade_id).items(): counts[card_id] = max(0, counts.get(card_id, 0) - amount)
        for record in self.world.setdefault("borrows", []):
            if record.get("state") == "active" and record.get("lender") == character_id:
                card_id = record.get("card_id", "")
                counts[card_id] = max(0, counts.get(card_id, 0) - 1)
        return counts

    def _card_trade_value(self, character_id, card_id):
        card = self.cards.get(card_id)
        character = self.characters.get(character_id)
        if not card or not character: return 0.0
        value = float(card.stars) * 1.6 + float(card.atk + card.defense) / 1000.0
        value += 2.5 if card_id in character.best_cards or card_id in character.preferred_cards else 0.0
        value += 1.2 if card.family in character.preferred_families else 0.0
        value += float(character.knowledge_state.get("cards", {}).get(card_id, {}).get("sightings", 0)) * 0.05
        return value

    def create_trade(self, creator_id, recipient_id, offered_cards, requested_cards=None, requested_family="", requested_kind=""):
        if creator_id not in self.characters or recipient_id not in self.characters or creator_id == recipient_id: return None
        offered_cards = [str(item) for item in list(offered_cards or [])[:3]]
        requested_cards = [str(item) for item in list(requested_cards or [])[:3]]
        if not offered_cards or any(item not in self.cards for item in offered_cards) or any(item not in self.cards for item in requested_cards): return None
        counts = self.available_card_counts(creator_id)
        if any(counts.get(card_id, 0) < offered_cards.count(card_id) for card_id in set(offered_cards)): return None
        sequence = int(self.world.get("trade_sequence", 0)) + 1
        self.world["trade_sequence"] = sequence
        trade_id = "trade_" + str(int(time.time() * 1000)) + "_" + str(sequence)
        now = float(self.world.get("simulation_time", 0.0))
        active = self.social_available(creator_id) and self.social_available(recipient_id)
        state = "open" if active else "deferred"
        relation = self.relationship_for(creator_id, recipient_id)
        trade = {"id": trade_id, "creator": creator_id, "recipient": recipient_id, "offered_cards": offered_cards, "requested_cards": requested_cards, "requested_family": str(requested_family or "").lower(), "requested_kind": str(requested_kind or "").lower(), "intent": "card_trade", "relationship": relation, "state": state, "parent_id": "", "chain_depth": 0, "created": time.time(), "created_sim_time": now, "expires": now + 10800, "expires_sim_time": now + 10800, "history": [{"actor": creator_id, "action": "opened", "status": state, "sim_time": now, "time": time.time()}], "events": [{"actor": creator_id, "action": "opened", "status": state, "sim_time": now}], "ownership_transferred": False, "next_decision_sim_time": now + 15.0}
        self.world.setdefault("trades", []).append(trade)
        self.register_interaction("trade", trade)
        self.record_history("character", creator_id, "trade_opened", {"trade_id": trade_id, "recipient": recipient_id, "relationship": relation, "state": state})
        self.save()
        return trade

    def get_trade(self, trade_id):
        return next((trade for trade in self.world.setdefault("trades", []) if trade.get("id") == trade_id), None)

    def requested_cards_for(self, trade, character_id):
        if character_id not in self.characters: return []
        counts = self.available_card_counts(character_id)
        requested = list(trade.get("requested_cards", []))
        if requested:
            if any(counts.get(card_id, 0) < requested.count(card_id) for card_id in set(requested)): return []
            return requested
        family = str(trade.get("requested_family", "")).lower()
        kind = str(trade.get("requested_kind", "")).lower()
        candidates = [card_id for card_id in self.characters[character_id].library_cards if card_id in self.cards and counts.get(card_id, 0) > 0 and (not family or self.cards[card_id].family.lower() == family) and (not kind or self.cards[card_id].kind.lower() == kind)]
        return [max(candidates, key=lambda item: (self._card_trade_value(character_id, item), item))] if candidates else []

    def trade_available(self, trade):
        if not trade or trade.get("state") not in ["open", "countered"]: return False
        now = float(self.world.get("simulation_time", 0.0))
        if now >= float(trade.get("expires_sim_time", 0.0) or 0.0): return False
        if not self.social_available(trade.get("creator", "")) or not self.social_available(trade.get("recipient", "")): return False
        counts = self.available_card_counts(trade.get("creator", ""), trade.get("id", ""))
        if any(counts.get(card_id, 0) < trade.get("offered_cards", []).count(card_id) for card_id in set(trade.get("offered_cards", []))): return False
        return bool(self.requested_cards_for(trade, trade.get("recipient", "")))

    def evaluate_trade(self, trade_id, actor_id):
        trade = self.get_trade(trade_id)
        if not trade or actor_id != trade.get("recipient"): return {"decision": "invalid", "score": -999.0}
        requested = self.requested_cards_for(trade, actor_id)
        if not requested: return {"decision": "refuse", "score": -999.0, "reason": "requested_cards_unavailable"}
        actor = self.characters[actor_id]
        relation = self.relationship_for(actor_id, trade.get("creator", ""))
        incoming = sum(self._card_trade_value(actor_id, card_id) for card_id in trade.get("offered_cards", []))
        outgoing = sum(self._card_trade_value(actor_id, card_id) for card_id in requested)
        multiplier = {"ally": 0.82, "stranger": 1.0, "enemy": 1.28}.get(relation, 1.0)
        score = incoming - outgoing * multiplier + float(actor.behavior_weights.get("risk_tolerance", 3.0)) * 0.12
        decision = "accept" if score >= 0.0 else "counter" if score >= -2.5 else "refuse"
        return {"decision": decision, "score": score, "relation": relation, "incoming": incoming, "outgoing": outgoing, "requested": requested}

    def counter_trade(self, trade_id, actor_id, offered_cards, requested_cards=None, requested_family="", requested_kind=""):
        parent = self.get_trade(trade_id)
        if not parent or parent.get("state") not in ["open", "countered"] or parent.get("recipient") != actor_id: return None
        counter = self.create_trade(actor_id, parent["creator"], offered_cards, requested_cards, requested_family, requested_kind)
        if not counter: return None
        counter["parent_id"] = parent["id"]
        counter["chain_depth"] = int(parent.get("chain_depth", 0)) + 1
        counter["state"] = "countered" if counter.get("state") == "open" else counter.get("state")
        counter["history"] = list(parent.get("history", [])) + [{"actor": actor_id, "action": "countered", "status": counter["state"], "parent_id": parent["id"], "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()}]
        counter["events"] = list(parent.get("events", [])) + [{"actor": actor_id, "action": "countered", "status": counter["state"], "sim_time": float(self.world.get("simulation_time", 0.0))}]
        parent["state"] = "countered"
        parent.setdefault("history", []).append({"actor": actor_id, "action": "answered_with_counter", "status": "countered", "child_id": counter["id"], "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()})
        self.transition_interaction("trade", parent, "countered", actor_id, "countered", {"child_id": counter["id"]})
        self.register_interaction("trade", counter)
        self.save()
        return counter

    def accept_trade(self, trade_id, actor_id):
        trade = self.get_trade(trade_id)
        if not trade or trade.get("recipient") != actor_id or not self.trade_available(trade): return False
        requested = self.requested_cards_for(trade, actor_id)
        creator = self.characters.get(trade.get("creator", ""))
        recipient = self.characters.get(trade.get("recipient", ""))
        if not creator or not recipient: return False
        offered = list(trade.get("offered_cards", []))
        if any(creator.library_cards.count(card_id) < offered.count(card_id) for card_id in set(offered)) or any(recipient.library_cards.count(card_id) < requested.count(card_id) for card_id in set(requested)): return False
        for card_id in offered: creator.library_cards.remove(card_id)
        for card_id in requested: recipient.library_cards.remove(card_id)
        recipient.library_cards.extend(offered)
        creator.library_cards.extend(requested)
        now = float(self.world.get("simulation_time", 0.0))
        trade.update({"requested_cards": requested, "state": "accepted", "ownership_transferred": True, "accepted_sim_time": now, "transaction_id": "tx_" + trade["id"]})
        trade.setdefault("history", []).append({"actor": actor_id, "action": "accepted", "status": "accepted", "received": offered, "gave": requested, "sim_time": now, "time": time.time()})
        self.transition_interaction("trade", trade, "accepted", actor_id, "accepted", {"received": offered, "gave": requested, "transaction_id": trade["transaction_id"]})
        self.record_history("character", creator.id, "trade_completed", {"trade_id": trade["id"], "with": recipient.id, "received": requested, "gave": offered})
        self.record_history("character", recipient.id, "trade_completed", {"trade_id": trade["id"], "with": creator.id, "received": offered, "gave": requested})
        for card_id in offered + requested:
            self.discover_card(creator.id, card_id, "traded", recipient.id, {"trade_id": trade["id"]})
            self.discover_card(recipient.id, card_id, "traded", creator.id, {"trade_id": trade["id"]})
        self.save()
        return True

    def cancel_trade(self, trade_id, actor_id):
        trade = self.get_trade(trade_id)
        if not trade or actor_id not in [trade.get("creator"), trade.get("recipient")] or trade.get("state") in ["accepted", "canceled", "expired", "escalated"]: return False
        self.transition_interaction("trade", trade, "canceled", actor_id, "canceled")
        trade["state"] = "canceled"
        trade.setdefault("history", []).append({"actor": actor_id, "action": "canceled", "status": "canceled", "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()})
        self.record_history("character", actor_id, "trade_canceled", {"trade_id": trade_id})
        self.save()
        return True

    def escalate_trade(self, trade_id, actor_id):
        trade = self.get_trade(trade_id)
        if not trade or actor_id not in [trade.get("creator"), trade.get("recipient")] or trade.get("state") not in ["open", "countered"]: return None
        self.transition_interaction("trade", trade, "escalated", actor_id, "escalated")
        trade["state"] = "escalated"
        request_id = self.add_request(actor_id, trade["creator"] if actor_id == trade["recipient"] else trade["recipient"], "high-stakes trade duel")
        trade["duel_request_id"] = request_id
        trade.setdefault("history", []).append({"actor": actor_id, "action": "escalated", "request_id": request_id, "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()})
        self.save()
        return request_id

    def _advance_trades(self):
        now = float(self.world.get("simulation_time", 0.0))
        for trade in self.world.setdefault("trades", []):
            if trade.get("state") in ["open", "countered", "deferred"] and now >= float(trade.get("expires_sim_time", 0.0) or 0.0):
                trade["state"] = "expired"
                self.transition_interaction("trade", trade, "expired", "world", "expired")
                continue
            if trade.get("state") == "deferred" and self.social_available(trade.get("creator", "")) and self.social_available(trade.get("recipient", "")):
                trade["state"] = "open"
                trade.setdefault("history", []).append({"actor": "world", "action": "resumed", "status": "open", "sim_time": now, "time": time.time()})
                self.transition_interaction("trade", trade, "open", "world", "resumed")

    def choose_ai_trade_offer(self, creator_id):
        creator = self.characters.get(creator_id)
        if not creator or creator.origin == "user" or not self.social_available(creator_id): return None
        active = any(item.get("creator") == creator_id and item.get("state") in ["open", "countered", "deferred"] for item in self.world.setdefault("trades", []))
        if active: return None
        desired = [card for card in self.cards.values() if card.id not in creator.library_cards and card.kind != "fusion"]
        if not desired: desired = [card for card in self.cards.values() if card.kind != "fusion"]
        desired.sort(key=lambda card: (1 if card.family in creator.preferred_families else 0, self._card_trade_value(creator_id, card.id), card.id), reverse=True)
        for target in sorted(self.characters.values(), key=lambda item: (-self._relationship_score(creator, item), item.id)):
            if target.id == creator_id or target.origin == "user" or not self.social_available(target.id): continue
            target_counts = self.available_card_counts(target.id)
            requested = next((card for card in desired if target_counts.get(card.id, 0) > 0), None)
            if not requested: continue
            offered = [card_id for card_id in creator.library_cards if self.available_card_counts(creator_id).get(card_id, 0) > 0 and card_id not in creator.preferred_cards]
            if not offered: offered = [card_id for card_id in creator.library_cards if self.available_card_counts(creator_id).get(card_id, 0) > 0]
            if not offered: continue
            offered.sort(key=lambda card_id: (self._card_trade_value(creator_id, card_id), card_id))
            return target.id, [offered[0]], [requested.id]
        return None

    def _ai_trade_tick(self):
        now = float(self.world.get("simulation_time", 0.0))
        if now < float(self.world.get("last_ai_trade_time", 0.0)) + 15.0: return
        self.world["last_ai_trade_time"] = now
        for trade in list(self.world.setdefault("trades", [])):
            if trade.get("state") != "open" or now < float(trade.get("next_decision_sim_time", 0.0)): continue
            recipient = self.characters.get(trade.get("recipient", ""))
            if not recipient or recipient.origin == "user" or not self.social_available(recipient.id): continue
            decision = self.evaluate_trade(trade["id"], recipient.id)
            trade["next_decision_sim_time"] = now + 30.0
            if decision.get("decision") == "accept":
                self.accept_trade(trade["id"], recipient.id)
            elif decision.get("decision") == "counter" and int(trade.get("chain_depth", 0)) < 3:
                candidates = [card_id for card_id in recipient.library_cards if card_id in self.cards and card_id not in trade.get("requested_cards", []) and self.available_card_counts(recipient.id).get(card_id, 0) > 0]
                if candidates:
                    target = min(candidates, key=lambda item: abs(self._card_trade_value(recipient.id, item) - decision.get("incoming", 0.0)))
                    self.counter_trade(trade["id"], recipient.id, [target], trade.get("offered_cards", []))
            elif decision.get("decision") == "refuse":
                self.cancel_trade(trade["id"], recipient.id)
        for creator in sorted(self.characters.values(), key=lambda item: item.id):
            offer = self.choose_ai_trade_offer(creator.id)
            if not offer: continue
            target_id, offered_cards, requested_cards = offer
            self.create_trade(creator.id, target_id, offered_cards, requested_cards)
            break
    def create_team_trade(self, team_id, giver_id, receiver_id, offered_cards, requested_cards=None, requested_family="", requested_kind=""):
        team = self.teams.get(team_id)
        if not team or team.formation_state != "complete" or giver_id not in team.members or receiver_id not in team.members or giver_id == receiver_id: return None
        trade = self.create_trade(giver_id, receiver_id, offered_cards, requested_cards, requested_family, requested_kind)
        if trade:
            trade["team_id"] = team_id
            trade["intent"] = "in_team_trade"
            trade["relationship"] = "team"
            trade.setdefault("history", []).append({"actor": giver_id, "action": "team_trade_opened", "team_id": team_id, "status": trade.get("state", "open"), "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()})
            self.record_history("team", team_id, "trade_opened", {"trade_id": trade.get("id", ""), "giver": giver_id, "receiver": receiver_id, "offered": list(offered_cards or []), "requested": list(requested_cards or [])})
            self.save()
        return trade

    def create_team_borrow_request(self, team_id, borrower_id, lender_id, card_id, duels=1):
        team = self.teams.get(team_id)
        if not team or team.formation_state != "complete" or borrower_id not in team.members or lender_id not in team.members or borrower_id == lender_id: return None
        record = self.create_borrow_request(lender_id, borrower_id, card_id, duels, self.characters[borrower_id].deck_id if borrower_id in self.characters else "")
        if record:
            record["team_id"] = team_id
            record["intent"] = "in_team_borrow"
            record.setdefault("history", []).append({"actor": borrower_id, "action": "team_borrow_opened", "team_id": team_id, "status": record.get("state", "requested"), "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()})
            self.record_history("team", team_id, "borrow_requested", {"borrow_id": record.get("id", ""), "borrower": borrower_id, "lender": lender_id, "card": card_id})
            self.save()
        return record

    def _borrow_reserved_count(self, lender_id, card_id, exclude_id=""):
        return sum(1 for record in self.world.setdefault("borrows", []) if record.get("id") != exclude_id and record.get("state") in ["requested", "deferred", "active"] and record.get("lender") == lender_id and record.get("card_id") == card_id)

    def create_borrow_request(self, lender_id, borrower_id, card_id, duels=1, deck_id=""):
        lender = self.characters.get(lender_id)
        borrower = self.characters.get(borrower_id)
        if not lender or not borrower or lender_id == borrower_id or card_id not in self.cards: return None
        if self.relationship_for(borrower_id, lender_id) != "ally" and not self.shared_team(lender_id, borrower_id): return None
        if self.owned_counts(lender_id).get(card_id, 0) - self._borrow_reserved_count(lender_id, card_id) < 1: return None
        if deck_id and deck_id != borrower.deck_id: return None
        deck = self.decks.get(borrower.deck_id, {}) if borrower.deck_id else {}
        if DeckRules.all_cards(deck).count(card_id) >= DeckRules.copies: return None
        sequence = int(self.world.get("borrow_sequence", 0)) + 1
        self.world["borrow_sequence"] = sequence
        request_id = "borrow_" + str(int(time.time() * 1000)) + "_" + str(sequence)
        now = float(self.world.get("simulation_time", 0.0))
        state = "requested" if self.social_available(lender_id) and self.social_available(borrower_id) else "deferred"
        record = {"id": request_id, "lender": lender_id, "borrower": borrower_id, "requester": borrower_id, "target": lender_id, "card_id": card_id, "deck_id": borrower.deck_id, "remaining_duels": max(1, min(5, int(duels))), "intent": "card_borrow", "state": state, "created": time.time(), "created_sim_time": now, "expires_sim_time": now + 10800, "approvals": {borrower_id: True, lender_id: False}, "history": [{"actor": borrower_id, "action": "opened", "status": state, "sim_time": now, "time": time.time()}], "events": [{"actor": borrower_id, "action": "opened", "status": state, "sim_time": now}]}
        self.world.setdefault("borrows", []).append(record)
        self.register_interaction("borrow", record)
        self.record_history("character", borrower_id, "borrow_requested", {"borrow_id": request_id, "lender": lender_id, "card": card_id, "state": state})
        self.save()
        return record

    def _activate_borrow(self, record, actor_id):
        lender_id, borrower_id, card_id = record.get("lender", ""), record.get("borrower", ""), record.get("card_id", "")
        if self.owned_counts(lender_id).get(card_id, 0) - self._borrow_reserved_count(lender_id, card_id, record.get("id", "")) < 1: return False
        borrower = self.characters.get(borrower_id)
        deck = self.decks.get(borrower.deck_id, {}) if borrower and borrower.deck_id else {}
        if not borrower or DeckRules.all_cards(deck).count(card_id) >= DeckRules.copies: return False
        record["state"] = "active"
        record["activated_sim_time"] = float(self.world.get("simulation_time", 0.0))
        record.setdefault("history", []).append({"actor": actor_id, "action": "accepted", "status": "active", "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()})
        record.setdefault("events", []).append({"actor": actor_id, "action": "accepted", "status": "active", "sim_time": float(self.world.get("simulation_time", 0.0))})
        borrower.borrowed_cards.append(card_id)
        self.transition_interaction("borrow", record, "active", actor_id, "accepted", {"deck_id": borrower.deck_id, "card_id": card_id})
        self.record_history("character", borrower_id, "borrow_started", {"borrow_id": record.get("id", ""), "card": card_id, "from": lender_id, "duels": record.get("remaining_duels", 1)})
        self.record_history("character", lender_id, "borrow_accepted", {"borrow_id": record.get("id", ""), "card": card_id, "to": borrower_id})
        self.save()
        return True

    def respond_borrow_request(self, request_id, actor_id, decision):
        record = next((item for item in self.world.setdefault("borrows", []) if item.get("id") == request_id), None)
        decision = str(decision or "").lower()
        if not record or record.get("state") not in ["requested", "deferred"] or actor_id not in [record.get("lender"), record.get("borrower")]: return False
        now = float(self.world.get("simulation_time", 0.0))
        if decision in ["deny", "cancel", "ignore"]:
            if decision == "cancel" and actor_id != record.get("borrower"): return False
            state = "canceled" if decision == "cancel" else "denied"
            record["state"] = state
            self.transition_interaction("borrow", record, state, actor_id, decision)
            record.setdefault("history", []).append({"actor": actor_id, "action": decision, "status": state, "sim_time": now, "time": time.time()})
            self.record_history("character", record.get("borrower", ""), "borrow_" + state, {"borrow_id": request_id, "lender": record.get("lender", ""), "card": record.get("card_id", "")})
            self.save()
            return True
        if decision != "accept" or actor_id != record.get("lender") or not self.social_available(actor_id) or not self.social_available(record.get("borrower", "")): return False
        return self._activate_borrow(record, actor_id)

    def borrow_card(self, lender_id, borrower_id, card_id, duels=1):
        return self.create_borrow_request(lender_id, borrower_id, card_id, duels)

    def _ai_borrow_tick(self):
        now = float(self.world.get("simulation_time", 0.0))
        if now < float(self.world.get("last_ai_borrow_time", 0.0)) + 20.0: return
        self.world["last_ai_borrow_time"] = now
        for record in list(self.world.setdefault("borrows", [])):
            if record.get("state") != "requested": continue
            lender = self.characters.get(record.get("lender", ""))
            borrower = self.characters.get(record.get("borrower", ""))
            if not lender or lender.origin == "user" or not borrower or not self.social_available(lender.id): continue
            relation = self.relationship_for(lender.id, borrower.id)
            utility = float(lender.behavior_weights.get("ally_bias", 4.0)) if relation == "ally" else 1.0 if self.shared_team(lender.id, borrower.id) else -4.0
            utility += float(lender.behavior_weights.get("resource", 5.0)) * 0.2
            utility -= self._card_trade_value(lender.id, record.get("card_id", "")) * 0.18
            if utility >= 0.0: self.respond_borrow_request(record.get("id", ""), lender.id, "accept")
            else: self.respond_borrow_request(record.get("id", ""), lender.id, "deny")
        for borrower in sorted(self.characters.values(), key=lambda item: item.id):
            if borrower.origin == "user" or not self.social_available(borrower.id): continue
            if any(record.get("borrower") == borrower.id and record.get("state") in ["requested", "deferred", "active"] for record in self.world.setdefault("borrows", [])): continue
            deck = self.decks.get(borrower.deck_id, {}) if borrower.deck_id else {}
            deck_cards = DeckRules.all_cards(deck)
            desired = [card for card in self.cards.values() if card.id not in deck_cards and card.family in borrower.preferred_families and card.kind != "fusion"]
            desired.sort(key=lambda card: (self._card_trade_value(borrower.id, card.id), card.id), reverse=True)
            preferred = desired[0] if desired else None
            if not preferred: continue
            lenders = [candidate for candidate in self.characters.values() if candidate.id != borrower.id and self.social_available(candidate.id) and (self.relationship_for(borrower.id, candidate.id) == "ally" or self.shared_team(borrower.id, candidate.id)) and self.available_card_counts(candidate.id).get(preferred.id, 0) > 0]
            lenders.sort(key=lambda candidate: (-self._relationship_score(borrower, candidate), self._card_trade_value(candidate.id, preferred.id), candidate.id))
            if lenders:
                self.create_borrow_request(lenders[0].id, borrower.id, preferred.id, 1, borrower.deck_id)
                break

    def _advance_borrow_requests(self):
        now = float(self.world.get("simulation_time", 0.0))
        for record in self.world.setdefault("borrows", []):
            if record.get("state") in ["requested", "deferred"] and now >= float(record.get("expires_sim_time", 0.0) or 0.0):
                record["state"] = "expired"
                self.transition_interaction("borrow", record, "expired", "world", "expired")
            elif record.get("state") == "deferred" and self.social_available(record.get("lender", "")) and self.social_available(record.get("borrower", "")):
                record["state"] = "requested"
                self.transition_interaction("borrow", record, "requested", "world", "resumed")

    def advance_borrows(self, character_id):
        changed = False
        for record in self.world.setdefault("borrows", []):
            if record.get("state") == "active" and record.get("borrower") == character_id:
                record["remaining_duels"] = int(record.get("remaining_duels", 1)) - 1
                changed = True
                if record["remaining_duels"] <= 0:
                    self.transition_interaction("borrow", record, "returned", character_id, "returned")
                    record["state"] = "returned"
                    borrower = self.characters.get(character_id)
                    if borrower and record.get("card_id") in borrower.borrowed_cards: borrower.borrowed_cards.remove(record.get("card_id"))
                    self.record_history("character", character_id, "borrow_returned", {"borrow_id": record.get("id", ""), "card": record.get("card_id", ""), "to": record.get("lender", "")})
                    self.record_history("character", record.get("lender", ""), "borrow_card_returned", {"borrow_id": record.get("id", ""), "card": record.get("card_id", ""), "from": character_id})
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

    def record_duel(self, winner_id, loser_id, turns, reason, reward_policy=None, metadata=None):
        winner = self.characters.get(winner_id) if winner_id else None
        loser = self.characters.get(loser_id) if loser_id else None
        metadata = dict(metadata or {})
        transferred = ""
        transferred_cards = []
        participants = [item for item in [winner, loser] if item]
        for character in participants:
            character.experience["duels"] = int(character.experience.get("duels", 0)) + 1
            result = "draw" if not winner else "win" if character is winner else "loss"
            character.experience[result + "s"] = int(character.experience.get(result + "s", 0)) + 1
            character.history.append({"opponent": loser.id if character is winner and loser else winner.id if character is loser and winner else "", "result": result, "turns": turns, "reason": reason, "mode": metadata.get("mode", "current"), "place": metadata.get("place", ""), "finisher": metadata.get("finisher", reason), "deck_id": metadata.get("deck_ids", {}).get(character.id, "") if isinstance(metadata.get("deck_ids", {}), dict) else "", "cards": list(metadata.get("transferred_cards", [])), "time": time.time()})
            character.history = character.history[-20:]
            character.learning_state["updates"] = int(character.learning_state.get("updates", 0)) + 1
            character.learning_state["last_update"] = time.time()
        if winner and loser:
            if reward_policy is None:
                reward_policy = {"mode": "random", "source": "library", "count": 1}
            transferred_cards = self.transfer_duel_reward(winner.id, loser.id, reward_policy, int(self.world.get("duel_sequence", 0)) + 1)
            transferred = transferred_cards[0] if transferred_cards else ""
            self.world["duel_sequence"] = int(self.world.get("duel_sequence", 0)) + 1
            difficulty = self.save_data.get("difficulty", "normal")
            learning_delta = {"normal": 1, "hard": 2, "extreme": 3}.get(difficulty, 1)
            for character, other in [(winner, loser), (loser, winner)]:
                character.learned_opponents[other.id] = character.learned_opponents.get(other.id, 0) + learning_delta
                opponent_memory = character.knowledge_state.setdefault("opponents", {}).setdefault(other.id, {"cards": {}, "effects": {}, "sightings": 0})
                observed_cards = list(opponent_memory.get("cards", {}).keys())
                for card_id in observed_cards: character.learned_cards[card_id] = character.learned_cards.get(card_id, 0) + learning_delta
                character.experience.setdefault("techniques", {})[other.id] = {"observed_cards": observed_cards[:20], "last_result": "win" if character is winner else "loss", "turns": turns, "updated": time.time()}
                character.behavior_weights["adaptation"] = min(10.0, float(character.behavior_weights.get("adaptation", 1.0)) + learning_delta * (0.25 if character is winner else 0.5))
            loser.smartness = clamp(loser.smartness + 1, 1, 10)
            self.advance_borrows(winner.id)
            self.advance_borrows(loser.id)
            self.calculate_rank(winner.id)
            self.calculate_rank(loser.id)
            if loser.stars >= winner.stars + 2: self.add_achievement(winner.id, "Historic upset", f"Defeated {loser.name} despite the star gap.")
        metadata["transferred_cards"] = list(transferred_cards)
        outcome = {"winner": winner.id if winner else "", "loser": loser.id if loser else "", "result": "draw" if not winner else "win", "turns": turns, "reason": reason, "mode": metadata.get("mode", "current"), "place": metadata.get("place", ""), "finisher": metadata.get("finisher", reason), "deck_ids": dict(metadata.get("deck_ids", {})), "transferred_cards": list(transferred_cards), "sim_time": float(self.world.get("simulation_time", 0.0))}
        self.world.setdefault("histories", []).append({"scope": "duel", "entity_id": winner.id if winner else loser.id if loser else "world", "event": "duel_completed", "payload": outcome, "sim_time": outcome["sim_time"], "time": time.time()})
        self.world["histories"] = self.world["histories"][-1000:]
        for character in participants: self.record_history("character", character.id, "duel_completed", outcome)
        involved_teams = [team for team in self.teams.values() if any(member.id in team.members for member in participants)]
        for team in involved_teams: self.record_history("team", team.id, "duel_completed", {**outcome, "members": list(team.members)})
        if outcome["place"] in self.places: self.record_history("place", outcome["place"], "duel_completed", {**outcome, "participants": [item.id for item in participants]})
        for card_id in transferred_cards:
            if winner: self.discover_card(winner.id, card_id, "traded", loser.id if loser else "", {"duel": True, "mode": metadata.get("mode", "current")})
            if loser: self.discover_card(loser.id, card_id, "traded", winner.id if winner else "", {"duel": True, "mode": metadata.get("mode", "current")})
        for team in involved_teams:
            distribution = dict(getattr(team, "distribution", {}) or {})
            if distribution.get("enabled"):
                trigger = "team_win" if winner and winner.id in team.members else "duel_completed"
                self.distribute_trio_cards(team, trigger, {"winner": winner.id if winner else "", "loser": loser.id if loser else "", "reason": reason})
        self.save()
        return transferred

    def validate_card_registry(self):
        errors = []
        legendary_rules = dict((self.rules or {}).get("legendary") or {})
        required_stars = int(legendary_rules.get("required_stars", 11) or 11)
        copy_limit = int(legendary_rules.get("copy_limit", 1) or 1)
        minimum_effects = int(legendary_rules.get("minimum_effects", 1) or 1)
        maximum_effects = int(legendary_rules.get("maximum_effects", 5) or 5)
        legendary_types = {}
        for card in self.cards.values():
            is_legendary = card.kind == "legendary" or bool(getattr(card, "legendary", False))
            legendary_type = str(getattr(card, "legendary_type", "") or "")
            if is_legendary:
                if card.kind != "legendary": errors.append(f"{card.id}: Legendary flag requires legendary kind")
                if not card.legendary: errors.append(f"{card.id}: Legendary kind requires legendary flag")
                if int(card.stars) != required_stars: errors.append(f"{card.id}: Legendary cards require {required_stars} stars")
                if int(card.limit) != copy_limit: errors.append(f"{card.id}: Legendary cards require copy limit {copy_limit}")
                if not legendary_type: errors.append(f"{card.id}: Legendary cards require legendary_type")
                if legendary_type in legendary_types: errors.append(f"{card.id}: legendary_type {legendary_type} duplicates {legendary_types[legendary_type]}")
                else: legendary_types[legendary_type] = card.id
                procedure = dict(getattr(card, "summon_procedure", {}) or {})
                if bool(legendary_rules.get("requires_special_procedure", True)) and (procedure.get("kind") != "legendary" or not procedure.get("enabler")): errors.append(f"{card.id}: Legendary cards require an authored special procedure and enabler")
                if not minimum_effects <= len(card.effects) <= maximum_effects: errors.append(f"{card.id}: Legendary cards require {minimum_effects}-{maximum_effects} effects")
            elif legendary_type: errors.append(f"{card.id}: legendary_type is reserved for Legendary cards")
        return list(dict.fromkeys(errors))

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

    def validate_card_definition(self, kind, stars, atk, defense, family, description, targets=None, target_count=0, timing="main", materials=None, ritual_cost=0, summon_method="normal", effects=None, summon_procedure=None, legendary_type=""):
        errors = []
        monster_kinds = {"normal", "effect", "fusion", "ritual", "legendary"}
        if not str(family or "").strip(): errors.append("family is required")
        if not str(description or "").strip(): errors.append("description is required")
        if kind in monster_kinds and int(stars) < 1: errors.append("monster cards require at least one star")
        if kind not in monster_kinds and (int(stars) != 0 or int(atk) != 0 or int(defense) != 0): errors.append("non-monster cards cannot carry monster stats")
        if kind == "fusion" and (summon_method != "fusion" or not materials or not summon_procedure or summon_procedure.get("kind") != "fusion" or not summon_procedure.get("enabler")): errors.append("fusion cards require a canonical Fusion procedure, materials, and authored enabler")
        if kind == "ritual" and (summon_method != "ritual" or int(ritual_cost) < 1 or not summon_procedure or summon_procedure.get("kind") != "ritual" or not summon_procedure.get("enabler")): errors.append("ritual cards require a canonical Ritual procedure, exact Level cost, and authored enabler")
        if kind == "legendary" and (int(stars) != 11 or summon_method != "legendary" or not summon_procedure or summon_procedure.get("kind") != "legendary" or not summon_procedure.get("enabler")): errors.append("Legendary cards require 11 stars, a canonical Legendary procedure, and authored enabler")
        if kind == "legendary" and not str(legendary_type or "").strip(): errors.append("Legendary cards require a legendary_type")
        if kind == "legendary" and not 1 <= len(effects or []) <= 5: errors.append("Legendary cards require one to five effects")
        if kind not in ["fusion", "ritual", "legendary"] and summon_method not in ["normal", ""]: errors.append("only Fusion, Ritual, and Legendary cards may use special summon modes")
        if int(target_count) > 0 and (not targets or targets == ["none"]): errors.append("target count requires a target type")
        if timing not in ["main", "opponent_attack", "any"]: errors.append("unsupported timing")
        errors.extend(self.validate_effects(effects or []))
        return list(dict.fromkeys(errors))

    def create_card(self, name, kind, stars, atk, defense, family, description, logic_graph="", targets=None, target_count=0, timing="main", field_effect=None, materials=None, ritual_cost=0, summon_method="normal", art_path="", effects=None, summon_procedure=None, legendary_type="", non_removable=False):
        card_id = "card_" + str(int(time.time() * 1000))
        frame = "yellow" if kind == "normal" else "orange" if kind == "effect" else "sky" if kind in ["spell", "field"] else "pink" if kind == "trap" else "violet" if kind == "fusion" else "blue" if kind == "ritual" else "red"
        resolved_method = summon_method if summon_method != "normal" else kind if kind in ["fusion", "ritual"] else "legendary" if kind == "legendary" else "normal"
        procedure = dict(summon_procedure or {})
        if not procedure and kind == "fusion": procedure = {"kind": "fusion", "required_card_ids": list(materials or []), "material_selector": {"side": "self", "zone": ["hand", "monster"]}, "locations": ["hand", "monster"], "exact": True, "material_destination": "graveyard", "source_selector": {"zone": "extra", "card_kind": "fusion"}, "source_method": "fusion", "enabler": {"card_kinds": ["spell", "effect"]}}
        if not procedure and kind == "ritual": procedure = {"kind": "ritual", "min_stars": int(ritual_cost), "material_selector": {"side": "self", "zone": ["hand", "monster"]}, "locations": ["hand", "monster"], "exact": False, "material_destination": "graveyard", "source_selector": {"zone": "hand", "card_kind": "ritual"}, "source_method": "ritual", "enabler": {"card_kinds": ["spell", "effect"]}}
        if not procedure and kind == "legendary": procedure = {"kind": "legendary", "source_zones": ["hand", "graveyard"], "source_selector": {"zone": ["hand", "graveyard"], "card_kind": "legendary"}, "source_method": "legendary_special", "special": True, "enabler": {"card_kinds": ["spell", "effect"]}}
        card = CardDef(card_id, name or "Unnamed Card", kind, frame, stars, atk, defense, family or "other", description or "A community-created card.", list(effects or []), (90, 120, 200), kind == "legendary", 1 if kind == "legendary" else 3, logic_graph, list(targets or ["none"]), int(target_count), timing, dict(field_effect or {}), list(materials or []), int(ritual_cost), resolved_method, summon_procedure=procedure, legendary_type=str(legendary_type or (family if kind == "legendary" else "")), non_removable=bool(non_removable))
        card.media_folder = self.scaffold_entity("cards", card_id, name or "Unnamed Card")
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

    def championship_team_count(self, level):
        level = clamp(int(level), 1, 5)
        return 128 if level == 5 else 2 ** (level + 1)

    def championship_library_count(self, entity_id):
        if entity_id in self.characters: return len(self.characters[entity_id].library_cards)
        team = self.teams.get(entity_id)
        return sum(len(self.characters[member].library_cards) for member in team.members if member in self.characters) if team else 0

    def championship_decks(self, entity_id):
        owner_ids = [entity_id]
        if entity_id in self.teams: owner_ids = list(self.teams[entity_id].members)
        return [deck for deck in self.decks.values() if deck.get("owner_id") in owner_ids and len(deck.get("main_cards", [])) >= DeckRules.minimum]

    def championship_host_eligible(self, host_id, level):
        level = clamp(int(level), 1, 5)
        rank = self.calculate_rank(host_id) if host_id in self.characters or host_id in self.teams else 0
        decks = self.championship_decks(host_id)
        library_minimum = 100 * level
        return bool(rank >= level and len(decks) >= 5 and self.championship_library_count(host_id) >= library_minimum)

    def championship_team_eligible(self, team_id, level):
        team = self.teams.get(team_id)
        if not team or team.formation_state != "complete" or len(team.members) != 3 or int(team.rank) < int(level): return False
        return all(member in self.characters and self.characters[member].world_status == "in_playground" for member in team.members)

    def championship_by_id(self, championship_id):
        return next((item for item in self.world.setdefault("championships", []) if item.get("id") == championship_id), None)

    def host_championship(self, level, host_id=""):
        level = clamp(int(level), 1, 5)
        if not host_id:
            candidates = [team.id for team in self.teams.values() if self.championship_host_eligible(team.id, level)] + [character.id for character in self.characters.values() if character.origin != "user" and self.championship_host_eligible(character.id, level)]
            host_id = max(candidates, key=lambda item: (self.calculate_rank(item), item)) if candidates else ""
        if not host_id or not self.championship_host_eligible(host_id, level): return None
        return self.create_championship(level, [], host_id)

    def create_championship(self, level, team_ids=None, host_id=""):
        level = clamp(int(level), 1, 5)
        host_id = host_id or self.role_config()["player_character"]
        if not self.championship_host_eligible(host_id, level): return None
        required = self.championship_team_count(level)
        candidate_ids = [team_id for team_id in list(team_ids or []) if self.championship_team_eligible(team_id, level)]
        candidate_ids = list(dict.fromkeys(candidate_ids))[:required]
        now = float(self.world.get("simulation_time", 0.0))
        championship = {"id": "championship_" + str(int(time.time() * 1000)), "level": level, "difficulty": ["easy", "medium", "hard", "extreme", "legendary"][level - 1], "required_teams": required, "host": host_id, "host_kind": "team" if host_id in self.teams else "character", "teams": [], "enrolled": [], "invitations": {}, "waitlist": [], "rounds": [], "current_round": -1, "state": "waiting", "mode": "current", "created": time.time(), "created_sim_time": now, "next_schedule_sim_time": now + 5.0, "history": [], "active_battle_ids": [], "rewards": [], "narrator_intro": {}, "narrator_waiting": {}, "narrator_events": []}
        intro = self.narrator_cue("championship_intro", host_id, "", {"championship_id": championship["id"], "level": level, "difficulty": championship["difficulty"], "required_teams": required})
        waiting = self.narrator_cue("championship_waiting", host_id, "", {"championship_id": championship["id"], "level": level, "required_teams": required})
        championship["narrator_intro"] = intro
        championship["narrator_waiting"] = waiting
        championship["narrator_events"].append(waiting)
        self.world.setdefault("championships", []).append(championship)
        self.record_history("character" if host_id in self.characters else "team", host_id, "championship_opened", {"championship_id": championship["id"], "level": level, "difficulty": championship["difficulty"], "required_teams": required, "narrator": intro})
        for team_id in candidate_ids: self.invite_championship(championship["id"], team_id)
        self.save()
        return championship

    def invite_championship(self, championship_id, team_id):
        championship = self.championship_by_id(championship_id)
        if not championship or championship.get("state") != "waiting" or not self.championship_team_eligible(team_id, championship.get("level", 1)): return False
        if team_id in championship.get("enrolled", []): return True
        championship.setdefault("invitations", {})[team_id] = {"state": "invited", "sim_time": float(self.world.get("simulation_time", 0.0))}
        enrollment = self.narrator_cue("championship_enrollment", championship.get("host", ""), team_id, {"championship_id": championship_id, "level": championship.get("level", 1), "team": team_id, "state": "invited"})
        championship.setdefault("narrator_events", []).append(enrollment)
        championship.setdefault("history", []).append({"event": "team_invited", "team": team_id, "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time(), "narrator": enrollment})
        self.record_history("team", team_id, "championship_invited", {"championship_id": championship_id, "level": championship.get("level", 1)})
        return True

    def _start_championship(self, championship):
        enrolled = list(dict.fromkeys(championship.get("enrolled", [])))
        if len(enrolled) != int(championship.get("required_teams", 0)): return False
        rounds = []
        current = enrolled
        while len(current) > 1:
            pairs = [[current[index], current[index + 1]] for index in range(0, len(current), 2)]
            rounds.append({"pairs": pairs, "results": [], "scheduled": []})
            current = [pair[0] for pair in pairs]
        championship["teams"] = enrolled
        championship["rounds"] = rounds
        championship["current_round"] = 0
        championship["state"] = "active"
        championship["next_schedule_sim_time"] = float(self.world.get("simulation_time", 0.0))
        championship.setdefault("history", []).append({"event": "enrollment_complete", "teams": enrolled, "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time()})
        return True

    def join_championship(self, championship_id, team_id):
        championship = self.championship_by_id(championship_id)
        if not championship or championship.get("state") != "waiting" or not self.championship_team_eligible(team_id, championship.get("level", 1)): return False
        if team_id in championship.get("enrolled", []): return True
        if len(championship.setdefault("enrolled", [])) >= int(championship.get("required_teams", 0)):
            championship.setdefault("waitlist", []).append(team_id)
            return False
        invitation = championship.setdefault("invitations", {}).setdefault(team_id, {"state": "invited", "sim_time": float(self.world.get("simulation_time", 0.0))})
        invitation["state"] = "accepted"
        championship["enrolled"].append(team_id)
        enrollment = self.narrator_cue("championship_enrollment", championship.get("host", ""), team_id, {"championship_id": championship_id, "level": championship.get("level", 1), "team": team_id, "state": "accepted", "position": len(championship["enrolled"])})
        championship.setdefault("narrator_events", []).append(enrollment)
        championship.setdefault("history", []).append({"event": "team_joined", "team": team_id, "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time(), "narrator": enrollment})
        self.record_history("team", team_id, "championship_joined", {"championship_id": championship_id, "level": championship.get("level", 1), "position": len(championship["enrolled"])})
        if len(championship["enrolled"]) == int(championship.get("required_teams", 0)): self._start_championship(championship)
        self.save()
        return True

    def watch_championship(self, championship_id, character_id):
        championship = self.championship_by_id(championship_id)
        if not championship or character_id not in self.characters: return False
        championship.setdefault("watchers", [])
        if character_id not in championship["watchers"]: championship["watchers"].append(character_id)
        self.record_history("character", character_id, "championship_watched", {"championship_id": championship_id})
        self.save()
        return True

    def _schedule_championship_matches(self, championship):
        if championship.get("state") != "active": return
        round_index = int(championship.get("current_round", -1))
        if round_index not in range(len(championship.get("rounds", []))): return
        round_data = championship["rounds"][round_index]
        scheduled_pairs = {int(item.get("pair_index", -1)) for item in round_data.get("scheduled", [])}
        resolved_pairs = {int(item.get("pair_index", -1)) for item in round_data.get("results", [])}
        for pair_index, pair in enumerate(round_data.get("pairs", [])):
            if pair_index in scheduled_pairs or pair_index in resolved_pairs or len(pair) != 2: continue
            place = next((item for item in self.places.values() if item.current_duels < item.capacity), None)
            if not place: break
            if not self.reserve_place(place.id): continue
            for team_id in pair:
                team = self.teams.get(team_id)
                if team:
                    for member_id in team.members:
                        character = self.characters.get(member_id)
                        if character: character.availability, character.activity = "active", "dueling"
            battle_id = "champ_battle_" + str(int(time.time() * 1000)) + "_" + str(round_index) + "_" + str(pair_index) + "_" + str(len(championship.get("active_battle_ids", [])))
            battle = {"id": battle_id, "engine_type": "team", "championship_id": championship["id"], "championship_round": round_index, "championship_pair": pair_index, "player_team": pair[0], "opponent_team": pair[1], "place": place.id, "starter": "opponent", "status": "active", "phase": "pre_duel", "elapsed": 0.0, "next_action": 3.0, "round": 1, "rounds": [], "watchers": list(championship.get("watchers", [])), "started_sim_time": float(self.world.get("simulation_time", 0.0))}
            self.world.setdefault("active_battles", []).append(battle)
            round_data.setdefault("scheduled", []).append({"pair_index": pair_index, "battle_id": battle_id, "place": place.id, "sim_time": float(self.world.get("simulation_time", 0.0))})
            championship.setdefault("active_battle_ids", []).append(battle_id)
            match_cue = self.narrator_cue("championship_match_start", championship.get("host", ""), pair[0], {"championship_id": championship["id"], "round": round_index, "pair": pair_index, "teams": pair, "place": place.id})
            championship.setdefault("narrator_events", []).append(match_cue)
            championship.setdefault("history", []).append({"event": "match_scheduled", "round": round_index, "pair": pair_index, "battle": battle_id, "place": place.id, "sim_time": float(self.world.get("simulation_time", 0.0)), "time": time.time(), "narrator": match_cue})

    def _advance_championships(self):
        now = float(self.world.get("simulation_time", 0.0))
        for championship in self.world.setdefault("championships", []):
            if championship.get("state") == "waiting":
                for team in sorted(self.teams.values(), key=lambda item: item.id):
                    if len(championship.get("enrolled", [])) >= int(championship.get("required_teams", 0)): break
                    if team.id in championship.get("enrolled", []) or team.id in championship.get("invitations", {}) or not self.championship_team_eligible(team.id, championship.get("level", 1)): continue
                    self.invite_championship(championship["id"], team.id)
                for team_id, invitation in list(championship.get("invitations", {}).items()):
                    team = self.teams.get(team_id)
                    if team and team_id not in championship.get("enrolled", []) and all(self.social_available(member_id) for member_id in team.members) and any(self.characters[member_id].origin != "user" for member_id in team.members): self.join_championship(championship["id"], team_id)
                if len(championship.get("enrolled", [])) == int(championship.get("required_teams", 0)): self._start_championship(championship)
            elif championship.get("state") == "active" and now >= float(championship.get("next_schedule_sim_time", 0.0)):
                self._schedule_championship_matches(championship)
                championship["next_schedule_sim_time"] = now + 5.0

    def resolve_championship_match(self, championship_id, round_index, pair_index, winner_id):
        championship = self.championship_by_id(championship_id)
        if not championship or round_index not in range(len(championship.get("rounds", []))): return False
        round_data = championship["rounds"][round_index]
        if pair_index not in range(len(round_data.get("pairs", []))) or winner_id not in round_data["pairs"][pair_index]: return False
        if any(int(item.get("pair_index", -1)) == int(pair_index) for item in round_data.get("results", [])): return False
        pair = list(round_data["pairs"][pair_index])
        loser_id = pair[1] if winner_id == pair[0] else pair[0]
        result = {"pair": pair, "pair_index": pair_index, "winner": winner_id, "loser": loser_id, "round": round_index, "time": time.time(), "sim_time": float(self.world.get("simulation_time", 0.0))}
        round_data.setdefault("results", []).append(result)
        progress_cue = self.narrator_cue("championship_round_progress", championship.get("host", ""), winner_id, {"championship_id": championship_id, "round": round_index, "pair": pair_index, "winner": winner_id, "loser": loser_id})
        championship.setdefault("narrator_events", []).append(progress_cue)
        championship.setdefault("history", []).append({"event": "match_resolved", **result, "narrator": progress_cue})
        winner_team = self.teams.get(winner_id)
        loser_team = self.teams.get(loser_id)
        reward_amount = int(round_index)
        if winner_team and loser_team and reward_amount > 0:
            winner_member = winner_team.leader if winner_team.leader in winner_team.members else winner_team.members[0]
            for member_id in loser_team.members:
                candidates = list(self.characters.get(member_id).library_cards) if member_id in self.characters else []
                for card_id in candidates[:reward_amount]:
                    if card_id in self.characters[member_id].library_cards:
                        self.characters[member_id].library_cards.remove(card_id)
                        self.characters[winner_member].library_cards.append(card_id)
                        championship.setdefault("rewards", []).append({"from": member_id, "to": winner_member, "card": card_id, "round": round_index})
                        championship.setdefault("narrator_events", []).append(self.narrator_cue("championship_reward", championship.get("host", ""), winner_id, {"championship_id": championship_id, "round": round_index, "winner": winner_id, "card": card_id}))
            host_owner = championship.get("host", "")
            source_character = self.characters.get(host_owner) if host_owner in self.characters else self.characters.get(self.teams[host_owner].leader) if host_owner in self.teams else None
            if source_character:
                for card_id in list(source_character.library_cards)[:reward_amount]:
                    if card_id in source_character.library_cards:
                        source_character.library_cards.remove(card_id)
                        self.characters[winner_member].library_cards.append(card_id)
                        championship.setdefault("rewards", []).append({"from": source_character.id, "to": winner_member, "card": card_id, "round": round_index, "host_reward": True})
                        championship.setdefault("narrator_events", []).append(self.narrator_cue("championship_reward", championship.get("host", ""), winner_id, {"championship_id": championship_id, "round": round_index, "winner": winner_id, "card": card_id, "host_reward": True}))
        if len(round_data["results"]) == len(round_data.get("pairs", [])):
            winners = [item["winner"] for item in round_data["results"]]
            next_round = round_index + 1
            if next_round < len(championship.get("rounds", [])):
                championship["rounds"][next_round]["pairs"] = [[winners[index], winners[index + 1]] for index in range(0, len(winners), 2)]
                championship["current_round"] = next_round
                championship["next_schedule_sim_time"] = float(self.world.get("simulation_time", 0.0)) + 5.0
            else:
                championship["state"] = "complete"
                championship["winner"] = winners[0]
                outro = self.narrator_cue("championship_outro", championship.get("host", ""), winners[0], {"championship_id": championship_id, "level": championship.get("level", 0), "difficulty": championship.get("difficulty", ""), "winner": winners[0], "rewards": list(championship.get("rewards", []))})
                championship["narrator_outro"] = outro
                self.record_history("team", winners[0], "championship_won", {"championship_id": championship_id, "level": championship.get("level", 0), "rewards": list(championship.get("rewards", [])), "narrator": outro})
                for team_id in championship.get("teams", []): self.calculate_rank(team_id)
                self.add_achievement(self.teams[winners[0]].leader, "Championship victory", f"Won championship {championship_id}.")
        self.save()
        return True

    def entity_tree(self, category):
        events = ["idle", "about", "pre-duel", "spin-dice", "draw", "standby", "turn-start", "turn-end", "summon", "special-summon", "set", "flip", "flip-reveal", "activate", "effect", "effect-start", "attack", "attacking", "attack-travel", "hit", "damage", "switch-position", "stat-change", "damage-dealt", "damage-received", "direct-damage", "destroy", "destroyed", "die", "death", "return", "return-to-hand", "banish", "banished", "best-card", "near-win", "near-lose", "win", "lose", "draw-result", "instant-win", "instant-lose"]
        trees = {
            "cards": ["logic", "art", "art/variants", "art/metadata"],
            "characters": ["logic", "weights", "pfp", "pfp/variants", "cards", "cards/best-class"],
            "teams": ["logic", "effects", "members", "members/1", "members/2", "members/3", "pfp", "pfp/variants"],
            "places": ["logic", "background/day", "background/night", "field/day", "field/night", "ground/day", "ground/night", "presentation"],
            "decks": ["logic", "pfp", "pfp/variants", "cards", "experience"]
        }
        if category == "cards":
            trees[category].extend(f"interactions/{event}/{part}" for event in events for part in ["animations", "audio", "vfx"])
            trees[category].append("characters")
        if category == "characters":
            trees[category].extend(f"animations/{event}" for event in events)
            trees[category].extend(f"audio/{event}" for event in events)
            trees[category].extend(f"duel/reactions/{relation}/{event}/{part}" for relation in ["stranger", "ally", "enemy", "opponent"] for event in events for part in ["animations", "audio"])
            trees[category].extend(f"duel/interactions/{event}/{part}" for event in events for part in ["animations", "audio"])
            trees[category].extend(f"duel/vfx/{event}" for event in events)
            trees[category].extend(f"duel/effects/{event}" for event in events)
        if category == "teams":
            trees[category].extend(f"animations/{event}" for event in events)
            trees[category].extend(f"audio/{event}" for event in events)
            trees[category].extend(f"members/{member}/animations" for member in ["1", "2", "3"])
            trees[category].extend(f"members/{member}/audio" for member in ["1", "2", "3"])
        if category == "places":
            trees[category].extend(f"presentation/{event}/{part}" for event in ["pre-duel", "spin-dice", "in-duel", "win", "lose", "draw", "landscape"] for part in ["animations", "audio"])
            trees[category].extend(f"music/{period}/{state}" for period in ["day", "night"] for state in ["pre-duel", "in-duel", "near-win", "near-lose", "post-duel-win", "post-duel-lose", "draw", "landscape"])
        return sorted(set(trees.get(category, ["logic"])))

    def write_tree_contract(self, root, folders, root_files=None):
        root = Path(root)
        directories = {Path(".")}
        for folder in folders:
            parts = Path(folder).parts
            directories.update(Path(*parts[:index]) for index in range(1, len(parts) + 1))
        for directory in sorted(directories, key=lambda item: (len(item.parts), str(item))):
            current = root / directory
            current.mkdir(parents=True, exist_ok=True)
            legal = set(root_files or []) if directory == Path(".") else set()
            for child in directories:
                if child.parent == directory and child != directory: legal.add(child.name + "/")
            for child in current.iterdir():
                if child.name == "tree.txt": continue
                if child.is_file() and child.name == "manifest.json" and directory == Path("."): legal.add("manifest.json")
            if directory.parts and directory.parts[-1] in {"logic", "weights", "metadata", "experience"}: legal.update(["*.json"])
            if directory.parts and directory.parts[-1] in {"art", "pfp"}: legal.update(["variants/"])
            if directory.parts and directory.parts[-1] == "variants": legal.update([f"{index}.png" for index in range(1, 11)])
            if directory.parts and directory.parts[-1] in {"animations", "audio", "vfx"}: legal.update([f"{index}/" for index in range(1, 11)] if directory.parts[-1] == "animations" else ["1..10.*"])
            (current / "tree.txt").write_text("\n".join(sorted(legal | {"tree.txt"})) + "\n", encoding="utf-8")

    def scaffold_entity(self, category, entity_id, display_name, folders=None, created=None, folder_name=""):
        folder_name = folder_name or slug(entity_id)
        root = DATA / category / folder_name
        paths = sorted(set(self.entity_tree(category) + list(folders or [])))
        for folder in paths:
            folder_path = root / folder
            folder_path.mkdir(parents=True, exist_ok=True)
            if folder.startswith("animations/") or folder.endswith("/animations"):
                for variant in range(1, 11): (folder_path / str(variant)).mkdir(exist_ok=True)
        manifest = {"schema": 4, "id": entity_id, "name": display_name, "category": category, "created": created or time.time(), "folders": paths, "asset_contract": "gdd_nested_v2"}
        if category == "cards": manifest["frame_contract"] = "engine_owned"; manifest["art_contract"] = "user_owned_optional"
        write_json(root / "manifest.json", manifest)
        self.write_tree_contract(root, paths, ["manifest.json"])
        return str(root.relative_to(DATA))

    def import_entity_image(self, value, media_folder):
        source = Path(str(value or "")).expanduser()
        if not source.exists(): source = DATA / str(value or "")
        if not source.exists() or not source.is_file() or source.suffix.lower() not in MediaRegistry.image_extensions: return ""
        target_root = DATA / media_folder / "pfp" / "variants"
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / ("1" + source.suffix.lower())
        shutil.copy2(source, target)
        return str(target.relative_to(DATA))

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
                    for item in paths:
                        item_path = root / item
                        item_path.mkdir(parents=True, exist_ok=True)
                        if item.startswith("animations/") or item.endswith("/animations"):
                            for variant in range(1, 11): (item_path / str(variant)).mkdir(exist_ok=True)
                    self.write_tree_contract(root, paths, ["manifest.json"])
                    manifest = read_json(root / "manifest.json", {})
                    manifest.update({"schema": 4, "id": entity.id, "name": entity.name, "category": category, "folders": sorted(set(manifest.get("folders", []) + paths)), "asset_contract": "gdd_nested_v2"})
                    if category == "cards": manifest.update({"frame_contract": "engine_owned", "art_contract": "user_owned_optional"})
                    write_json(root / "manifest.json", manifest)
                    self.write_tree_contract(root, paths, ["manifest.json"])
                    if category == "cards" and not getattr(entity, "art_folder", ""):
                        entity.art_folder = entity.media_folder
                        changed = True
        if changed:
            self.save()

    def create_place(self, name, capacity=3, background="", day_night=True):
        place_id = "place_" + str(int(time.time() * 1000))
        display_name = name or "New Place"
        folder = self.scaffold_entity("places", place_id, display_name)
        place = PlaceDef(place_id, display_name, clamp(int(capacity), 1, 10), 0, background.strip(), bool(day_night), folder)
        self.places[place_id] = place
        self.save()
        return place

    def create_team(self, name, members, preferred_place="", portrait="", description="", leader="", preferred_places=None, preferred_families=None, preferred_card_kinds=None, preferred_cards=None, logic_graph=""):
        team_id = "team_" + str(int(time.time() * 1000))
        display_name = str(name or "New Team").strip() or "New Team"
        selected = [member for member in dict.fromkeys(members if isinstance(members, list) else []) if member in self.characters][:3]
        if not selected: return None
        leader = leader if leader in selected else selected[0]
        folder = self.scaffold_entity("teams", team_id, display_name)
        places = list(preferred_places or [])
        if preferred_place: places.insert(0, preferred_place)
        team = TeamDef(team_id, display_name, selected, leader, [item for item in dict.fromkeys(places) if item in self.places][:20], "community", {}, False, 1, [], folder, "", description or "", self.normalize_profile_list(preferred_families, limit=20), self.normalize_profile_list(preferred_card_kinds, {"normal", "effect", "spell", "field", "trap", "fusion", "ritual", "legendary"}, 10), self.normalize_profile_list(preferred_cards, set(self.cards), 20))
        team.logic_graph = str(logic_graph or "")
        self.import_entity_image(portrait, folder)
        self.teams[team_id] = team
        self.normalize_team_profile(team)
        self.save()
        return team

    def update_character(self, character_id, values):
        character = self.characters.get(character_id)
        if not character: return None
        allowed = {"name", "portrait", "description", "stars", "smartness", "relationship", "preferred_families", "preferred_card_kinds", "preferred_subtypes", "preferred_cards", "preferred_places", "deck_id", "gender", "origin", "best_cards", "technique_profile", "cognition", "learning_policy", "state_rules", "mood", "logic_graph"}
        for key, value in values.items():
            if key not in allowed: continue
            if key in ["stars", "smartness"]: value = clamp(int(value), 1, 10)
            if key in ["preferred_families", "preferred_card_kinds", "preferred_subtypes"]: value = value if isinstance(value, list) else [value]
            if key in ["preferred_cards", "best_cards"]: value = [str(item) for item in (value if isinstance(value, list) else [value]) if str(item) in self.cards][:20]
            if key == "preferred_places": value = [str(item) for item in (value if isinstance(value, list) else [value]) if str(item) in self.places][:20]
            if key == "portrait":
                self.import_entity_image(value, character.media_folder)
                value = ""
            setattr(character, key, value)
        self.normalize_character_profile(character)
        self.ensure_behavior_weights()
        self.save()
        return character

    def update_team(self, team_id, values):
        team = self.teams.get(team_id)
        if not team: return None
        if "members" in values:
            members = [member for member in dict.fromkeys(values["members"] if isinstance(values["members"], list) else []) if member in self.characters][:3]
            if members: team.members = members
        for key in ["name", "portrait", "description"]:
            if key in values and values[key] is not None and str(values[key]).strip():
                if key == "portrait":
                    self.import_entity_image(values[key], team.media_folder)
                    setattr(team, key, "")
                else: setattr(team, key, str(values[key]).strip())
        if "leader" in values and values["leader"] in team.members: team.leader = values["leader"]
        if "preferred_places" in values: team.preferred_places = [place for place in dict.fromkeys(values["preferred_places"] if isinstance(values["preferred_places"], list) else []) if place in self.places]
        if "preferred_families" in values: team.preferred_families = values["preferred_families"]
        if "preferred_card_kinds" in values: team.preferred_card_kinds = values["preferred_card_kinds"]
        if "preferred_cards" in values: team.preferred_cards = values["preferred_cards"]
        if "behavior_weights" in values and isinstance(values["behavior_weights"], dict): team.behavior_weights = dict(values["behavior_weights"])
        if "logic_graph" in values: team.logic_graph = str(values["logic_graph"] or "")
        self.normalize_team_profile(team)
        self.save()
        return team

    def update_place(self, place_id, values):
        place = self.places.get(place_id)
        if not place: return None
        if "name" in values and values["name"]: place.name = str(values["name"])
        if "capacity" in values: place.capacity = clamp(int(values["capacity"]), 1, 10)
        if "background" in values and values["background"]: place.background = str(values["background"])
        if "day_night" in values: place.day_night = bool(values["day_night"])
        if "effects" in values and isinstance(values["effects"], list): place.effects = list(values["effects"])
        if "event_response_policies" in values and isinstance(values["event_response_policies"], dict): place.event_response_policies = dict(values["event_response_policies"])
        if "event_window_policies" in values and isinstance(values["event_window_policies"], dict): place.event_window_policies = dict(values["event_window_policies"])
        if "trigger_order_policies" in values and isinstance(values["trigger_order_policies"], dict): place.trigger_order_policies = dict(values["trigger_order_policies"])
        if "logic_graph" in values: place.logic_graph = str(values["logic_graph"] or "")
        self.save()
        return place

    def update_card(self, card_id, values):
        card = self.cards.get(card_id)
        if not card: return None
        allowed = {"name", "kind", "stars", "atk", "defense", "family", "subtypes", "description", "logic_graph", "targets", "target_count", "timing", "field_effect", "materials", "ritual_cost", "summon_method", "summon_procedure", "legendary_type", "non_removable", "effects"}
        merged = {key: getattr(card, key) for key in allowed}
        merged.update({key: value for key, value in values.items() if key in allowed})
        errors = self.validate_card_definition(merged["kind"], int(merged["stars"]), int(merged["atk"]), int(merged["defense"]), merged["family"], merged["description"], merged["targets"], int(merged["target_count"]), merged["timing"], merged["materials"], int(merged["ritual_cost"]), merged["summon_method"], merged["effects"], merged.get("summon_procedure", {}), merged.get("legendary_type", ""))
        if errors: return None
        for key, value in merged.items(): setattr(card, key, value)
        card.subtypes = self.normalize_profile_list(getattr(card, "subtypes", []), limit=2)
        card.frame = "yellow" if card.kind == "normal" else "orange" if card.kind == "effect" else "sky" if card.kind in ["spell", "field"] else "pink" if card.kind == "trap" else "violet" if card.kind == "fusion" else "blue" if card.kind == "ritual" else "red"
        card.legendary = card.kind == "legendary"
        card.limit = 1 if card.legendary else 3
        self.save()
        return card

    def deck_editor_state(self, deck_id):
        deck = self.decks.get(deck_id)
        if not deck: return None
        main = list(deck.get("main_cards", []))
        fusion = list(deck.get("fusion_cards", []))
        errors = DeckRules.validate(main, fusion, self.cards)
        cards = main + fusion
        counts = {}
        for card_id in cards: counts[card_id] = counts.get(card_id, 0) + 1
        return {"id": deck_id, "name": deck.get("name", deck_id), "description": deck.get("description", ""), "portrait": deck.get("portrait", ""), "owner_id": deck.get("owner_id", ""), "main_cards": main, "fusion_cards": fusion, "counts": counts, "errors": errors, "legal": not errors}

    def create_deck(self, name, owner_id="", main_cards=None, fusion_cards=None, description="", portrait="", preferred_families=None, preferred_card_kinds=None, best_cards=None):
        if len(self.decks) >= 10: return None
        deck_id = "deck_" + str(int(time.time() * 1000))
        display_name = str(name or "New Deck").strip() or "New Deck"
        preferred_families = self.normalize_profile_list(preferred_families, limit=20)
        preferred_card_kinds = self.normalize_profile_list(preferred_card_kinds, {"normal", "effect", "spell", "field", "trap", "fusion", "ritual", "legendary"}, 10)
        main_values = list(main_cards or [])
        fusion_values = list(fusion_cards or [])
        if len(main_values) < DeckRules.minimum: main_values = self.starter_deck_cards(preferred_families, preferred_card_kinds, best_cards)
        folder = self.scaffold_entity("decks", deck_id, display_name)
        self.decks[deck_id] = {"schema": 2, "name": display_name, "description": str(description or ""), "portrait": "", "owner_id": owner_id if owner_id in self.characters else "", "main_cards": DeckRules.normalized(main_values, self.cards), "fusion_cards": DeckRules.normalized_fusion(fusion_values, self.cards), "best_cards": [item for item in self.normalize_profile_list(best_cards, set(self.cards), 20)], "preferred_families": preferred_families, "preferred_card_kinds": preferred_card_kinds, "media_folder": folder}
        self.save()
        return deck_id

    def update_deck(self, deck_id, values):
        deck = self.decks.get(deck_id)
        if not deck: return None
        if "name" in values and str(values["name"]).strip(): deck["name"] = str(values["name"]).strip()
        if "description" in values: deck["description"] = str(values["description"] or "")
        if "portrait" in values:
            self.import_entity_image(values.get("portrait", ""), deck.get("media_folder", ""))
            deck["portrait"] = ""
        if "owner_id" in values and values["owner_id"] in self.characters: deck["owner_id"] = values["owner_id"]
        candidate_main = list(values["main_cards"] if isinstance(values.get("main_cards"), list) else deck.get("main_cards", []))
        candidate_fusion = list(values["fusion_cards"] if isinstance(values.get("fusion_cards"), list) else deck.get("fusion_cards", []))
        if "main_cards" in values or "fusion_cards" in values:
            errors = DeckRules.validate(candidate_main, candidate_fusion, self.cards)
            if errors: return None
            deck["main_cards"] = candidate_main
            deck["fusion_cards"] = candidate_fusion
        if "best_cards" in values: deck["best_cards"] = self.normalize_profile_list(values["best_cards"], set(self.cards), 20)
        if "preferred_families" in values: deck["preferred_families"] = self.normalize_profile_list(values["preferred_families"], limit=20)
        if "preferred_card_kinds" in values: deck["preferred_card_kinds"] = self.normalize_profile_list(values["preferred_card_kinds"], {"normal", "effect", "spell", "field", "trap", "fusion", "ritual", "legendary"}, 10)
        self.save()
        return deck

    def duplicate_deck(self, deck_id, name=""):
        source = self.decks.get(deck_id)
        if not source or len(self.decks) >= 10: return None
        return self.create_deck(name or str(source.get("name", deck_id)) + " Copy", source.get("owner_id", ""), list(source.get("main_cards", [])), list(source.get("fusion_cards", [])), source.get("description", ""), source.get("portrait", ""), source.get("preferred_families", []), source.get("preferred_card_kinds", []), source.get("best_cards", []))

    def delete_deck(self, deck_id, force=False):
        if deck_id not in self.decks: return False
        if not force and any(character.deck_id == deck_id for character in self.characters.values()): return False
        self.decks.pop(deck_id, None)
        self.save()
        return True

    def add_library_card(self, character_id, card_id, copies=1):
        character = self.characters.get(character_id)
        if not character or card_id not in self.cards: return False
        for _ in range(max(1, min(9, int(copies)))): character.library_cards.append(card_id)
        self.save()
        return True

    def remove_library_card(self, character_id, card_id, copies=1):
        character = self.characters.get(character_id)
        if not character: return False
        removed = 0
        for _ in range(max(1, int(copies))):
            if card_id not in character.library_cards: break
            character.library_cards.remove(card_id); removed += 1
        if removed: self.save()
        return removed == max(1, int(copies))

    def starter_deck_cards(self, preferred_families=None, preferred_card_kinds=None, preferred_cards=None):
        preferred_families = {str(item).lower() for item in (preferred_families or [])}
        preferred_card_kinds = {str(item).lower() for item in (preferred_card_kinds or [])}
        preferred_cards = [str(item) for item in (preferred_cards or []) if str(item) in self.cards]
        ranked = list(self.cards.values())
        def score(card):
            return (1000 if card.id in preferred_cards else 0) + (100 if str(card.family).lower() in preferred_families else 0) + (50 if str(card.kind).lower() in preferred_card_kinds else 0) + int(card.atk or 0) + int(card.defense or 0)
        ranked.sort(key=lambda card: (-score(card), card.id))
        pool = [card.id for card in ranked if card.kind != "fusion"]
        result = []
        index = 0
        while pool and len(DeckRules.normalized(result, self.cards)) < DeckRules.minimum and index < len(pool) * 4:
            result.append(pool[index % len(pool)])
            index += 1
        normalized = DeckRules.normalized(result, self.cards)
        return normalized if len(normalized) >= DeckRules.minimum else normalized + [item for item in pool if item not in normalized][:max(0, DeckRules.minimum - len(normalized))]

    def create_character(self, name, stars, smartness, family, portrait="", gender="other", origin="community", deck_id="", description="", preferred_card_kinds=None, preferred_subtypes=None, preferred_cards=None, preferred_places=None, technique_profile=None, logic_graph=""):
        char_id = "character_" + str(int(time.time() * 1000))
        display_name = str(name or "New Character").strip() or "New Character"
        families = [str(family or "warrior").lower()]
        if deck_id not in self.decks:
            deck_id = "deck_" + str(int(time.time() * 1000))
            deck_folder = self.scaffold_entity("decks", deck_id, display_name + " Deck")
            self.decks[deck_id] = {"schema": 2, "name": display_name + " Deck", "description": "", "portrait": "", "owner_id": char_id, "main_cards": self.starter_deck_cards(families, preferred_card_kinds, preferred_cards), "fusion_cards": [], "best_cards": list(preferred_cards or [])[:20], "preferred_families": families, "preferred_card_kinds": list(preferred_card_kinds or []), "media_folder": deck_folder}
        folder = self.scaffold_entity("characters", char_id, display_name)
        char = CharacterDef(id=char_id, name=display_name, portrait="", stars=clamp(int(stars), 1, 10), smartness=clamp(int(smartness), 1, 10), relationship="stranger", preferred_families=families, deck_id=deck_id, mood="neutral", allies=[], enemies=[], history=[], library_cards=DeckRules.all_cards(self.decks[deck_id]), gender=gender or "other", origin=origin or "community", best_cards=list(preferred_cards or [])[:20], borrowed_cards=[], rank=1, media_folder=folder, description=description or "", preferred_card_kinds=list(preferred_card_kinds or []), preferred_subtypes=list(preferred_subtypes or []), preferred_cards=list(preferred_cards or [])[:20], preferred_places=list(preferred_places or []), technique_profile=dict(technique_profile or {}))
        char.logic_graph = str(logic_graph or "")
        self.import_entity_image(portrait, folder)
        self.characters[char_id] = char
        self.normalize_character_profile(char)
        self.ensure_behavior_weights()
        self.save()
        return char

    def register_user(self, name, portrait="", gender="other"):
        timestamp = int(time.time() * 1000)
        user_id = "user_" + str(timestamp)
        display_name = str(name or "New User").strip() or "New User"
        deck_id = user_id + "_deck"
        card_ids = self.starter_deck_cards(["warrior"])
        deck_folder = self.scaffold_entity("decks", deck_id, display_name + " Deck", folder_name=deck_id + "_deck")
        self.decks[deck_id] = {"schema": 2, "name": display_name + " Deck", "description": "", "portrait": "", "owner_id": user_id, "main_cards": card_ids, "fusion_cards": [], "best_cards": [], "preferred_families": ["warrior"], "preferred_card_kinds": [], "media_folder": deck_folder}
        character_folder = self.scaffold_entity("characters", user_id, display_name, folder_name=user_id)
        character = CharacterDef(id=user_id, name=display_name, portrait="", stars=5, smartness=5, relationship="stranger", preferred_families=["warrior"], deck_id=deck_id, mood="neutral", allies=[], enemies=[], history=[], library_cards=list(card_ids), gender=gender or "other", origin="user", best_cards=[], borrowed_cards=[], rank=1, media_folder=character_folder)
        self.import_entity_image(portrait, character_folder)
        self.characters[user_id] = character
        self.save_data.update({"active_user_id": user_id, "active_user_folder": character_folder, "setup_complete": True})
        self.world.setdefault("roles", {})["player_character"] = user_id
        self.save()
        return character

    def package_scope(self, kind, entity_id, include_dependencies=True):
        kind = str(kind or "world").lower().rstrip("s")
        categories = {"cards": set(), "characters": set(), "decks": set(), "places": set(), "teams": set(), "logic": set()}
        world = kind == "world"
        if kind == "all":
            for category, registry in [("cards", self.cards), ("characters", self.characters), ("decks", self.decks), ("places", self.places), ("teams", self.teams), ("logic", self.logic)]: categories[category] = set(registry)
            world = True
        elif kind == "card" and entity_id in self.cards: categories["cards"].add(entity_id)
        elif kind == "character" and entity_id in self.characters:
            categories["characters"].add(entity_id)
            character = self.characters[entity_id]
            if include_dependencies and character.deck_id in self.decks: categories["decks"].add(character.deck_id)
            if include_dependencies and character.preferred_places: categories["places"].update(item for item in character.preferred_places if item in self.places)
        elif kind == "deck" and entity_id in self.decks: categories["decks"].add(entity_id)
        elif kind == "team" and entity_id in self.teams:
            categories["teams"].add(entity_id)
            team = self.teams[entity_id]
            if include_dependencies:
                categories["characters"].update(item for item in team.members if item in self.characters)
                categories["places"].update(item for item in team.preferred_places if item in self.places)
        elif kind == "place" and entity_id in self.places: categories["places"].add(entity_id)
        elif kind == "world":
            world = True
            for category, registry in [("cards", self.cards), ("characters", self.characters), ("decks", self.decks), ("places", self.places), ("teams", self.teams), ("logic", self.logic)]: categories[category] = set(registry)
        if include_dependencies:
            for deck_id in list(categories["decks"]):
                categories["cards"].update(item for item in DeckRules.all_cards(self.decks.get(deck_id, {})) if item in self.cards)
            for character_id in list(categories["characters"]):
                character = self.characters.get(character_id)
                if character:
                    categories["cards"].update(item for item in character.preferred_cards + character.best_cards + character.library_cards if item in self.cards)
                    if character.deck_id in self.decks: categories["decks"].add(character.deck_id)
            for team_id in list(categories["teams"]):
                team = self.teams.get(team_id)
                if team: categories["characters"].update(item for item in team.members if item in self.characters)
            for character_id in list(categories["characters"]):
                character = self.characters.get(character_id)
                if character and include_dependencies and character.deck_id in self.decks: categories["decks"].add(character.deck_id)
            for deck_id in list(categories["decks"]): categories["cards"].update(item for item in DeckRules.all_cards(self.decks.get(deck_id, {})) if item in self.cards)
        for card_id in list(categories["cards"]):
            card = self.cards.get(card_id)
            if card and card.logic_graph and card.logic_graph in self.logic: categories["logic"].add(card.logic_graph)
        return {"kind": kind, "entity_id": entity_id, "categories": categories, "world": world}

    def package_media_items(self, scope):
        result = []
        for category, ids in scope["categories"].items():
            registry = self.logic if category == "logic" else self.decks if category == "decks" else getattr(self, category, {})
            for entity_id in ids:
                entity = registry.get(entity_id) if isinstance(registry, dict) else None
                folder = str(self.logic_owners.get(entity_id, "")) if category == "logic" else entity.get("media_folder", "") if isinstance(entity, dict) else getattr(entity, "media_folder", "") if entity else ""
                if not folder: continue
                root = Path(folder) if category == "logic" else DATA / folder
                if not root.exists() or root == DATA: continue
                result.append({"category": category, "id": entity_id, "path": str(root.relative_to(DATA))})
        return result

    def export_cbp(self, kind, entity_id, include_experience=False, include_dependencies=True):
        scope = self.package_scope(kind, entity_id, include_dependencies)
        filename = DATA / "exports" / f"{slug(entity_id or kind)}.cbp"
        includes = {key: sorted(value) for key, value in scope["categories"].items()}
        media_items = self.package_media_items(scope)
        manifest = {"schema": 4, "kind": scope["kind"], "entity_id": entity_id, "created": time.time(), "asset_contract": "gdd_nested_v2", "experience_included": bool(include_experience), "world_included": bool(scope["world"]), "dependencies_included": bool(include_dependencies), "includes": includes, "required_categories": [key for key, value in includes.items() if value], "entity_media": media_items, "logic_owners": {logic_id: str(self.logic_owners[logic_id].relative_to(DATA)) for logic_id in includes.get("logic", []) if logic_id in self.logic_owners and self.logic_owners[logic_id].is_relative_to(DATA)}, "package_contract": "entity_dependency_closure_v2"}
        with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as archive:
            archive_names = {"manifest.json"}
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            for category, ids in scope["categories"].items():
                if category == "logic":
                    for logic_id in ids:
                        owner = self.logic_owners.get(logic_id)
                        path = owner / f"{logic_id}.json" if owner else None
                        archive_name = "logic/" + path.name if path and path.exists() else ""
                        if archive_name and archive_name not in archive_names:
                            archive.write(path, archive_name)
                            archive_names.add(archive_name)
                elif category == "decks":
                    archive.writestr("decks.json", json.dumps({key: self.decks[key] for key in ids if key in self.decks}, indent=2))
                else:
                    registry = getattr(self, category)
                    if category == "places": records = [self.authored_entry(registry[key], {"current_duels"}) for key in ids if key in registry]
                    else: records = [self.authored_entry(registry[key], CHARACTER_RUNTIME_FIELDS if category == "characters" else TEAM_RUNTIME_FIELDS if category == "teams" else set()) for key in ids if key in registry]
                    archive_name = category + ".json"
                    if archive_name not in archive_names:
                        archive.writestr(archive_name, json.dumps(records, indent=2))
                        archive_names.add(archive_name)
            if scope["world"] and "world.json" not in archive_names:
                archive.writestr("world.json", json.dumps(self.world, indent=2))
                archive_names.add("world.json")
            if include_experience:
                for category, ids in [("characters", scope["categories"]["characters"]), ("teams", scope["categories"]["teams"])]:
                    for entity_id in ids:
                        runtime_path = self.runtime_path(category, entity_id)
                        archive_name = f"runtime/{category}/{runtime_path.name}"
                        if runtime_path.exists() and archive_name not in archive_names:
                            archive.write(runtime_path, archive_name)
                            archive_names.add(archive_name)
            for item in media_items:
                root = DATA / item["path"]
                for media_path in root.rglob("*"):
                    archive_name = "data/" + str(media_path.relative_to(DATA))
                    if media_path.is_file() and media_path != filename and DATA / "exports" not in media_path.parents and archive_name not in archive_names:
                        archive.write(media_path, archive_name)
                        archive_names.add(archive_name)
        return filename

    def inspect_cbp(self, path):
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            manifest["available_files"] = sorted(archive.namelist())
            return manifest

    def package_preview(self, path):
        manifest = self.inspect_cbp(path)
        includes = manifest.get("includes", {})
        conflicts = {}
        registries = {"cards": self.cards, "characters": self.characters, "places": self.places, "teams": self.teams, "decks": self.decks, "logic": self.logic}
        for category, ids in includes.items():
            registry = registries.get(category, {})
            conflicts[category] = sorted(item for item in ids if item in registry)
        return {"manifest": manifest, "conflicts": conflicts, "counts": {category: len(ids) for category, ids in includes.items()}}

    def import_cbp(self, path, include=None, include_experience=None, conflict="replace"):
        conflict = conflict if conflict in ["replace", "skip", "reject"] else "replace"
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            available = set(archive.namelist())
            requested = set(manifest.get("required_categories", [])) if include is None else set(include)
            requested &= {"cards", "characters", "decks", "places", "teams", "logic"}
            if include_experience is None: include_experience = bool(manifest.get("experience_included", False))
            imported = []
            preview = self.package_preview(path)
            relevant_conflicts = {category: values for category, values in preview["conflicts"].items() if category in requested and values}
            if conflict == "reject" and relevant_conflicts: return {"imported": [], "source": str(path), "nested_media": True, "manifest": manifest, "experience_included": bool(include_experience), "rejected": True, "conflicts": relevant_conflicts}
            def can_write(category, entity_id):
                registry = self.logic if category == "logic" else self.decks if category == "decks" else getattr(self, category, {})
                return conflict != "skip" or entity_id not in registry
            def records(category):
                name = category + ".json"
                if name not in available: return []
                payload = json.loads(archive.read(name).decode("utf-8"))
                return payload if isinstance(payload, list) else list(payload.values())
            allowed = manifest.get("includes", {})
            if "cards" in requested:
                for entry in records("cards"):
                    if entry.get("id") in set(allowed.get("cards", [])) and can_write("cards", entry.get("id")): self.cards[entry["id"]] = CardDef(**entry)
                imported.append("cards")
            if "characters" in requested:
                for entry in records("characters"):
                    if entry.get("id") in set(allowed.get("characters", [])):
                        entry.setdefault("relationship", "stranger")
                        entry.setdefault("preferred_families", ["warrior"])
                        entry.setdefault("deck_id", "")
                        if can_write("characters", entry.get("id")): self.characters[entry["id"]] = CharacterDef(**entry)
                imported.append("characters")
            if "decks" in requested and "decks.json" in available:
                incoming = json.loads(archive.read("decks.json").decode("utf-8"))
                for deck_id in allowed.get("decks", []):
                    if deck_id in incoming and can_write("decks", deck_id): self.decks[deck_id] = dict(incoming[deck_id])
                imported.append("decks")
            if "places" in requested:
                for entry in records("places"):
                    if entry.get("id") in set(allowed.get("places", [])) and can_write("places", entry.get("id")): self.places[entry["id"]] = self.place_from_entry(entry)
                imported.append("places")
            if "teams" in requested:
                for entry in records("teams"):
                    if entry.get("id") in set(allowed.get("teams", [])) and can_write("teams", entry.get("id")): self.teams[entry["id"]] = TeamDef(**entry)
                imported.append("teams")
            if "logic" in requested:
                owners = manifest.get("logic_owners", {}) if isinstance(manifest.get("logic_owners", {}), dict) else {}
                for name in available:
                    if not name.startswith("logic/") or not name.endswith(".json"): continue
                    key = Path(name).stem
                    if key not in set(allowed.get("logic", [])) or not can_write("logic", key): continue
                    owner_relative = Path(str(owners.get(key, "")))
                    if len(owner_relative.parts) != 3 or owner_relative.parts[0] not in ["cards", "characters", "teams", "places", "decks"] or owner_relative.parts[2] != "logic": continue
                    owner = DATA / owner_relative
                    if owner == DATA or any(part in ["", ".", ".."] for part in owner_relative.parts): continue
                    owner.mkdir(parents=True, exist_ok=True)
                    self.logic[key] = LogicGraph.from_dict(json.loads(archive.read(name)))
                    self.logic_owners[key] = owner
                    write_json(owner / f"{key}.json", self.logic[key].to_dict())
                imported.append("logic")
            if include_experience:
                for name in available:
                    if not name.startswith("runtime/") or not name.endswith(".json"): continue
                    parts = Path(name).parts
                    if len(parts) != 3 or parts[1] not in ["characters", "teams"]: continue
                    category, entity_id = parts[1], Path(parts[2]).stem
                    if category not in requested or entity_id not in set(allowed.get(category, [])): continue
                    payload = json.loads(archive.read(name).decode("utf-8"))
                    target = self.characters.get(entity_id) if category == "characters" else self.teams.get(entity_id)
                    state = payload.get("state", payload) if isinstance(payload, dict) else {}
                    if target and isinstance(state, dict):
                        for key, value in state.items():
                            if hasattr(target, key): setattr(target, key, value)
            media_roots = [Path(item.get("path", "")) for item in manifest.get("entity_media", []) if item.get("category") in requested]
            skip_media_roots = []
            if conflict == "skip":
                conflicting_ids = {category: set(values) for category, values in preview["conflicts"].items()}
                for item in manifest.get("entity_media", []):
                    if item.get("category") not in requested or item.get("id") not in conflicting_ids.get(item.get("category"), set()): continue
                    skip_media_roots.append(Path(item.get("path", "")))
            for name in available:
                if not name.startswith("data/") or name.endswith("/"): continue
                relative = Path(name[5:])
                if any(part in ["", ".", ".."] for part in relative.parts): continue
                category = relative.parts[0] if relative.parts else ""
                if category not in ["cards", "characters", "teams", "places", "decks"] or category not in requested: continue
                if any(relative.parts[:len(root.parts)] == root.parts for root in skip_media_roots if root.parts): continue
                target = DATA / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        self.ensure_behavior_weights()
        self.ensure_entity_scaffolds()
        self.media.scan()
        self.save()
        return {"imported": sorted(imported), "source": str(path), "nested_media": True, "manifest": manifest, "experience_included": bool(include_experience), "conflict": conflict, "conflicts": preview["conflicts"], "requested": sorted(requested)}


def query_entities(values, query="", sort_mode="name"):
    query = (query or "").strip().lower()
    items = [value for value in values if not query or query in value.name.lower()]
    if sort_mode == "rank": items.sort(key=lambda value: (-int(getattr(value, "rank", 1)), value.name.lower()))
    else: items.sort(key=lambda value: value.name.lower())
    return items


class DeckRules:
    minimum = 0
    maximum = 0
    copies = 0
    fusion_minimum = 0
    fusion_maximum = 0
    legendary_copies = 0
    legendary_no_other = False

    @classmethod
    def configure(cls, rules):
        deck = dict((rules or {}).get("deck") or {})
        main = dict(deck.get("main") or {})
        fusion = dict(deck.get("fusion_extra") or {})
        legendary = dict((rules or {}).get("legendary") or {})
        cls.minimum = max(0, int(main.get("minimum", 0) or 0))
        cls.maximum = max(cls.minimum, int(main.get("maximum", cls.minimum) or cls.minimum))
        cls.copies = max(1, int(main.get("copy_limit", 1) or 1))
        cls.fusion_minimum = max(0, int(fusion.get("minimum", 0) or 0))
        cls.fusion_maximum = max(cls.fusion_minimum, int(fusion.get("maximum", cls.fusion_minimum) or cls.fusion_minimum))
        cls.legendary_copies = max(1, int(legendary.get("copy_limit", 1) or 1))
        cls.legendary_no_other = bool(legendary.get("no_other_legendary_deck_rule", False))

    @classmethod
    def all_cards(cls, deck):
        return list((deck or {}).get("main_cards", []) or []) + list((deck or {}).get("fusion_cards", []) or [])

    @classmethod
    def partition(cls, card_ids, available):
        main = []
        fusion = []
        for card_id in card_ids:
            card = available.get(card_id)
            if not card: continue
            if card.kind == "fusion": fusion.append(card_id)
            else: main.append(card_id)
        return main, fusion

    @classmethod
    def normalized(cls, card_ids, available):
        result = []
        counts = {}
        for card_id in card_ids:
            card = available.get(card_id)
            if not card or card.kind == "fusion": continue
            limit = cls.legendary_copies if card.legendary else cls.copies
            if counts.get(card_id, 0) >= limit or len(result) >= cls.maximum: continue
            result.append(card_id)
            counts[card_id] = counts.get(card_id, 0) + 1
        return result

    @classmethod
    def normalized_fusion(cls, card_ids, available):
        result = []
        counts = {}
        for card_id in card_ids:
            card = available.get(card_id)
            if not card or card.kind != "fusion": continue
            limit = cls.legendary_copies if card.legendary else cls.copies
            if counts.get(card_id, 0) >= limit or len(result) >= cls.fusion_maximum: continue
            result.append(card_id)
            counts[card_id] = counts.get(card_id, 0) + 1
        return result

    @classmethod
    def validate(cls, main_cards, fusion_cards, available):
        errors = []
        main = list(main_cards or [])
        fusion = list(fusion_cards or [])
        if len(main) < cls.minimum: errors.append(f"minimum {cls.minimum} main-deck cards")
        if len(main) > cls.maximum: errors.append(f"maximum {cls.maximum} main-deck cards")
        if len(fusion) < cls.fusion_minimum: errors.append(f"minimum {cls.fusion_minimum} Fusion/Extra cards")
        if len(fusion) > cls.fusion_maximum: errors.append(f"maximum {cls.fusion_maximum} Fusion/Extra cards")
        counts = {}
        legendary_ids = set()
        for collection, card_ids in [("Main Deck", main), ("Fusion/Extra", fusion)]:
            for card_id in card_ids:
                card = available.get(card_id)
                if not card:
                    errors.append(f"unknown card {card_id}")
                    continue
                if collection == "Main Deck" and card.kind == "fusion": errors.append(f"{card.name} must be in Fusion/Extra")
                if collection == "Fusion/Extra" and card.kind != "fusion": errors.append(f"{card.name} is not a Fusion card")
                counts[card_id] = counts.get(card_id, 0) + 1
                limit = cls.legendary_copies if card.legendary else cls.copies
                if counts[card_id] > limit: errors.append(f"{card.name} exceeds its copy limit")
                if card.legendary:
                    legendary_ids.add(card_id)
        if cls.legendary_no_other and len(legendary_ids) > 1: errors.append("only one Legendary card may be used")
        return list(dict.fromkeys(errors))

    @classmethod
    def summary(cls, main_cards, fusion_cards, available):
        errors = cls.validate(main_cards, fusion_cards, available)
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
        deck = store.decks.get(character.deck_id, {})
        main_ids = DeckRules.normalized(deck.get("main_cards", []), store.cards)
        fusion_ids = DeckRules.normalized_fusion(deck.get("fusion_cards", []), store.cards)
        loan_cards = [record.get("card_id", "") for record in store.world.setdefault("borrows", []) if record.get("state") == "active" and record.get("borrower") == character.id and record.get("card_id") in store.cards]
        main_ids = DeckRules.normalized(main_ids + [card_id for card_id in loan_cards if store.cards[card_id].kind != "fusion"], store.cards)
        fusion_ids = DeckRules.normalized_fusion(fusion_ids + [card_id for card_id in loan_cards if store.cards[card_id].kind == "fusion"], store.cards)
        for card_id in fusion_ids:
            instance = CardInstance(store.cards[card_id], self.name)
            instance.position = "extra"
            instance.last_zone = "extra"
            self.extra.append(instance)
        for card_id in main_ids:
            instance = CardInstance(store.cards[card_id], self.name)
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

    def __init__(self, store, player_id=None, opponent_id=None, place_id=None, cpu=False, team_effect=None, opponent_team_effect=None, first_side=None, duel_mode="current", time_limit=180.0, duel_terms=None, reward_policy=None):
        self.store = store
        roles = store.role_config()
        player_id = player_id or roles["player_character"]
        opponent_id = opponent_id or roles["default_opponent_character"]
        place_id = place_id or roles["default_place"]
        self.player = Duelist(store.characters[player_id], store)
        self.opponent = Duelist(store.characters[opponent_id], store)
        self.place = store.places[place_id]
        self.first_side = first_side if first_side in ["player", "opponent"] else "opponent" if cpu else "player"
        self.active = self.player if self.first_side == "player" else self.opponent
        normalized_terms = store.normalize_duel_terms("1v1", duel_mode, time_limit) if duel_terms is None else dict(duel_terms)
        self.duel_mode = normalized_terms.get("mode", "current") if normalized_terms.get("mode", "current") in DUEL_MODES else "current"
        self.time_limit = float(normalized_terms.get("time_limit", 0.0) or 0.0)
        self.duel_elapsed = 0.0
        self.time_expired = False
        self.gamble_state = dict(normalized_terms) if self.duel_mode == "gamble" and normalized_terms.get("state") == "reserved" else {}
        self.gamble_selection_pending = False
        self.outcome_narrator = {}
        self.reward_policy = dict(reward_policy) if isinstance(reward_policy, dict) else reward_policy
        if self.duel_mode == "gamble" and not self.gamble_state:
            reserved_terms = store.reserve_gamble_terms(player_id, opponent_id, normalized_terms)
            if reserved_terms: self.gamble_state = reserved_terms
            else: self.duel_mode, self.time_limit = "current", 0.0
        self.watcher_ids = []
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
        self.presentation_events = []
        self.presentation_sequence = 0
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

    def set_watchers(self, watcher_ids):
        self.watcher_ids = list(dict.fromkeys(str(item) for item in list(watcher_ids or []) if str(item) in self.store.characters))[:6]
        return list(self.watcher_ids)

    def watcher_pressure(self, actor):
        pressure = 0.0
        for watcher_id in self.watcher_ids:
            relation = self.store.relationship_for(watcher_id, actor.character.id)
            watcher = self.store.characters.get(watcher_id)
            if relation == "ally": pressure += float(watcher.behavior_weights.get("ally_bias", 4.0)) * 0.12 if watcher else 0.4
            elif relation == "enemy": pressure += float(watcher.behavior_weights.get("enemy_bias", 6.0)) * 0.08 if watcher else 0.3
        return min(3.0, pressure)

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
        self.store.set_relationship(actor.id, target.id, relation, action)
        actor.history.append({"type": "interaction", "action": action, "target": target.id, "time": time.time()})
        target.history.append({"type": "interaction_received", "action": action, "actor": actor.id, "time": time.time()})
        self.log(f"{actor.name} {action}s with {target.name}; mood becomes {target.mood}.")
        self.react("pfp_" + action, actor.id, target.id, "opponent")
        self.store.save()

    def react(self, event, actor_id, target_id="", relation="stranger", entity_type="characters", entity_id="", mode="hang", metadata=None):
        if relation == "opponent": relation = self.store.relationship_for(actor_id, target_id)
        selection = self.reaction_resolver.resolve(event, actor_id, target_id, relation, entity_type, entity_id, self.place.id, mode, None, metadata)
        selection.metadata = dict(metadata or {})
        record = {"kind": "reaction", "event": event, "actor": actor_id, "target": target_id, "relation": relation, "selection": selection.to_dict(), "metadata": dict(metadata or {}), "sequence": len(self.reaction_events) + 1, "time": time.time()}
        self.reaction_events.append(record)
        self.reaction_events = self.reaction_events[-100:]
        self.log(f"MEDIA {event}: {selection.source} variant {selection.variant or 'placeholder'}")
        return selection

    def logical_anchor(self, side, zone, card=None):
        duelist = self.player if side == "player" else self.opponent
        collection = duelist.monsters if zone == "monster" else duelist.spells if zone == "spell_trap" else []
        index = collection.index(card) if card in collection else -1
        return {"side": side, "zone": zone, "index": index, "card_id": card.card.id if isinstance(card, CardInstance) else ""}

    def card_react(self, event, card, owner, other=None, metadata=None, mode="hang"):
        other = other or self.other(owner)
        data = dict(metadata or {})
        data.setdefault("card_id", card.card.id if isinstance(card, CardInstance) else "")
        data.setdefault("anchor", self.logical_anchor(self.side_key(owner), "monster" if card in owner.monsters else "spell_trap", card))
        return self.react(event, owner.character.id, other.character.id if other else "", "opponent", "cards", card.card.id if isinstance(card, CardInstance) else "", mode, data)

    def emit_attack_presentation(self, attacker_side, attacker, target=None, target_side=None, direct=False):
        target_side = target_side or self.other(attacker_side)
        self.presentation_sequence += 1
        source_anchor = self.logical_anchor(self.side_key(attacker_side), "monster", attacker)
        target_anchor = {"side": self.side_key(target_side), "zone": "duelist" if direct or target is None else "monster", "index": -1 if direct or target is None else target_side.monsters.index(target), "card_id": target.card.id if isinstance(target, CardInstance) else ""}
        vfx = self.store.media.vfx_path("attack", attacker.card.id, attacker_side.character.id)
        selection = ReactionSelection("attack_travel", attacker_side.character.id, target_side.character.id if direct or target is None else target.card.id, self.store.relationship_for(attacker_side.character.id, target_side.character.id), vfx or "universal", 1 if vfx else 0, vfx, "", "hang", not bool(vfx), [], "", 0.72, 0.72, FPS, "hang", {"kind": "attack", "source_anchor": source_anchor, "target_anchor": target_anchor, "direct": bool(direct or target is None), "presentation_id": "attack_presentation_" + str(self.presentation_sequence)}, {"card_id": attacker.card.id, "target_card_id": target.card.id if isinstance(target, CardInstance) else "", "amount": 0})
        record = {"kind": "presentation", "event": "attack_travel", "actor": attacker_side.character.id, "target": target_side.character.id if direct or target is None else target.card.id, "relation": selection.relation, "presentation_id": selection.presentation.get("presentation_id", ""), "selection": selection.to_dict(), "metadata": dict(selection.metadata), "sequence": self.presentation_sequence, "time": time.time()}
        self.presentation_events.append(record)
        self.presentation_events = self.presentation_events[-50:]
        self.reaction_events.append(record)
        self.reaction_events = self.reaction_events[-100:]
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
        selector = selector or self.card_selector(card, actor)
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
        if procedure.kind == "ritual" and sum(item.card.stars for item in selected) != procedure.min_stars:
            return False, f"Ritual summoning requires exactly {procedure.min_stars} material stars."
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

    def procedure_enabler_valid(self, procedure, enabler, enabler_effect_id):
        if procedure.kind not in ["fusion", "ritual", "legendary"]: return True, ""
        contract = dict(procedure.enabler or {})
        if not enabler: return False, f"{procedure.kind.title()} summoning requires its authored enabler."
        definition = getattr(enabler, "card", enabler)
        allowed_ids = list(contract.get("card_ids", contract.get("required_card_ids", [])) or [])
        allowed_kinds = list(contract.get("card_kinds", []) or [])
        allowed_effect_ids = list(contract.get("effect_ids", []) or [])
        allowed_effect_ids.extend(list(contract.get("actions", [contract.get("action", "")] if contract.get("action") else []) or []))
        if allowed_ids and definition.id not in allowed_ids: return False, "That card is not an authored enabler for this summon."
        if allowed_kinds and definition.kind not in allowed_kinds: return False, "That card type cannot enable this summon."
        if allowed_effect_ids and enabler_effect_id not in allowed_effect_ids and enabler_effect_id != contract.get("effect_id", ""): return False, "That effect is not an authored summon enabler."
        owner = self.owner_of(enabler)
        if owner is None: return False, "The summon enabler is no longer in the duel."
        if owner is not self.player and owner is not self.opponent: return False, "The summon enabler has no duel owner."
        return True, ""

    def begin_summon_procedure(self, card, actor, procedure=None, enabler=None, enabler_effect_id=""):
        procedure = procedure or ProcedureSpec.from_card(card)
        source_zones = list(procedure.source_zones or (["extra"] if procedure.kind == "fusion" else ["hand"]))
        source_cards = []
        for zone in source_zones: source_cards.extend(SelectorRuntime(self, actor, card).zone_items(actor, zone))
        if card not in source_cards: return False, "Select a summon card from its legal source zone."
        if procedure.source_selector and not SelectorRuntime(self, actor, card).matches(card, procedure.source_selector): return False, "The summon card is not in its allowed source state."
        allowed_source_zones = procedure.source_selector.get("zone", source_zones) if procedure.source_selector else source_zones
        allowed_source_zones = allowed_source_zones if isinstance(allowed_source_zones, list) else [allowed_source_zones]
        if card.position not in allowed_source_zones and card.last_zone not in allowed_source_zones: return False, "The summon card is not in its allowed source zone."
        if procedure.kind not in ["fusion", "ritual", "tribute", "legendary"]: return False, "This summon procedure is not implemented."
        if procedure.special and procedure.kind != "legendary": return False, "This monster requires an authored special summon procedure."
        valid_enabler, reason = self.procedure_enabler_valid(procedure, enabler, enabler_effect_id)
        if not valid_enabler: return False, reason
        if procedure.kind == "tribute" and self.normal_summon_remaining(actor) <= 0: return False, "No normal summon permission remains this turn."
        if not any(value is None for value in actor.monsters): return False, "All five monster zones are occupied."
        if procedure.costs:
            cost_spec = EffectSpec.from_dict({"id": card.card.id + "_procedure_cost", "trigger": "summon", "cost": procedure.costs}, card.card.id + "_procedure_cost")
            valid, result = self.preflight_costs(cost_spec, card, actor)
            if not valid: return False, result.get("reason", "The summon procedure cost cannot be paid.")
        self.pending_procedure = {"card": card, "actor": actor, "procedure": procedure, "enabler": enabler, "enabler_effect_id": enabler_effect_id, "candidates": [], "selected": [], "required": 0, "snapshot": [], "costs_paid": False, "transaction": self.capture_procedure_transaction()}
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
        if procedure.kind == "legendary": return self.resolve_pending_procedure([])
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
        placed, reason = self.place_procedure_summon(card, actor, procedure.source_method or procedure.kind, source_zone, pending.get("enabler"), pending.get("enabler_effect_id", ""))
        if not placed: return self.abort_procedure(reason)
        self.pending_procedure = None
        notification = self.pending_notification("choose_cards")
        if notification: notification.status, notification.answer = "resolved", "ok"
        self.log(f"{actor.name} {procedure.kind} summons {card.card.name}.")
        self.react(procedure.kind + "_summon", actor.character.id, self.other(actor).character.id, "opponent", "cards", card.card.id)
        self.run_logic(card, "summon", actor, self.other(actor))
        return True, ""

    def _manual_procedure_summon(self, card, actor, kind, materials, enabler=None, enabler_effect_id=""):
        procedure = ProcedureSpec.from_card(card)
        if procedure.kind != kind: return False, "The card does not declare the requested summon procedure."
        started = self.begin_summon_procedure(card, actor, procedure, enabler, enabler_effect_id)
        if not started[0]: return started
        if self.pending_cost: return True, "pending_cost"
        return self.resolve_pending_procedure(materials)

    def fusion_summon(self, card, materials=None, enabler=None, enabler_effect_id=""):
        if self.finished or self.active is not self.player or self.phase not in ["MAIN 1", "MAIN 2"]: return False, "Fusion summoning is only available during your main phase."
        if card.card.summon_method != "fusion" or card not in self.player.extra: return False, "Select a Fusion monster from the Extra Deck."
        if enabler is None: return False, "Activate an authored Fusion Spell or effect first."
        procedure = ProcedureSpec.from_card(card)
        return self.begin_summon_procedure(card, self.player, procedure, enabler, enabler_effect_id) if materials is None else self._manual_procedure_summon(card, self.player, "fusion", materials, enabler, enabler_effect_id)

    def ritual_summon(self, card, tributes=None, enabler=None, enabler_effect_id=""):
        if self.finished or self.active is not self.player or self.phase not in ["MAIN 1", "MAIN 2"]: return False, "Ritual summoning is only available during your main phase."
        if card.card.summon_method != "ritual" or card not in self.player.hand: return False, "Select a Ritual monster from your hand."
        if enabler is None: return False, "Activate an authored Ritual Spell or effect first."
        procedure = ProcedureSpec.from_card(card)
        return self.begin_summon_procedure(card, self.player, procedure, enabler, enabler_effect_id) if tributes is None else self._manual_procedure_summon(card, self.player, "ritual", tributes, enabler, enabler_effect_id)

    def summon(self, card, actor=None):
        actor = actor or self.player
        if self.finished or self.active is not actor or self.phase not in ["MAIN 1", "MAIN 2"]:
            return False, "Summoning is only available during your main phase."
        if card not in actor.hand or card.card.kind not in ["normal", "effect", "legendary"]:
            return False, "Select a monster from your hand."
        if card.card.kind == "legendary": return False, "Legendary cards require their authored special summon procedure."
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
        if card.card.kind == "legendary": return False, "Legendary cards cannot be set."
        is_monster = card.card.kind in ["normal", "effect"]
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
        selector = activate_spec.selector if activate_spec and activate_spec.selector else self.card_selector(card, actor)
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
        if bool(getattr(card.card, "non_removable", False)) and card.position in ["field", "monster", "spell", "set"] and destination in ["graveyard", "banished", "hand", "deck"]: return False
        source_zone = card.position
        source_anchor = self.logical_anchor(self.side_key(owner), "monster" if card in owner.monsters else "spell_trap", card)
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
        movement_metadata = {"from_zone": source_zone, "to_zone": destination, "owner": owner.character.id, "anchor": source_anchor, "card_id": card.card.id}
        self.emit_event("movement", owner, source=card, target=card, metadata=movement_metadata)
        if destination == "hand": self.card_react("return", card, owner, self.other(owner), movement_metadata)
        elif destination == "banished": self.card_react("banish", card, owner, self.other(owner), movement_metadata)
        elif destination == "graveyard": self.card_react("send_to_graveyard", card, owner, self.other(owner), movement_metadata)
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
                    selector = spec.selector or self.card_selector(card, side)
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
        selector = spec.selector or self.card_selector(card, actor)
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

    def knowledge_character(self, viewer):
        side = viewer if isinstance(viewer, Duelist) else self.player if str(viewer) == "player" else self.opponent
        return side.character if side else None

    def known_card(self, viewer, card_or_id):
        card_id = card_or_id.card.id if isinstance(card_or_id, CardInstance) else str(card_or_id)
        side = viewer if isinstance(viewer, Duelist) else self.player if str(viewer) == "player" else self.opponent
        if not side: return False
        if isinstance(card_or_id, CardInstance) and self.owner_of(card_or_id) is side: return True
        viewer_key = self.side_key(side)
        if card_id in self.knowledge.get(viewer_key, {}).get("card_ids", []): return True
        memory = getattr(side.character, "knowledge_state", {}).get("cards", {})
        item = memory.get(card_id, {}) if isinstance(memory, dict) else {}
        return float(item.get("confidence", 0.0) or 0.0) >= 0.35

    def learn_visible_card(self, viewer, card, visibility):
        character = self.knowledge_character(viewer)
        if not character: return
        state = character.knowledge_state.setdefault("cards", {})
        record = dict(state.get(card.card.id, {}) or {})
        already_seen = record.get("last_seen_turn") == self.turn and record.get("last_seen_phase") == self.phase and record.get("visibility") == visibility
        record.update({"card_id": card.card.id, "last_seen_turn": self.turn, "last_seen_phase": self.phase, "visibility": visibility, "confidence": 1.0})
        if not already_seen: record["sightings"] = int(record.get("sightings", 0)) + 1
        state[card.card.id] = record
        owner = self.owner_of(card)
        if owner and owner is not (self.player if viewer is self.player or str(viewer) == "player" else self.opponent):
            opponents = character.knowledge_state.setdefault("opponents", {})
            opponent = opponents.setdefault(owner.character.id, {"cards": {}, "effects": {}, "sightings": 0})
            prior = dict(opponent.get("cards", {}).get(card.card.id, {}) or {})
            seen_before = prior.get("last_seen_turn") == self.turn and prior.get("last_seen_phase") == self.phase
            prior.update({"last_seen_turn": self.turn, "last_seen_phase": self.phase, "confidence": 1.0})
            if not seen_before: prior["sightings"] = int(prior.get("sightings", 0)) + 1
            opponent.setdefault("cards", {})[card.card.id] = prior
            if not seen_before:
                opponent["sightings"] = int(opponent.get("sightings", 0)) + 1
                character.learned_cards[card.card.id] = int(character.learned_cards.get(card.card.id, 0)) + 1
        if not already_seen: character.learning_state["observations"] = int(character.learning_state.get("observations", 0)) + 1

    def observe_visible_information(self, viewer):
        viewer_key = self.side_key(viewer) if isinstance(viewer, Duelist) else str(viewer)
        if viewer_key not in self.knowledge: return
        side = self.player if viewer_key == "player" else self.opponent
        known_cards = set(self.knowledge[viewer_key].get("card_ids", []))
        known_effects = set(self.knowledge[viewer_key].get("effect_ids", []))
        effect_facts = dict(self.knowledge[viewer_key].get("effect_facts", {}))
        for card in self.card_instances():
            visibility = self.visibility(side, card)
            if visibility == "hidden": continue
            known_cards.add(card.card.id)
            self.learn_visible_card(side, card, visibility)
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
        state = {"turn": self.turn, "phase": self.phase, "active": self.side_key(self.active), "finished": self.finished, "winner": self.side_key(self.winner) if self.winner else "", "duel_mode": self.duel_mode, "time_limit": self.time_limit, "duel_elapsed": self.duel_elapsed, "time_remaining": max(0.0, self.time_limit - self.duel_elapsed) if self.duel_mode == "timed" else None, "gamble": {"state": self.gamble_state.get("state", "") if self.gamble_state else "", "wager_count": self.gamble_state.get("wager_count", 0) if self.gamble_state else 0, "revealed": list(self.gamble_state.get("revealed", [])) if self.gamble_state and self.gamble_state.get("state") in ["revealed", "settled", "returned"] else [], "selection_pending": bool(self.gamble_selection_pending)}, "outcome_narrator": dict(self.outcome_narrator), "players": [], "knowledge": self.knowledge_for(viewer)}
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
        if self.pending_procedure:
            pending = self.pending_procedure
            procedure = pending.get("procedure")
            return {"kind": "procedure", "procedure": procedure.kind if procedure else "", "actor": self.side_key(pending.get("actor")), "card": pending.get("card").card.id if pending.get("card") else "", "enabler": pending.get("enabler").card.id if pending.get("enabler") else "", "enabler_effect_id": pending.get("enabler_effect_id", ""), "selected": [self.pending_ref(item) for item in pending.get("selected", [])], "candidates": [self.pending_ref(item) for item in pending.get("candidates", [])]}
        if self.pending_cost or self.pending_response or self.pending_trigger_order: return {"kind": "unsupported_interactive", "supported": False}
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
        return {"schema": "cbp.state.v1", "turn": self.turn, "phase_index": self.phase_index, "first_side": self.first_side, "duel_mode": self.duel_mode, "time_limit": self.time_limit, "duel_elapsed": self.duel_elapsed, "time_expired": self.time_expired, "gamble_state": dict(self.gamble_state), "gamble_selection_pending": self.gamble_selection_pending, "outcome_narrator": dict(self.outcome_narrator), "watchers": sorted(self.watcher_ids), "active": self.side_key(self.active), "finished": self.finished, "winner": self.side_key(self.winner) if self.winner else "", "reason": self.reason, "cpu": self.cpu, "player": self.checkpoint_side(self.player), "opponent": self.checkpoint_side(self.opponent), "field_card": self.checkpoint_card(self.field_card) if self.field_card else None, "field_card_owner": self.side_key(self.field_card_owner) if self.field_card_owner else "", "effect_sequence": self.effect_sequence, "notification_sequence": self.notification_sequence, "rule_event_sequence": self.rule_event_sequence, "trigger_group_sequence": self.trigger_group_sequence, "chain_sequence": self.chain_sequence, "continuous_sequence": self.continuous_sequence, "summon_permissions": self.summon_permissions, "team_effect": self.team_effect, "opponent_team_effect": self.opponent_team_effect, "knowledge": self.export_knowledge(), "notifications": [item.__dict__.copy() for item in self.notifications], "notification_history": list(self.notification_history), "observation_sequence": self.observation_sequence, "observation_log": list(self.observation_log), "event_history": list(self.event_history), "chain_history": list(self.chain_history), "resolution_history": list(self.resolution_history), "chain": self.checkpoint_chain(), "pending": self.pending_payload()}

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
            self.first_side = payload.get("first_side") if payload.get("first_side") in ["player", "opponent"] else "player"
            self.duel_mode = payload.get("duel_mode") if payload.get("duel_mode") in DUEL_MODES else "current"
            self.time_limit = max(0.0, float(payload.get("time_limit", 0.0) or 0.0))
            self.duel_elapsed = max(0.0, float(payload.get("duel_elapsed", 0.0) or 0.0))
            self.time_expired = bool(payload.get("time_expired", False))
            self.gamble_state = dict(payload.get("gamble_state", {})) if isinstance(payload.get("gamble_state", {}), dict) else {}
            self.gamble_selection_pending = bool(payload.get("gamble_selection_pending", False))
            self.outcome_narrator = dict(payload.get("outcome_narrator", {})) if isinstance(payload.get("outcome_narrator", {}), dict) else {}
            self.watcher_ids = list(dict.fromkeys(str(item) for item in payload.get("watchers", []) if str(item) in self.store.characters and str(item) not in [self.player.character.id, self.opponent.character.id]))[:6]
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
            for recipient, value in zip(recipients, values):
                self.emit_event("damage", actor, source=card, target=recipient, metadata={"amount": value, "requested": amount})
                if isinstance(recipient, Duelist):
                    self.react("damage_dealt", actor.character.id, recipient.character.id, "opponent", "characters", actor.character.id, "hang", {"amount": value, "source_card_id": card.card.id if isinstance(card, CardInstance) else "", "direct": True})
                    self.react("damage_received", recipient.character.id, actor.character.id, "opponent", metadata={"amount": value, "source_card_id": card.card.id if isinstance(card, CardInstance) else ""})
                elif isinstance(recipient, CardInstance):
                    recipient_owner = self.owner_of(recipient) or self.other(actor)
                    self.card_react("hit", recipient, recipient_owner, actor, {"amount": value, "source_card_id": card.card.id if isinstance(card, CardInstance) else "", "cause": "effect"})
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
                anchor = self.logical_anchor(self.side_key(self.owner_of(selected_card) or actor), "monster" if selected_card in (self.owner_of(selected_card) or actor).monsters else "spell_trap", selected_card)
                if action == "set_face_up": selected_card.face_up = True
                elif action == "set_face_down": selected_card.face_up = False
                elif selected_card.face_up: selected_card.battle_position = "defense" if selected_card.battle_position == "attack" else "attack"
                values.append({"id": selected_card.card.id, "face_up": selected_card.face_up, "position": selected_card.battle_position})
                self.emit_event(action, actor, source=card, target=selected_card, metadata={"face_up": selected_card.face_up, "position": selected_card.battle_position})
                owner = self.owner_of(selected_card) or actor
                self.card_react("flip" if action in ["set_face_up", "set_face_down"] else "switch_position", selected_card, owner, self.other(owner), {"anchor": anchor, "face_up": selected_card.face_up, "position": selected_card.battle_position, "cause": "effect"})
            result["value"] = values
            self.log(f"{source} changes state of {len(selected_cards)} card(s).")
        elif action in ["boost_attack", "boost_defense"]:
            selected_cards = [item for item in targets if isinstance(item, CardInstance)] or [card]
            values = []
            for selected_card in selected_cards:
                if action == "boost_attack": selected_card.attack_bonus += amount; values.append(selected_card.attack_bonus)
                else: selected_card.defense_bonus += amount; values.append(selected_card.defense_bonus)
                owner = self.owner_of(selected_card) or actor
                self.card_react("stat_change", selected_card, owner, self.other(owner), {"anchor": self.logical_anchor(self.side_key(owner), "monster" if selected_card in owner.monsters else "spell_trap", selected_card), "amount": amount, "stat": "attack" if action == "boost_attack" else "defense", "cause": "effect"})
            result["value"] = values[0] if len(values) == 1 else values
            result["target_ids"] = [item.card.id for item in selected_cards]
            label = "ATK" if action == "boost_attack" else "DEF"
            self.log(f"{source} modifies {len(selected_cards)} card(s) by {amount} {label}.")
        elif action == "destroy":
            selected_cards = [item for item in targets if isinstance(item, CardInstance)] or [card]
            for selected_card in selected_cards:
                owner = self.owner_of(selected_card) or actor
                anchor = self.logical_anchor(self.side_key(owner), "monster" if selected_card in owner.monsters else "spell_trap", selected_card)
                self.card_react("destroy", selected_card, owner, self.other(owner), {"anchor": anchor, "cause": "effect", "destroyed_by": card.card.id if isinstance(card, CardInstance) else ""})
            moved = [item.card.id for item in selected_cards if self.move_card(item, "graveyard")]
            result["value"] = moved
            result["status"] = "resolved" if moved else "blocked"
            if moved: self.log(f"{source} destroys {len(moved)} card(s).")
        elif action == "control":
            selected_cards = [item for item in targets if isinstance(item, CardInstance)] or [card]
            moved = []
            for selected_card in selected_cards:
                current_owner = self.owner_of(selected_card)
                if bool(getattr(selected_card.card, "non_removable", False)): continue
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

    def card_selector(self, card, actor):
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
        selector = spec.selector or self.card_selector(card, actor)
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
            if action_name in ["fusion_summon", "ritual_summon"]:
                selected_summon = resolved[0] if isinstance(resolved, list) and resolved else resolved
                if not isinstance(selected_summon, CardInstance): return False
                expected_kind = "fusion" if action_name == "fusion_summon" else "ritual"
                if selected_summon.card.kind != expected_kind: return False
                result = self.begin_summon_procedure(selected_summon, actor, ProcedureSpec.from_card(selected_summon), card, spec.effect_id)
                if not result[0]: return False
                if result[1] == "pending_procedure": return False
                continue
            if action_name in ["summon", "special_summon"]:
                summon_selector = action.get("select") or (target_value if isinstance(target_value, dict) else spec.selector)
                summon_method = str(action.get("method", "special" if action_name == "special_summon" else "special")).lower()
                summon_count = action.get("count", len(resolved) if isinstance(resolved, list) else 1)
                candidate_selector = dict(summon_selector or {})
                candidate_selector["count"] = "all"
                summon_source = SelectorRuntime(self, actor, card).select(candidate_selector)
                if summon_source:
                    if summon_method in ["fusion", "ritual", "normal"] or any(summon_card.card.kind == "legendary" for summon_card in summon_source):
                        for summon_card in summon_source[:int(summon_count or 1)]:
                            if summon_card.card.kind == "legendary": summon_result = self.begin_summon_procedure(summon_card, actor, ProcedureSpec.from_card(summon_card), card, spec.effect_id)
                            elif summon_method in ["fusion", "ritual"]: summon_result = self.begin_summon_procedure(summon_card, actor, ProcedureSpec.from_card(summon_card), card, spec.effect_id)
                            else: summon_result = self.summon(summon_card, actor)
                            if not summon_result[0] or summon_result[1] in ["pending_procedure", "pending_cost"]: return False
                    else:
                        summon_result = self.special_summon({"side": "both", "zone": "any", "card_id": [item.card.id for item in summon_source], "count": summon_count}, actor, summon_method, card, spec.effect_id, summon_count)
                        if summon_result[1] == "pending": return False
                continue
            amount = action.get("amount", 0)
            if isinstance(amount, dict): amount = amount.get("value", 0)
            self.apply_effect(card, action_name, int(amount or 0), actor, resolved, card.card.name, spec.trigger)
        if spec.media:
            cue = spec.media.get("cue", spec.effect_id)
            mode = spec.media.get("mode", "hang")
            self.react(cue, actor.character.id, default_target.character.id, "opponent", "cards", card.card.id if isinstance(card, CardInstance) else "", mode, {"effect_id": spec.effect_id, "source_card_id": card.card.id if isinstance(card, CardInstance) else ""})
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
        self.emit_attack_presentation(attacker_side, attacker, target, defender_side, not bool(targets))
        self.card_react("attack", attacker, attacker_side, defender_side, {"target_card_id": target.card.id if isinstance(target, CardInstance) else "", "direct": not bool(targets)})
        if not target:
            damage = self.effective_atk(attacker, attacker_side)
            defender_side.hp = max(0, defender_side.hp - damage)
            self.emit_event("damage", attacker_side, source=attacker, target=defender_side, metadata={"amount": damage, "source": "battle", "direct": True})
            self.log(f"{attacker.card.name} attacks directly for {damage}.")
            self.react("direct_damage", attacker_side.character.id, defender_side.character.id, "opponent", metadata={"amount": damage, "direct": True})
            self.react("attack", attacker_side.character.id, defender_side.character.id, "opponent", metadata={"amount": damage, "direct": True})
            self.check_end()
            return True, ""
        if not target.face_up:
            target.face_up = True
            self.log(f"{target.card.name} flips face-up.")
            self.emit_event("flip", defender_side, source=target, target=target, metadata={"position": target.battle_position})
            self.card_react("flip", target, defender_side, attacker_side, {"revealed_by_attack": True, "position": target.battle_position})
            self.react("flip_reveal", defender_side.character.id, attacker_side.character.id, "opponent", metadata={"card_id": target.card.id, "position": target.battle_position})
            self.resolve(target, "flip", actor=defender_side, target=attacker)
            self.run_logic(target, "flip", defender_side, attacker_side)
        attack_value = self.effective_atk(attacker, attacker_side)
        target_in_attack = target.battle_position == "attack"
        target_value = self.battle_value(target, defender_side)
        if attack_value > target_value:
            target_anchor = self.logical_anchor(self.side_key(defender_side), "monster", target)
            self.destroy(defender_side, target)
            self.card_react("destroy", target, defender_side, attacker_side, {"anchor": target_anchor, "cause": "battle", "destroyed_by": attacker.card.id})
            damage = attack_value - target_value if target_in_attack else 0
            if damage:
                defender_side.hp = max(0, defender_side.hp - damage)
                self.emit_event("damage", attacker_side, source=attacker, target=defender_side, metadata={"amount": damage, "source": "battle", "direct": False, "defeated": target.card.id})
            self.log(f"{attacker.card.name} defeats {target.card.name}" + (f" for {damage} damage." if damage else "."))
            if damage:
                self.react("damage_dealt", attacker_side.character.id, defender_side.character.id, "opponent", metadata={"amount": damage, "target_card_id": target.card.id})
                self.react("damage_received", defender_side.character.id, attacker_side.character.id, "opponent", metadata={"amount": damage, "source_card_id": attacker.card.id, "anchor": target_anchor})
            self.card_react("hit", target, defender_side, attacker_side, {"amount": damage, "cause": "battle", "anchor": target_anchor, "destroyed": True})
        elif attack_value < target_value:
            damage = target_value - attack_value
            attacker_anchor = self.logical_anchor(self.side_key(attacker_side), "monster", attacker)
            self.destroy(attacker_side, attacker)
            self.card_react("destroy", attacker, attacker_side, defender_side, {"anchor": attacker_anchor, "cause": "battle", "destroyed_by": target.card.id})
            self.card_react("hit", attacker, attacker_side, defender_side, {"amount": damage, "cause": "battle", "anchor": attacker_anchor, "destroyed": True})
            attacker_side.hp = max(0, attacker_side.hp - damage)
            self.emit_event("damage", defender_side, source=target, target=attacker_side, metadata={"amount": damage, "source": "battle", "direct": False, "attacker": attacker.card.id})
            self.react("damage_dealt", defender_side.character.id, attacker_side.character.id, "opponent", metadata={"amount": damage, "target_card_id": attacker.card.id})
            self.react("damage_received", attacker_side.character.id, defender_side.character.id, "opponent", metadata={"amount": damage, "source_card_id": target.card.id, "anchor": attacker_anchor})
            self.log(f"{attacker.card.name} loses the battle and {attacker_side.name} takes {damage} damage.")
        elif target_in_attack:
            attacker_anchor = self.logical_anchor(self.side_key(attacker_side), "monster", attacker)
            target_anchor = self.logical_anchor(self.side_key(defender_side), "monster", target)
            self.destroy(attacker_side, attacker)
            self.destroy(defender_side, target)
            self.card_react("destroy", attacker, attacker_side, defender_side, {"anchor": attacker_anchor, "cause": "battle", "destroyed_by": target.card.id})
            self.card_react("destroy", target, defender_side, attacker_side, {"anchor": target_anchor, "cause": "battle", "destroyed_by": attacker.card.id})
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

    def advance_clock(self, seconds):
        if self.finished or self.duel_mode != "timed" or self.time_expired: return
        self.duel_elapsed = min(self.time_limit, self.duel_elapsed + max(0.0, float(seconds)))
        if self.duel_elapsed >= self.time_limit:
            self.time_expired = True
            if self.player.hp == self.opponent.hp: self.finish(None, "timed-draw")
            else:
                winner = self.player if self.player.hp > self.opponent.hp else self.opponent
                self.finish(winner, "timed-instant-win" if winner is self.player else "timed-instant-lose")

    def resolve_gamble_selection(self, card_id):
        if self.duel_mode != "gamble" or not self.finished or self.winner is None or not self.gamble_selection_pending: return False
        loser = self.other(self.winner)
        settled = self.store.settle_gamble_terms(self.winner.character.id, loser.character.id, self.gamble_state, card_id)
        if not settled: return False
        self.gamble_state = settled
        self.gamble_selection_pending = False
        self.transferred_card = settled.get("selected_card", "")
        if not self.match_recorded:
            self.store.record_duel(self.winner.character.id, loser.character.id, self.turn, self.reason, {"mode": "none"}, {"mode": "gamble", "place": self.place.id, "finisher": self.reason, "transferred_cards": list(settled.get("transferred", []))})
            self.match_recorded = True
        return True

    def _record_match(self):
        if self.match_recorded: return
        loser = self.other(self.winner) if self.winner else None
        policy = {"mode": "none"} if self.duel_mode == "gamble" else self.reward_policy
        metadata = {"mode": self.duel_mode, "place": self.place.id, "finisher": self.reason, "transferred_cards": [self.transferred_card] if self.transferred_card else []}
        self.transferred_card = self.store.record_duel(self.winner.character.id if self.winner else None, loser.character.id if loser else None, self.turn, self.reason, policy, metadata)
        self.match_recorded = True

    def check_end(self):
        if self.player.hp <= 0 and self.opponent.hp <= 0: self.finish(None, "simultaneous zero HP")
        elif self.player.hp <= 0: self.finish(self.opponent, "health")
        elif self.opponent.hp <= 0: self.finish(self.player, "health")

    def finish(self, winner, reason):
        if self.finished: return
        self.finished = True
        self.winner = winner
        self.reason = reason
        if winner is None: outcome_state = "timed_draw" if str(reason).startswith("timed-") else "post_duel_draw"
        elif str(reason).startswith("timed-"): outcome_state = "time_end_house_win" if winner is self.player else "time_end_house_lose"
        else: outcome_state = "post_duel_win" if winner is self.player else "post_duel_loss"
        self.outcome_narrator = self.store.narrator_cue(outcome_state, winner.character.id if winner else self.player.character.id, self.other(winner).character.id if winner else self.opponent.character.id, {"mode": self.duel_mode, "reason": reason, "winner": winner.character.id if winner else "", "time_end": str(reason).startswith("timed-")})
        if winner is None:
            self.react("draw_result", self.player.character.id, self.opponent.character.id, "opponent")
        else:
            self.react("instant_win" if str(reason).startswith("timed-") and winner is self.player else "instant_lose" if str(reason).startswith("timed-") else "win" if winner is self.player else "lose", winner.character.id, self.other(winner).character.id, "opponent")
        if self.duel_mode == "gamble" and winner is not None and self.gamble_state and not self.gamble_state.get("settled"):
            self.gamble_selection_pending = True
            self.gamble_state["state"] = "reveal_pending"
            self.outcome_narrator = self.store.narrator_cue("gamble_selection", winner.character.id, self.other(winner).character.id, {"mode": "gamble", "wager_count": self.gamble_state.get("wager_count", 0)})
        elif self.duel_mode == "gamble" and self.gamble_state and not self.gamble_state.get("settled"):
            self.gamble_state = self.store.return_gamble_terms(self.gamble_state)
            self._record_match()
        else:
            self._record_match()
        self.log("The duel ends in a draw." if winner is None else f"{winner.name} wins by {reason}.")

    def resolve_ai(self, card, trigger, actor=None, target=None):
        actor = actor or self.opponent
        target = target or self.other(actor)
        self.resolve(card, trigger, actor, target)

    def ai_can_summon(self, card, actor):
        if not any(value is None for value in actor.monsters): return False
        if card.card.kind in ["fusion", "ritual", "legendary"] or card.card.summon_method in ["fusion", "ritual", "legendary"]: return False
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
        known = self.known_card(actor, item)
        if owner is enemy and not known:
            score = 260 + (80 if item.position in ["set", "spell_trap"] else 0)
            if spec and any(action.get("name") in ["destroy", "banish", "send_to_graveyard", "return_to_hand"] for action in spec.actions): score += 80
            return score
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
        family = str(card.card.family).lower()
        kind = str(card.card.kind).lower()
        subtypes = {str(item).lower() for item in getattr(card.card, "subtypes", [])}
        family_weights = weights.get("family_weights", {})
        kind_weights = weights.get("card_kind_weights", {})
        subtype_weights = weights.get("subtype_weights", {})
        phase_weights = weights.get("phase_weights", {})
        relation = self.store.relationship_for(character.id, enemy.character.id)
        state_weight = float(weights.get("state_weights", {}).get(relation, 1.0))
        family_weight = float(family_weights.get(family, 0.0))
        kind_weight = float(kind_weights.get(kind, 0.0))
        subtype_weight = sum(float(subtype_weights.get(item, 0.0)) for item in subtypes)
        preferred_bonus = 120 if card.card.id in character.preferred_cards or card.card.id in character.best_cards else 0
        learned_weight = int(character.learned_cards.get(card.card.id, 0)) * float(weights.get("adaptation", 1.0))
        phase_weight = float(phase_weights.get(self.phase, 1.0))
        technique = character.technique_profile
        urgency = float(weights.get("risk_tolerance", 3.0)) if mode in ["monster", "set"] else float(weights.get("reward_value", 5.0))
        watcher_pressure = self.watcher_pressure(actor)
        hp_pressure = max(0, 8000 - actor.hp) / 800.0 if mode == "spell" else 0.0
        effect_score = 0
        for index, raw_effect in enumerate(card.card.effects):
            spec = EffectSpec.from_dict(raw_effect, card.card.id + "_effect_" + str(index))
            if not spec.validate():
                effect_score += self.declarative_effect_score(card, spec, actor, enemy)
                if spec.trigger == "flip" and mode == "set": effect_score += 500 * float(technique.get("defense", 5.0)) / 5.0
                if spec.trigger == "battle" and mode == "set": effect_score += 700 * float(technique.get("bluff", 5.0)) / 5.0
        stat_score = card.atk + card.card.stars * 40
        if mode == "set": stat_score = card.defense * (1.0 + float(technique.get("defense", 5.0)) / 20.0) + card.atk * 0.15
        if mode == "trap": stat_score = effect_score + 150 + float(technique.get("bluff", 5.0)) * 20
        if mode == "monster": stat_score += float(technique.get("aggression", 5.0)) * card.atk / 50.0
        if mode == "spell": stat_score += float(technique.get("control", 5.0)) * 20 + float(technique.get("resource", 5.0)) * 10
        bias_key = "summon_bias" if mode == "monster" else "set_bias" if mode == "set" else "activation_bias" if mode in ["spell", "trap"] else "summon_bias"
        bias = max(0.1, float(weights.get("duel", {}).get(bias_key, 1.0)))
        return (stat_score + family_weight * 100 * phase_weight * state_weight + kind_weight * 45 + subtype_weight * 30 + preferred_bonus + learned_weight * 20 + urgency * 25 + watcher_pressure * 18 + hp_pressure * 200 + effect_score) * bias

    def ai_activation_spec(self, card):
        return next((EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index)) for index, raw in enumerate(card.card.effects) if EffectSpec.from_dict(raw, card.card.id + "_effect_" + str(index)).trigger == "activate"), None)

    def ai_activation_score(self, card, actor):
        spec = self.ai_activation_spec(card)
        if not spec: return self.ai_card_score(card, "spell", actor)
        score = self.ai_card_score(card, "spell", actor)
        selector = spec.selector or self.card_selector(card, actor)
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
            elif name in ["fusion_summon", "ritual_summon"]:
                expected = "fusion" if name == "fusion_summon" else "ritual"
                targets = [item for item in legal if isinstance(item, CardInstance) and item.card.kind == expected]
                opportunities = []
                for target in targets:
                    procedure = ProcedureSpec.from_card(target)
                    selected = self.ai_procedure_selection(target, actor, procedure)
                    if selected and self.validate_procedure_materials(target, selected, actor, procedure)[0]: opportunities.append(self.ai_special_summon_score(target, actor, selected))
                score += max(opportunities, default=-100000)
            elif name == "special_summon":
                targets = [item for item in legal if isinstance(item, CardInstance) and item.card.kind == "legendary"]
                score += max((self.ai_special_summon_score(item, actor, []) for item in targets), default=0)
        if selector and selector.get("zone") == "spell_trap" and not any(self.owner_of(item) is enemy for item in legal): score -= 100000
        return score * float(actor.character.behavior_weights.get("duel", {}).get("activation_bias", 1.0))

    def ai_special_summon_score(self, card, actor, materials):
        enemy = self.other(actor)
        score = float(self.effective_atk(card, actor)) * 0.38 + float(self.effective_defense(card, actor)) * 0.12
        visible_threat = max([self.effective_atk(item, enemy) for item in enemy.monsters if item and item.face_up and self.known_card(actor, item)] or [0])
        if score > visible_threat: score += (score - visible_threat) * 0.34
        if materials: score -= sum(float(self.ai_card_score(item, "monster", actor)) for item in materials) * 0.08
        score += float(card.card.stars) * 24
        return score

    def ai_summon_score(self, card, actor):
        enemy = self.other(actor)
        attack = float(self.effective_atk(card, actor))
        defense = float(self.effective_defense(card, actor))
        visible = [item for item in enemy.monsters if item and item.face_up and self.known_card(actor, item)]
        visible_attack = max([self.effective_atk(item, enemy) for item in visible] or [0])
        winning_targets = [item for item in visible if attack > self.effective_atk(item, enemy)]
        score = attack * 0.34 + defense * 0.08 + float(card.card.stars) * 28
        if not visible:
            score += attack * 0.42 + 300
        elif winning_targets:
            score += max(attack - self.effective_atk(item, enemy) for item in winning_targets) * 0.52 + len(winning_targets) * 180
        else:
            score += max(0.0, defense - visible_attack) * 0.44 - max(0.0, visible_attack - attack) * 0.34
        if len([item for item in actor.monsters if item]) >= 4: score -= 180
        for index, raw_effect in enumerate(card.card.effects):
            spec = EffectSpec.from_dict(raw_effect, card.card.id + "_effect_" + str(index))
            if not spec.validate(): score += self.declarative_effect_score(card, spec, actor, enemy) * 0.65
        score += float(actor.character.technique_profile.get("aggression", 5.0)) * attack * 0.035
        score += float(actor.character.technique_profile.get("control", 5.0)) * max(0.0, visible_attack - attack) * 0.015
        return score

    def ai_set_score(self, card, actor):
        enemy = self.other(actor)
        defense = float(self.effective_defense(card, actor))
        attack = float(self.effective_atk(card, actor))
        visible = [item for item in enemy.monsters if item and item.face_up and self.known_card(actor, item)]
        strongest = max([self.effective_atk(item, enemy) for item in visible] or [0])
        score = defense * 0.31 + attack * 0.06
        if strongest:
            score += max(0.0, defense - strongest) * 0.55
            score += max(0.0, strongest - attack) * 0.28
        else:
            score -= attack * 0.03
        for index, raw_effect in enumerate(card.card.effects):
            spec = EffectSpec.from_dict(raw_effect, card.card.id + "_effect_" + str(index))
            if not spec.validate() and spec.trigger in ["flip", "battle", "summon"]: score += self.declarative_effect_score(card, spec, actor, enemy) * 0.75
        score += float(actor.character.technique_profile.get("defense", 5.0)) * defense * 0.04
        return score

    def ai_can_activate(self, card, actor):
        if card not in actor.hand or card.card.kind not in ["spell", "field"] or card.card.timing not in ["main", "any"]: return False
        spec = self.ai_activation_spec(card)
        selector = spec.selector if spec and spec.selector else self.card_selector(card, actor)
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
            for card in actor.hand:
                if card.card.kind in ["normal", "effect"] and self.ai_can_summon(card, actor):
                    actions.append({"kind": "summon", "card": card, "score": self.ai_summon_score(card, actor)})
        if self.normal_summon_remaining(actor) > 0 and any(value is None for value in actor.monsters):
            for card in actor.hand:
                if card.card.kind in ["normal", "effect"] and self.ai_can_summon(card, actor):
                    actions.append({"kind": "set", "card": card, "score": self.ai_set_score(card, actor)})
        for card in actor.hand:
            if card.card.kind in ["spell", "field"] and self.ai_can_activate(card, actor):
                actions.append({"kind": "activate", "card": card, "score": self.ai_activation_score(card, actor)})
            elif card.card.kind == "trap" and any(value is None for value in actor.spells):
                actions.append({"kind": "set", "card": card, "score": self.ai_card_score(card, "trap", actor) + float(actor.character.technique_profile.get("bluff", 5.0)) * 18})
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
        target_known = self.known_card(actor, target)
        target_value = self.battle_value(target, defender) if target_known else 1500.0 + float(actor.character.cognition.get("uncertainty", 5.0)) * 40.0
        score = 0
        if target.battle_position == "attack":
            score += (attack_value - target_value) * 4
            if attack_value > target_value: score += 900
            elif attack_value < target_value: score -= 900
        else:
            score += 240 if attack_value > target_value else -180
        if not target.face_up:
            score += 80 if target_known else -float(actor.character.technique_profile.get("risk", 5.0)) * 25
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
        self.observe_visible_information(self.player)
        self.observe_visible_information(self.opponent)
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
        self.current = DuelEngine(self.store, player.id, opponent.id, self.place_id, self.starter != "player", player_effect, opponent_effect, first_side="player" if self.starter == "player" else "opponent", reward_policy={"mode": "none"})
        self.log(f"{self.format_name} round {self.round}: {player.name} vs {opponent.name}.")
        if player_effect: self.log(f"{self.player_team.name} effect: {player_effect.get('kind')}.")
        if opponent_effect: self.log(f"{self.opponent_team.name} effect: {opponent_effect.get('kind')}.")

    def step(self):
        if self.finished or not self.current: return
        if self.current.finished:
            winner_id = self.current.winner.character.id if self.current.winner else "draw"
            loser_id = self.current.other(self.current.winner).character.id if self.current.winner else ""
            self.results.append({"round": self.round, "winner": winner_id, "loser": loser_id, "reason": self.current.reason})
            self.log(f"Round {self.round} result: {winner_id} by {self.current.reason}.")
            if self.round >= 3:
                player_wins = sum(1 for result in self.results if result["winner"] in self.player_team.members)
                opponent_wins = sum(1 for result in self.results if result["winner"] in self.opponent_team.members)
                self.finish(self.player_team if player_wins > opponent_wins else self.opponent_team if opponent_wins > player_wins else None, "three rounds complete")
            else:
                self.round += 1
                self.start_round()
            return
        actors = [self.current.active, self.current.other(self.current.active)]
        for actor in actors:
            result = self.current.autonomous_step(actor)
            if result != "waiting": return
        if not self.current.pending_discard and not self.current.pending_target and not self.current.pending_effect and not self.current.pending_response and not self.current.pending_trap and not self.current.chain_window: self.current.advance()

    def finish(self, winner, reason):
        self.finished = True
        self.winner = winner
        result = {"winner": winner.id if winner else "", "loser": "", "winning_member": "", "losing_member": "", "format": self.format_name, "place": self.place_id, "reason": reason, "rounds": list(self.results), "transferred_cards": [], "sim_time": float(self.store.world.get("simulation_time", 0.0))}
        if winner is not None:
            losing_team = self.opponent_team if winner is self.player_team else self.player_team
            result["loser"] = losing_team.id
            result["winning_member"] = ""
            result["losing_member"] = ""
            for round_result in reversed(self.results):
                if not result["winning_member"] and round_result.get("winner", "") in winner.members:
                    result["winning_member"] = round_result.get("winner", "")
                    if round_result.get("loser", "") in losing_team.members: result["losing_member"] = round_result.get("loser", "")
                if result["winning_member"] and result["losing_member"]: break
            if result["winning_member"] and result["losing_member"]:
                result["transferred_cards"] = self.store.transfer_duel_reward(result["winning_member"], result["losing_member"], {"mode": "random", "source": "library", "count": 1}, int(self.store.world.get("duel_sequence", 0)) + 1)
        self.store.record_history("team", self.player_team.id, "team_duel_completed", result)
        self.store.record_history("team", self.opponent_team.id, "team_duel_completed", result)
        if result["winning_member"]: self.store.record_history("character", result["winning_member"], "team_duel_completed", result)
        if result["losing_member"]: self.store.record_history("character", result["losing_member"], "team_duel_completed", result)
        if self.place_id in self.store.places: self.store.record_history("place", self.place_id, "team_duel_completed", result)
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
        if background is None: background = self.app.assets.image("menu/anchor", (W, H)) or self.app.assets.critical_image((W, H))
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
        self.portrait = TextInput((238, 278, 324, 36), "")
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
        ui_blit(surface, self.app.assets.image("menu/splash/1", (W, H)) or self.app.assets.critical_image((W, H)), (0, 0))
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
        elif tab == "championship": self.utility_button.label, self.utility_button.callback = "HOST LEVEL", lambda: self.select_opponent("host", 1)
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
            self.items = [(entry.get("title", "Order"), entry.get("taker", ""), entry.get("reward", {}).get("label", entry.get("reward_policy", "random")), 5, 7, entry.get("id")) for entry in self.app.store.world.get("orders", []) if entry.get("status") == "open"]
        elif self.tab == "championship":
            self.items = [(f"Level {level} championship", "host", "hostable" if self.app.store.championship_host_eligible(self.app.store.role_config()["player_character"], level) else "not qualified", level, 0, level) for level in range(1, 6)]
            for championship in self.app.store.world.get("championships", []):
                self.items.append((f"{championship.get('difficulty', 'level')} championship", "championship", championship.get("state", "waiting"), championship.get("level", 1), len(championship.get("enrolled", [])), championship.get("id")))
        else:
            roles = self.app.store.role_config()
            player_name = self.app.store.characters[roles["player_character"]].name
            opponent_name = self.app.store.characters[roles["default_opponent_character"]].name
            self.items = [(f"Live duel: {opponent_name} vs {player_name}", "watch", "active", 8, 10, None), ("Archived duel: authored showcase", "watch", "history", 5, 7, None)]
        self.buttons = list(self.nav_buttons) + [self.utility_button, self.format_button]
        self.request_button_indices = []
        for index, item in enumerate(self.items):
            target = item[1]
            action = "WATCH" if self.tab == "watch" else "ACCEPT" if self.tab == "requests" else "TAKE" if self.tab == "orders" else "HOST" if self.tab == "championship" and target == "host" else "VIEW" if self.tab == "championship" else "DUEL"
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
            status_text = f"Status: {relation}   |   Star level: {stars}   |   Smartness: {smartness}/10"
            if self.tab == "orders": status_text = "Reward: " + str(relation)
            draw_text(surface, status_text, (82, y + 42), self.app.assets.font(12), COLORS["muted"])
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
        if self.tab == "orders":
            self.app.push(DuelOrderScene(self.app))
            return
        if self.tab in ["free", "requests"]:
            self.app.store.add_request(roles["player_character"], roles["default_opponent_character"], "friendly duel", kind="duel", format_name="1v1", preferred_place=roles["default_place"], relationship_intent="stranger")
        self.refresh_content()

    def select_opponent(self, target, entry_id=None):
        if self.tab == "championship" and entry_id:
            player_id = self.app.store.role_config()["player_character"]
            if target == "host":
                championship = self.app.store.create_championship(int(entry_id), [], player_id)
                self.app.notify(f"Level {entry_id} championship opened for real-time enrollment." if championship else f"The player host is not qualified for level {entry_id}.")
            elif target == "championship":
                watched = self.app.store.watch_championship(entry_id, player_id)
                self.app.notify("Championship observation registered." if watched else "That championship is no longer available.")
            self.refresh_content()
            return
        if self.tab == "requests" and entry_id:
            decision = "ignore" if target == "ignore" else "cancel" if target == "cancel" else "accept"
            if self.app.store.respond_request(entry_id, self.app.store.role_config()["player_character"], decision):
                self.app.notify("Request moved to " + ("the real-time queue." if decision == "accept" else decision + "."))
            self.refresh_content()
            return
        if self.tab == "orders" and entry_id:
            if not self.app.store.respond_order(entry_id, self.app.store.role_config()["player_character"], "accept"):
                self.app.notify("That order could not be converted into a duel request.")
                self.refresh_content()
                return
            self.app.notify("Order accepted and converted into a real duel request.")
            self.refresh_content()
            return
        if target == "watch": self.app.push(WatchScene(self.app))
        elif self.tab == "free": self.app.push(PreDuelScene(self.app, target, self.duel_format))
        else: self.app.push(PreDuelScene(self.app, target))


class DuelOrderScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        roles = app.store.role_config()
        self.placer_id = roles["player_character"]
        character = app.store.characters.get(self.placer_id)
        owned_decks = {character.deck_id} if character and character.deck_id else set()
        owned_decks.update(deck_id for deck_id, deck in app.store.decks.items() if isinstance(deck, dict) and deck.get("owner_id") == self.placer_id)
        self.deck_ids = sorted(deck_id for deck_id in owned_decks if deck_id in app.store.decks)
        self.deck_index = 0
        preferred_places = list(app.store.characters.get(self.placer_id).preferred_places if self.placer_id in app.store.characters else [])
        self.place_ids = list(dict.fromkeys(preferred_places + sorted(app.store.places)))
        self.place_index = 0
        self.reward_modes = ["random library", "random deck", "named card", "no card"]
        self.reward_index = 0
        character = app.store.characters.get(self.placer_id)
        self.card_ids = list(dict.fromkeys((character.best_cards if character else []) + (character.library_cards if character else [])))
        self.card_ids = [card_id for card_id in self.card_ids if card_id in app.store.cards]
        self.card_index = 0
        self.taker_ids = [""] + sorted(item.id for item in app.store.characters.values() if item.id != self.placer_id)
        self.taker_index = 0
        self.duel_modes = ["current", "timed", "gamble"]
        self.duel_mode_index = 0
        self.time_limit = 180.0
        self.wager_count = 1

    def enter(self):
        self.buttons = [Button((54, 430, 160, 34), "MODE: CURRENT", lambda: self.cycle_mode(), COLORS["orange"]), Button((224, 430, 160, 34), "TIME / WAGER", lambda: self.cycle_mode_term(), COLORS["orange"]), Button((394, 430, 150, 34), "DECK", lambda: self.cycle_deck(), COLORS["cyan"]), Button((554, 430, 150, 34), "PLACE", lambda: self.cycle_place(), COLORS["green"]), Button((54, 476, 132, 38), "REWARD", lambda: self.cycle_reward(), COLORS["gold"]), Button((194, 476, 132, 38), "CARD", lambda: self.cycle_card(), COLORS["violet"]), Button((334, 476, 132, 38), "TARGET", lambda: self.cycle_taker(), COLORS["red"]), Button((286, 526, 228, 40), "PUBLISH ORDER", lambda: self.publish(), COLORS["cyan"]), Button((650, 526, 110, 40), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def cycle_mode(self):
        self.duel_mode_index = (self.duel_mode_index + 1) % len(self.duel_modes)
        self.buttons[0].label = "MODE: " + self.duel_modes[self.duel_mode_index].upper()

    def cycle_mode_term(self):
        mode = self.duel_modes[self.duel_mode_index]
        if mode == "timed": self.time_limit = 60.0 if self.time_limit >= 180.0 else self.time_limit + 60.0
        elif mode == "gamble": self.wager_count = 1 if self.wager_count >= 10 else self.wager_count + 1
        else: self.time_limit, self.wager_count = 180.0, 1

    def selected_mode(self):
        return self.duel_modes[self.duel_mode_index]

    def cycle_deck(self):
        if self.deck_ids: self.deck_index = (self.deck_index + 1) % len(self.deck_ids)

    def cycle_place(self):
        if self.place_ids: self.place_index = (self.place_index + 1) % len(self.place_ids)

    def cycle_reward(self):
        self.reward_index = (self.reward_index + 1) % len(self.reward_modes)

    def cycle_card(self):
        if self.card_ids: self.card_index = (self.card_index + 1) % len(self.card_ids)

    def cycle_taker(self):
        self.taker_index = (self.taker_index + 1) % len(self.taker_ids)

    def selected_deck(self):
        return self.deck_ids[self.deck_index] if self.deck_ids else ""

    def selected_place(self):
        return self.place_ids[self.place_index] if self.place_ids else self.app.store.role_config()["default_place"]

    def selected_taker(self):
        return self.taker_ids[self.taker_index] if self.taker_ids else ""

    def reward_policy(self):
        mode = self.reward_modes[self.reward_index]
        if mode == "random deck": return {"mode": "random", "source": "deck", "count": 1, "giver_id": self.placer_id, "trigger": "placer_loss", "label": "one random card from the order placer deck if the placer loses"}
        if mode == "named card" and self.card_ids: return {"mode": "preset", "source": "library", "card_ids": [self.card_ids[self.card_index]], "count": 1, "giver_id": self.placer_id, "trigger": "placer_loss", "label": "the selected card if the order placer loses and owns it"}
        if mode == "no card": return {"mode": "none", "source": "library", "count": 0, "giver_id": self.placer_id, "trigger": "placer_loss", "label": "no card transfer"}
        return {"mode": "random", "source": "library", "count": 1, "giver_id": self.placer_id, "trigger": "placer_loss", "label": "one random card from the order placer library if the placer loses"}

    def publish(self):
        deck_id = self.selected_deck()
        place_id = self.selected_place()
        target_id = self.selected_taker()
        order_id = self.app.store.place_order(self.placer_id, target_id, "duel order", deck_id=deck_id, preferred_deck_id=deck_id, place_id=place_id, reward=self.reward_policy(), duel_mode=self.selected_mode(), time_limit=self.time_limit, wager_count=self.wager_count if self.selected_mode() == "gamble" else 0)
        if order_id:
            self.app.notify("Duel order published with a " + self.reward_policy()["label"] + ".")
            self.app.pop()

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        self.draw_panel(surface, (42, 40, 716, 492), "DUEL ORDER COMPOSER", COLORS["gold"])
        character = self.app.store.characters.get(self.placer_id)
        draw_text(surface, "Order placer: " + (character.name if character else self.placer_id), (70, 102), self.app.assets.font(18, True), COLORS["cream"])
        deck_id = self.selected_deck()
        deck = self.app.store.decks.get(deck_id, {}) if deck_id else {}
        draw_text(surface, "Preset deck: " + (str(deck.get("name", deck_id)) if isinstance(deck, dict) else deck_id or "automatic"), (70, 145), self.app.assets.font(13), COLORS["cyan"])
        draw_text(surface, "Duel place: " + (self.app.store.places.get(self.selected_place()).name if self.selected_place() in self.app.store.places else "default"), (70, 175), self.app.assets.font(13), COLORS["green"])
        draw_text(surface, "Reward on loss: " + self.reward_policy()["label"], (70, 205), self.app.assets.font(13), COLORS["gold"])
        selected_card = self.app.store.cards.get(self.card_ids[self.card_index]) if self.card_ids else None
        draw_text(surface, "Named card: " + (selected_card.name if selected_card else "none selected"), (70, 235), self.app.assets.font(13), COLORS["violet"])
        taker = self.app.store.characters.get(self.selected_taker()) if self.selected_taker() else None
        draw_text(surface, "Target: " + (taker.name if taker else "any compatible character"), (70, 265), self.app.assets.font(13), COLORS["red"])
        mode = self.selected_mode()
        term = "3:00 limit; lower LP wins, equal LP draws" if mode == "timed" else str(self.wager_count) + " cards per side; winner selects one loser card" if mode == "gamble" else "no clock; standard completion"
        draw_text(surface, "Duel mode: " + mode.upper() + "  |  " + term, (400, 300), self.app.assets.font(12, True), COLORS["orange"], "center")
        draw_text(surface, "The loser supplies the configured reward only if the duel completes with a winner.", (400, 330), self.app.assets.font(12), COLORS["muted"], "center")
        draw_text(surface, "Random deck/library choices are resolved from real owned cards; named choices fail safely when unavailable.", (400, 360), self.app.assets.font(10), COLORS["muted"], "center")
        self.draw_buttons(surface, 11)


class PreDuelScene(Scene):
    def __init__(self, app, opponent_id, format_name="1v1", place_id=None, duel_mode="current", time_limit=180.0, duel_terms=None):
        super().__init__(app)
        self.opponent_id = opponent_id
        self.format_name = format_name
        self.place_id = place_id or app.store.role_config()["default_place"]
        self.duel_mode = duel_mode if duel_mode in DUEL_MODES else "current"
        self.time_limit = float(time_limit or 180.0)
        self.duel_terms = dict(duel_terms or {})
        self.requester_id = opponent_id
        self.acceptor_id = app.store.role_config()["player_character"]
        self.requested_first_side = "opponent"
        self.dice_launcher_id = self.acceptor_id
        self.choice = ""
        self.decision = "request_first"
        self.dice_value = None
        self.dice_owner = ""
        self.dice_clock = 0.0
        self.dice_rolling = False
        self.dice_roll_value = 1
        self.dice_roll_count = 0
        self.dice_result_delay = 0.0
        self.dice_rng = random.Random(time.time_ns() ^ sum(ord(char) for char in str(opponent_id)))
        self.narrator_text = ""
        self.narrator_audio = ""
        self.narrator_state = ""
        self.interaction_sequence = 0
        self.elapsed = 0.0

    def enter(self):
        self.buttons = [Button((90, 496, 180, 44), "ACCEPT FIRST", lambda: self.accept_first(), COLORS["cyan"]), Button((290, 496, 180, 44), "SPIN DICE", lambda: self.deny_first(), COLORS["gold"]), Button((490, 496, 120, 44), "BACK", lambda: self.cancel(), COLORS["muted"]), Button((270, 448, 260, 30), "MODE: " + self.duel_mode.upper(), lambda: self.cycle_mode(), COLORS["orange"])]
        self.app.assets.play_duel_music(self.place_id, self.app.store.save_data.get("music", True), 0.35, self.app.store.clock.period(float(self.app.store.world.get("simulation_time", 0.0))) == "night", "pre-duel")
        self.narrate("request_first")

    def cycle_mode(self):
        if self.format_name != "1v1" or self.decision != "request_first": return
        self.duel_mode = DUEL_MODES[(DUEL_MODES.index(self.duel_mode) + 1) % len(DUEL_MODES)]
        self.time_limit = 180.0 if self.duel_mode == "timed" else 0.0
        if self.buttons: self.buttons[-1].label = "MODE: " + self.duel_mode.upper()

    def narrate(self, state):
        cue = self.app.store.narrator_cue(state, self.requester_id, self.acceptor_id, {"format": self.format_name, "launcher": self.dice_launcher_id, "value": self.dice_value or 0})
        self.narrator_state = cue["state"]
        self.narrator_text = cue["text"]
        self.narrator_audio = cue.get("audio", "")
        if self.narrator_audio and self.app.store.save_data.get("vocals", True): self.app.assets.play_reaction_audio(self.narrator_audio, True, 0.8, "narrator")
        return cue

    def record_decision(self, mode):
        self.interaction_sequence += 1
        event = {"type": "first_play_decision", "sequence": self.interaction_sequence, "mode": mode, "requester": self.requester_id, "acceptor": self.acceptor_id, "launcher": self.dice_launcher_id, "first": self.choice, "value": self.dice_value, "sim_time": float(self.app.store.world.get("simulation_time", 0.0)), "time": time.time()}
        self.app.store.world.setdefault("simulation_events", []).append(event)
        self.app.store.save()
        return event

    def cancel(self):
        if self.decision in ["request_first", "dice_intro", "rolling", "result"]:
            self.decision = "canceled"
            self.record_decision("canceled")
        self.app.pop()

    def accept_first(self):
        if self.decision != "request_first": return
        self.choice = "opponent"
        self.decision = "accepted"
        self.narrate("ready")
        self.record_decision("accepted")
        self.launch()

    def deny_first(self):
        if self.decision != "request_first": return
        self.decision = "rolling"
        self.app.assets.play_duel_music(self.place_id, self.app.store.save_data.get("music", True), 0.35, self.app.store.clock.period(float(self.app.store.world.get("simulation_time", 0.0))) == "night", "spin-dice")
        self.dice_rolling = True
        self.dice_clock = 0.0
        self.dice_result_delay = 0.0
        self.dice_value = None
        self.dice_roll_value = self.dice_rng.randint(1, 6)
        result = self.app.store.spin_dice_result(self.dice_launcher_id, self.requester_id)
        self.final_dice_value = result["value"]
        self.final_dice_side = result["first"]
        self.dice_roll_count = 0
        self.dice_owner = self.dice_launcher_id
        self.narrate("dice_intro")
        self.buttons = [Button((650, 530, 110, 38), "CANCEL", lambda: self.cancel(), COLORS["muted"])]

    def roll_result(self):
        self.dice_value = self.final_dice_value
        self.dice_roll_value = self.dice_value
        self.choice = "player" if self.dice_value <= 3 else "opponent"
        self.final_dice_side = self.acceptor_id if self.choice == "player" else self.requester_id
        self.decision = "result"
        self.dice_rolling = False
        self.dice_result_delay = 0.0
        self.narrate("result_launcher" if self.dice_value <= 3 else "result_requester")
        self.record_decision("dice")
        self.app.notify(f"Dice result {self.dice_value}: {self.choice} goes first.")
        self.buttons = [Button((170, 496, 180, 44), "START DUEL", lambda: self.launch(), COLORS["cyan"]), Button((650, 530, 110, 38), "CANCEL", lambda: self.cancel(), COLORS["muted"])]

    def launch(self):
        if self.decision not in ["accepted", "ready", "result"]: return
        place_id = self.place_id
        place = self.app.store.places[place_id]
        terms = self.app.store.normalize_duel_terms(self.format_name, self.duel_mode, self.time_limit, 1 if self.duel_mode == "gamble" else 0)
        if not self.app.store.reserve_place(place_id):
            self.app.notify(place.name + " is full. This duel must wait or choose another place.")
            return
        starter = self.choice or "player"
        if self.format_name == "1v1": self.app.push(DuelScene(self.app, self.opponent_id, starter, place_id, True, None, None, self.duel_mode, self.time_limit, terms))
        else: self.app.push(TeamDuelScene(self.app, self.format_name, self.opponent_id, starter, True))

    def update(self, dt):
        self.elapsed += dt
        if self.dice_rolling:
            self.dice_clock += dt
            while self.dice_clock >= 0.09:
                self.dice_clock -= 0.09
                self.dice_roll_value = self.dice_rng.randint(1, 6)
                self.dice_roll_count += 1
            if self.dice_roll_count >= 18: self.roll_result()
        elif self.decision == "result":
            self.dice_result_delay += dt
            if self.dice_result_delay >= 0.65:
                self.decision = "ready"
                self.narrate("ready")

    def draw_dice(self, surface):
        if not self.dice_rolling and not self.dice_value: return
        value = self.dice_roll_value if self.dice_rolling else self.dice_value
        image = self.app.assets.dice_face(value, (144, 144))
        if image:
            angle = math.sin(self.elapsed * 32.0) * 13.0 if self.dice_rolling else 0.0
            bounce = math.sin(self.elapsed * 27.0) * 18.0 if self.dice_rolling else 0.0
            rotated = pygame.transform.rotozoom(image, angle, 1.0)
            rect = rotated.get_rect(center=(400, int(320 + bounce)))
            ui_blit(surface, rotated, rect.topleft)
        else:
            rounded(surface, (328, 248, 144, 144), (238, 241, 252), COLORS["gold"], 18, 4)
            draw_text(surface, str(value), (400, 320), self.app.assets.font(48, True), COLORS["ink"], "center")

    def draw(self, surface):
        place = self.app.store.places[self.place_id]
        night = self.app.store.clock.period(float(self.app.store.world.get("simulation_time", 0.0))) == "night"
        background = self.app.assets.place_visual(self.place_id, "pre_duel", night, self.elapsed, (W, H), "pre-duel") or self.app.assets.image(place.background, (W, H))
        if background: ui_blit(surface, background, (0, 0))
        else: surface.fill(COLORS["deep"])
        veil = ui_surface((W, H), pygame.SRCALPHA)
        veil.fill((247, 227, 177, 36))
        ui_blit(surface, veil, (0, 0))
        roles = self.app.store.role_config()
        player = self.app.store.characters[roles["player_character"]]
        rival = self.app.store.characters.get(self.opponent_id, self.app.store.characters[roles["default_opponent_character"]])
        self.draw_panel(surface, (54, 74, 692, 375), "PRE-DUEL  |  " + self.format_name, COLORS["gold"])
        draw_text(surface, place.name, (400, 115), self.app.assets.font(17, True), COLORS["cyan"], "center")
        mode_label = self.duel_mode.upper() if self.format_name == "1v1" else "CURRENT"
        mode_detail = "3:00 limit; lower LP wins; equal LP draws" if self.duel_mode == "timed" else "both sides wager one or more cards; winner selects one" if self.duel_mode == "gamble" else "standard LP duel; loser-to-winner reward terms apply"
        draw_text(surface, "DUEL MODE: " + mode_label, (400, 132), self.app.assets.font(10, True), COLORS["orange"], "center")
        draw_text(surface, mode_detail, (400, 146), self.app.assets.font(9), COLORS["muted"], "center")
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
        if self.decision == "request_first":
            draw_text(surface, f"{requester_name} requests the first move. {acceptor_name} may accept or spin the dice.", (400, 388), self.app.assets.font(11), COLORS["muted"], "center")
        elif self.decision == "rolling":
            draw_text(surface, f"Spin-Dicer: {acceptor_name} launched the roll. Faces 1–3 belong to the launcher; faces 4–6 belong to {requester_name}.", (400, 388), self.app.assets.font(10), COLORS["gold"], "center")
            self.draw_dice(surface)
        elif self.decision in ["result", "ready", "accepted"]:
            first_name = acceptor_name if self.choice == "player" else requester_name
            draw_text(surface, f"Dice result {self.dice_value}: {first_name} goes first.", (400, 388), self.app.assets.font(12, True), COLORS["gold"], "center")
            self.draw_dice(surface)
        if self.narrator_text:
            rounded(surface, (110, 414, 580, 30), (35, 28, 52, 210), COLORS["gold"], 8, 1)
            narrator_line = wrap(self.app.assets.font(9), "NARRATOR: " + self.narrator_text, 550)[0]
            draw_text(surface, narrator_line, (400, 429), self.app.assets.font(9), COLORS["cream"], "center")
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
        image = self.app.assets.character_portrait(char, (92, 92))
        if image: ui_blit(surface, image, (x + 59, y + 14))
        draw_text(surface, char.name, (x + 105, y + 123), self.app.assets.font(17, True), COLORS["cream"], "center")
        draw_text(surface, f"{char.stars} stars  |  {char.mood}", (x + 105, y + 150), self.app.assets.font(12), accent, "center")
        draw_text(surface, ", ".join(char.preferred_families), (x + 105, y + 171), self.app.assets.font(11), COLORS["muted"], "center")



class DuelScene(Scene):
    def __init__(self, app, opponent_id=None, starter="player", place_id=None, reserved=False, spectator_battle=None, spectator_engine=None, duel_mode="current", time_limit=180.0, duel_terms=None):
        super().__init__(app)
        roles = app.store.role_config()
        place_id = place_id or roles["default_place"]
        self.spectator = bool(spectator_battle)
        self.watched_battle = spectator_battle or {}
        self.watcher_id = ""
        if spectator_engine:
            self.engine = spectator_engine
        elif self.spectator:
            house_id = self.watched_battle.get("house") or self.watched_battle.get("accepted_by") or self.watched_battle.get("to") or self.watched_battle.get("from")
            guest_id = self.watched_battle.get("guest") or (self.watched_battle.get("to") if house_id == self.watched_battle.get("from") else self.watched_battle.get("from"))
            self.engine = app.store._world_session(self.watched_battle) or DuelEngine(app.store, house_id, guest_id, place_id, True)
        else:
            self.engine = DuelEngine(app.store, roles["player_character"], opponent_id, place_id, starter == "opponent", first_side=starter, duel_mode=duel_mode, time_limit=time_limit, duel_terms=duel_terms)
        self.layout = DuelLayout()
        self.place_id = place_id
        if self.spectator:
            watcher_id = roles["player_character"]
            if app.store.add_battle_watcher(self.watched_battle.get("id", ""), watcher_id): self.watcher_id = watcher_id
        self.place_reserved = reserved
        self.reaction_player = ReactionPlayer()
        self.media_scope = "duel_scene_" + str(id(self))
        self.music_state = ""
        self.reaction_seen = 0
        self.reaction_queue = []
        self.attack_presentation = None
        self.attack_preview_clock = 0.0
        self.last_pointer = (400, 300)
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
        self.watcher_media = {}
        self.watcher_seen = set()
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
        self.gamble_rects = []
        self.idle_elapsed = 0.0
        self.idle_observation = self.engine.observation_sequence
        self.idle_cue_count = 0

    def dispatch_idle_narrator(self, dt):
        current_observation = self.engine.observation_sequence
        if current_observation != self.idle_observation:
            self.idle_observation = current_observation
            self.idle_elapsed = 0.0
            return
        if self.engine.finished: return
        self.idle_elapsed += max(0.0, float(dt))
        threshold = float(self.app.store.rules.get("narrator", {}).get("idle_seconds", {}).get("duel", 45.0) or 45.0)
        while self.idle_elapsed >= threshold:
            self.idle_elapsed -= threshold
            self.idle_cue_count += 1
            self.app.store.narrator_cue("duel_idle", self.engine.player.character.id, self.engine.opponent.character.id, {"cadence": self.idle_cue_count, "spectator": self.spectator, "duel_mode": self.engine.duel_mode})

    def enter(self):
        super().enter()
        self.app.assets.media_scopes.setdefault(self.media_scope, set())
        self.sync_duel_music()
        if self.spectator:
            self.reaction_seen = len(self.engine.reaction_events)
            self.buttons = [Button((650, 530, 110, 38), "EXIT WATCH", lambda: self.app.pop(), COLORS["muted"])]

    def leave(self):
        if pygame.mixer.get_init():
            try: pygame.mixer.stop()
            except pygame.error: pass
        self.app.assets.release_media_scope(self.media_scope)
        if self.spectator and self.watcher_id: self.app.store.remove_battle_watcher(self.watched_battle.get("id", ""), self.watcher_id)
        self.reaction_player.selection = None
        self.reaction_player.finished = True
        self.reaction_queue.clear()
        self.attack_presentation = None
        self.attack_preview_clock = 0.0

    def sync_duel_music(self):
        if self.engine.finished:
            state = "post-duel-draw" if self.engine.winner is None else "post-duel-win" if self.engine.winner is self.engine.player else "post-duel-lose"
        elif self.engine.opponent.hp <= 2000:
            state = "near-win"
        elif self.engine.player.hp <= 2000:
            state = "near-lose"
        else:
            state = "duel"
        if state == self.music_state: return
        self.music_state = state
        self.app.assets.play_duel_music(self.place_id, self.app.store.save_data.get("music", True), 0.35, self.app.store.clock.period(float(self.app.store.world.get("simulation_time", 0.0))) == "night", state)

    def handle(self, event):
        if self.spectator:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: self.app.pop(); return
            super().handle(event)
            return
        if event.type == pygame.MOUSEMOTION:
            self.last_pointer = event.pos
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
        if self.engine.gamble_selection_pending and event.button == 1:
            for rect, card_id in self.gamble_rects:
                if rect.collidepoint(event.pos):
                    if self.engine.resolve_gamble_selection(card_id): self.message = "Gamble card selected and all wager cards revealed."
                    return
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
                self.attack_preview_clock = 0.0
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

    def sync_watcher_media(self):
        watcher_ids = list(self.watched_battle.get("watchers", [])) if self.spectator else list(getattr(self.engine, "watcher_ids", []))
        house_id = self.engine.player.character.id
        for watcher_id in watcher_ids[:6]:
            if watcher_id not in self.app.store.characters: continue
            if watcher_id not in self.watcher_media:
                relation = self.app.store.relationship_for(watcher_id, house_id)
                selection = self.app.store.media.resolve("watching_in", watcher_id, house_id, relation, "characters", watcher_id, self.place_id, "loop", metadata={"watcher": True})
                self.watcher_media[watcher_id] = selection
                self.watcher_seen.add(watcher_id)
                if selection.audio and self.app.store.save_data.get("vocals", True): self.app.assets.play_reaction_audio(selection.audio, True, 0.7, self.media_scope)
        for watcher_id in list(self.watcher_media):
            if watcher_id not in watcher_ids: self.watcher_media.pop(watcher_id, None)

    def start_reaction(self, record):
        selection = ReactionSelection.from_dict(record.get("selection", {}))
        self.reaction_player.start(selection)
        self.attack_presentation = dict(selection.presentation) if selection.presentation else None
        enabled = bool(self.app.store.save_data.get("vocals", True))
        if selection.audio: self.app.assets.play_reaction_audio(selection.audio, enabled, 0.8, self.media_scope)

    def update(self, dt):
        super().update(dt)
        if not self.spectator: self.engine.advance_clock(dt)
        if not self.spectator and self.engine.gamble_selection_pending and self.engine.winner is not self.engine.player:
            selected = self.app.store.choose_ai_gamble_card(self.engine.winner.character.id, self.engine.other(self.engine.winner).character.id, self.engine.gamble_state)
            self.engine.resolve_gamble_selection(selected)
        if self.spectator:
            self.app.store.advance_world(dt)
            session = self.app.store._world_session(self.watched_battle)
            if session: self.engine = session
            while self.reaction_seen < len(self.engine.reaction_events):
                self.reaction_queue.append(self.engine.reaction_events[self.reaction_seen])
                self.reaction_seen += 1
            if self.reaction_player.finished and self.reaction_queue: self.start_reaction(self.reaction_queue.pop(0))
            self.reaction_player.update(dt)
            if self.attack_presentation and self.reaction_player.finished: self.attack_presentation = None
            self.sync_watcher_media()
            self.sync_duel_music()
            return
        self.dispatch_idle_narrator(dt)
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
        while self.reaction_seen < len(self.engine.reaction_events):
            self.reaction_queue.append(self.engine.reaction_events[self.reaction_seen])
            self.reaction_seen += 1
        if self.reaction_player.finished and self.reaction_queue: self.start_reaction(self.reaction_queue.pop(0))
        self.reaction_player.update(dt)
        if self.attack_presentation and self.reaction_player.finished: self.attack_presentation = None
        self.sync_watcher_media()
        self.attack_preview_clock = self.attack_preview_clock + dt if self.engine.selected_monster and not self.engine.finished else 0.0
        self.sync_duel_music()
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
        self.draw_watchers(surface)
        if self.spectator:
            draw_text(surface, "LIVE HOUSE POV  |  " + self.engine.player.character.name.upper(), (400, 74), self.app.assets.font(10, True), COLORS["gold"], "center")
        self.draw_reaction(surface)
        self.draw_attack_preview(surface)
        self.draw_hand(surface)
        self.draw_interactions(surface)
        self.draw_hover_cloud(surface)
        self.draw_question(surface)
        self.draw_card_list_popup(surface)
        if self.engine.finished: self.draw_result(surface)

    def draw_watchers(self, surface):
        watcher_ids = list(self.watched_battle.get("watchers", [])) if self.spectator else list(getattr(self.engine, "watcher_ids", []))
        for index, watcher_id in enumerate(watcher_ids[:6]):
            character = self.app.store.characters.get(watcher_id)
            if not character: continue
            side = "left" if index < 3 else "right"
            column_index = index if index < 3 else index - 3
            x = 12 if side == "left" else W - 92
            y = 155 + column_index * 112
            relation = self.app.store.relationship_for(watcher_id, self.engine.player.character.id)
            accent = COLORS["gold"] if relation == "ally" else COLORS["red"] if relation == "enemy" else COLORS["line"]
            rounded(surface, (x, y, 80, 96), (18, 30, 58, 215), accent, 7, 1)
            selection = self.watcher_media.get(watcher_id)
            image = None
            if selection:
                frame_index = int(self.time * max(1.0, float(selection.frame_rate or FPS)))
                if selection.frames: image = self.app.assets.media_image(selection.frames[frame_index % len(selection.frames)], (66, 66), self.media_scope)
                elif selection.image: image = self.app.assets.media_image(selection.image, (66, 66), self.media_scope)
            if not image: image = self.app.assets.image(character.portrait, (66, 66))
            if image and side == "right": image = pygame.transform.flip(image, True, False)
            if image: ui_blit(surface, image, (x + 7, y + 6))
            draw_text(surface, character.name[:11], (x + 40, y + 76), self.app.assets.font(8, True), COLORS["cream"], "center")
            draw_text(surface, relation.upper(), (x + 40, y + 88), self.app.assets.font(7), COLORS["gold"], "center")

    def draw_duel_backdrop(self, surface):
        night = self.app.store.clock.period(float(self.app.store.world.get("simulation_time", 0.0))) == "night"
        ground = self.app.assets.place_visual(self.place_id, "ground", night, self.time, (W, H), self.media_scope) or self.app.assets.role_image("place_ground", (W, H), True) or self.app.assets.role_image("duel_environment", (W, H), True)
        if ground: ui_blit(surface, ground, (0, 0))
        else:
            place = self.app.store.places.get(self.place_id)
            image = self.app.assets.image(place.background, (W, H)) if place and place.background else None
            if image: ui_blit(surface, image, (0, 0))
        table = self.app.assets.role_image("table_frame", (646, 564), True)
        frame = self.app.assets.role_image("duel_frame", (552, 480), True)
        field_surface = self.app.assets.place_visual(self.place_id, "field", night, self.time, self.layout.field.size, self.media_scope) or self.app.assets.role_image("field_surface", self.layout.field.size, True)
        ui_blit(surface, table, self.layout.table.topleft)
        ui_blit(surface, frame, self.layout.duel_frame.topleft)
        ui_blit(surface, field_surface, self.layout.field.topleft)

    def anchor_rect(self, anchor):
        anchor = dict(anchor or {})
        side = anchor.get("side", "player")
        zone = anchor.get("zone", "monster")
        index = int(anchor.get("index", -1))
        if zone == "duelist": return self.layout.hud_rect(side)
        if zone == "monster" and 0 <= index < 5: return self.layout.monster_rect(side, index)
        if zone == "spell_trap" and 0 <= index < 5: return self.layout.spell_rect(side, index)
        return self.layout.hud_rect(side)

    def draw_attack_preview(self, surface):
        if not self.engine.selected_monster or self.engine.finished or self.engine.phase != "BATTLE": return
        source = self.monster_rect(self.engine.selected_monster, True)
        target = pygame.Vector2(self.last_pointer)
        origin = pygame.Vector2(source.centerx, source.centery + 34)
        elapsed = min(1.0, self.attack_preview_clock / 0.35)
        point = origin.lerp(target, elapsed)
        pygame.draw.line(surface, (255, 248, 228, 120), source.center, (int(point.x), int(point.y)), 2)
        vfx_path = self.app.store.media.vfx_path("attack", self.engine.selected_monster.card.id, self.engine.player.character.id)
        image = self.app.assets.media_image(vfx_path, (84, 84), self.media_scope) if vfx_path else None
        if image:
            direction = target - pygame.Vector2(source.center)
            sprite = pygame.transform.rotate(image, -math.degrees(math.atan2(direction.y, direction.x)))
            sprite.set_alpha(int(110 + 90 * elapsed))
            ui_blit(surface, sprite, sprite.get_rect(center=(int(point.x), int(point.y))))
        self.draw_cloud(surface, int(point.x), int(point.y) - 12, "Attack!")

    def draw_attack_presentation(self, surface, state):
        presentation = dict(self.attack_presentation or {})
        source = self.anchor_rect(presentation.get("source_anchor", {}))
        target = self.anchor_rect(presentation.get("target_anchor", {}))
        clock = float(state.get("clock", 0.0))
        duration = max(0.05, float(state.get("duration", 0.72)))
        progress = clamp(clock / duration, 0.0, 1.0)
        eased = progress * progress * (3.0 - 2.0 * progress)
        start = pygame.Vector2(source.centerx, source.centery + 42)
        end = pygame.Vector2(target.center)
        point = start.lerp(end, eased)
        path = state.get("image", "")
        image = self.app.assets.media_image(path, (108, 108), self.media_scope) if path else None
        if image:
            direction = end - start
            angle = -math.degrees(math.atan2(direction.y, direction.x))
            sprite = pygame.transform.rotate(image, angle)
            fade = int(255 * clamp(progress * 5.0, 0.0, 1.0) * clamp((1.0 - progress) * 5.0, 0.0, 1.0))
            sprite.set_alpha(max(40, fade))
            ui_blit(surface, sprite, sprite.get_rect(center=(int(point.x), int(point.y))))
        if progress >= 0.82:
            ui_draw_rect(surface, (255, 248, 228, int(110 * (1.0 - progress))), target.inflate(8, 8), 2, border_radius=6)

    def draw_card_reaction_fx(self, surface, state):
        selection = self.reaction_player.selection
        if not selection: return
        metadata = dict(selection.metadata or {})
        anchor = metadata.get("anchor")
        if not anchor: return
        rect = self.anchor_rect(anchor)
        event = str(state.get("event", "")).lower().replace("-", "_")
        clock = float(state.get("clock", 0.0))
        duration = max(0.05, float(state.get("duration", 0.35)))
        progress = clamp(clock / duration, 0.0, 1.0)
        if event in ["hit", "damage", "damage_dealt", "damage_received"]:
            offset = int(math.sin(clock * 78.0) * (1.0 - progress) * 6.0)
            flash = pygame.Surface(rect.size, pygame.SRCALPHA)
            flash.fill((218, 74, 65, int(85 * (1.0 - progress))))
            ui_blit(surface, flash, (rect.x + offset, rect.y))
            ui_draw_rect(surface, (255, 212, 176, int(180 * (1.0 - progress))), rect.inflate(4, 4), 2, border_radius=5)
        elif event in ["flip", "flip_reveal", "reveal"]:
            ui_draw_rect(surface, (255, 255, 255, int(150 * (1.0 - progress))), rect.inflate(6, 6), 3, border_radius=5)
        elif event in ["destroy", "destroyed", "die", "death"]:
            center = rect.center
            alpha = int(230 * (1.0 - progress))
            ui_draw_line(surface, (255, 224, 167, alpha), (rect.x, rect.y), (rect.right, rect.bottom), 3)
            ui_draw_line(surface, (255, 224, 167, alpha), (rect.right, rect.y), (rect.x, rect.bottom), 3)
            ui_draw_rect(surface, (255, 180, 90, alpha), rect.inflate(int(progress * 12), int(progress * 12)), 2, border_radius=5)
        elif event in ["return", "return_to_hand", "banish", "banished", "send_to_graveyard", "graveyard"]:
            ui_draw_rect(surface, (205, 225, 221, int(150 * (1.0 - progress))), rect.inflate(5, 5), 2, border_radius=5)
        frame_path = state.get("image", "")
        if frame_path and not state.get("placeholder") and event not in ["destroy", "destroyed", "die", "death"]:
            image = self.app.assets.media_image(frame_path, (rect.width, rect.height), self.media_scope)
            if image:
                image = image.copy()
                image.set_alpha(int(190 * (1.0 - progress)))
                ui_blit(surface, image, rect.topleft)

    def draw_reaction(self, surface):
        state = self.reaction_player.state()
        if not state.get("active"): return
        rounded(surface, (286, 78, 228, 42), (232, 218, 173), (126, 112, 73), 7, 1)
        label = state["event"].replace("_", " ").upper()
        source = "PLACEHOLDER" if state["placeholder"] else f"VARIANT {state['variant']}"
        draw_text(surface, f"REACTION  {label}", (400, 91), self.app.assets.font(9, True), COLORS["ink"], "midtop")
        draw_text(surface, source, (400, 106), self.app.assets.font(8), COLORS["muted"], "midtop")
        image_path = state.get("image")
        image = self.app.assets.media_image(image_path, (52, 32), self.media_scope) if image_path else self.app.assets.media_video_frame(state.get("video", ""), state.get("clock", 0.0), (52, 32), self.media_scope)
        if image: ui_blit(surface, image, (292, 82))
        if self.attack_presentation: self.draw_attack_presentation(surface, state)
        self.draw_card_reaction_fx(surface, state)

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
            portrait = self.app.assets.character_portrait(participant.character, pfp.size)
            if portrait: ui_blit(surface, portrait, pfp.topleft)
            draw_text(surface, "LP", (plaque.x + 64, plaque.y + 15), self.app.assets.font(7, True), COLORS["gold"], "topleft")
            draw_text(surface, f"{current:04d}", (plaque.right - 10, plaque.y + 22), self.app.assets.font(19, True), COLORS["white"], "topright")
            if self.hp_delta_until[side] > self.time and self.hp_delta[side]:
                delta = self.hp_delta[side]
                color = COLORS["blue"] if delta > 0 else COLORS["red"]
                draw_text(surface, f"{delta:+d}", (plaque.right - 12, plaque.bottom - 7), self.app.assets.font(9, True), color, "bottomright")
        if self.engine.duel_mode == "timed" and not self.engine.finished:
            remaining = max(0.0, self.engine.time_limit - self.engine.duel_elapsed)
            color = COLORS["red"] if remaining <= 30.0 else COLORS["orange"]
            draw_text(surface, f"TIME  {remaining:05.1f}", (400, 95), self.app.assets.font(13, True), color, "center")
        elif self.engine.duel_mode == "gamble" and not self.engine.finished:
            draw_text(surface, f"GAMBLE  {self.engine.gamble_state.get('wager_count', 0)} CARDS", (400, 95), self.app.assets.font(11, True), COLORS["orange"], "center")

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
                image = self.app.assets.image("placeholder/card_back")
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
        image = self.app.assets.image("placeholder/card_back") or self.app.assets.critical_image(rect.size)
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
        title = "DRAW" if self.engine.winner is None else f"{self.engine.winner.name} WINS"
        color = COLORS["gold"] if self.engine.winner is None else COLORS["cyan"] if self.engine.winner is self.engine.player else COLORS["red"]
        panel = pygame.Rect(180, 175, 440, 205) if self.engine.duel_mode != "gamble" or not self.engine.gamble_selection_pending else pygame.Rect(30, 120, 740, 410)
        rounded(surface, panel, COLORS["panel"], COLORS["gold"], 12, 2)
        draw_text(surface, "DUEL COMPLETE", (400, panel.y + 35), self.app.assets.font(24, True), COLORS["gold"], "center")
        draw_text(surface, title, (400, panel.y + 80), self.app.assets.font(25, True), color, "center")
        draw_text(surface, f"Resolution: {self.engine.reason}", (400, panel.y + 118), self.app.assets.font(13), COLORS["cream"], "center")
        if self.engine.duel_mode == "timed": draw_text(surface, "TIMED DUEL  " + ("DRAW" if self.engine.winner is None else "LOWEST LP RESOLUTION"), (400, panel.y + 145), self.app.assets.font(10, True), COLORS["orange"], "center")
        reward = self.app.store.cards[self.engine.transferred_card].name if self.engine.transferred_card in self.app.store.cards else "No card transfer"
        draw_text(surface, "Card transfer: " + reward, (400, panel.y + 145 if self.engine.duel_mode != "timed" else panel.y + 162), self.app.assets.font(11), COLORS["gold"], "center")
        narrator_text = str(self.engine.outcome_narrator.get("text", "")) if isinstance(self.engine.outcome_narrator, dict) else ""
        if narrator_text: draw_text(surface, narrator_text[:92], (400, panel.y + (198 if self.engine.duel_mode == "gamble" else 178)), self.app.assets.font(10), COLORS["cream"], "center")
        self.gamble_rects = []
        if self.engine.duel_mode == "gamble":
            status = "CARD SELECTION REQUIRED" if self.engine.gamble_selection_pending else "WAGERS SETTLED"
            draw_text(surface, "GAMBLE  |  " + status, (400, panel.y + 174), self.app.assets.font(11, True), COLORS["orange"], "center")
            if self.engine.gamble_selection_pending:
                winner_is_player = self.engine.winner is self.engine.player
                loser_id = self.engine.other(self.engine.winner).character.id
                pool = list(self.engine.gamble_state.get("pools", {}).get(loser_id, []))
                draw_text(surface, "SELECT ONE CARD FROM THE LOSER'S FACE-DOWN WAGER" if winner_is_player else "THE OPPONENT IS SELECTING ONE CARD", (400, panel.y + 220), self.app.assets.font(10, True), COLORS["cream"], "center")
                for index, card_id in enumerate(pool):
                    x = 68 + (index % 5) * 132
                    y = panel.y + 241 + (index // 5) * 74
                    rect = pygame.Rect(x, y, 82, 58)
                    if winner_is_player: self.gamble_rects.append((rect, card_id))
                    back = self.app.assets.image("placeholder/card_back")
                    if back: blit_aspect(surface, back, rect)
                    else: rounded(surface, rect, (30, 36, 66), COLORS["gold"] if winner_is_player else COLORS["line"], 5, 1)
                    draw_text(surface, "CARD " + str(index + 1), (rect.centerx, rect.bottom + 8), self.app.assets.font(8, True), COLORS["cream"], "center")
            elif self.engine.gamble_state.get("selected_card") in self.app.store.cards:
                card = self.app.store.cards[self.engine.gamble_state["selected_card"]]
                draw_text(surface, "SELECTED CARD REVEALED", (400, panel.y + 220), self.app.assets.font(10, True), COLORS["gold"], "center")
                render_engine_card(surface, (335, panel.y + 238, 130, 90), card, self.app.assets, self.app.store.media, True, False, card.art_variant, True)
        draw_text(surface, "Press Escape to return to Battle", (400, 565 if panel.height > 250 else 347), self.app.assets.font(12), COLORS["muted"], "center")


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
        draw_text(surface, "data/cards/<entity>/ and data/universal_assets/", (350, 414), self.app.assets.font(13), COLORS["cream"])
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
        return set(player.library_cards) | set(DeckRules.all_cards(deck))

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
            blit_aspect(surface, self.app.assets.image("placeholder/card_back"), pygame.Rect(x + 8, y + 8, 194, 106))
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
        self.known = self.card.id in set(player.library_cards) | set(DeckRules.all_cards(deck))

    def enter(self):
        self.buttons = [Button((70, 470, 230, 46), "RUN EFFECT EXAMPLE", lambda: self.app.push(CardSimulationScene(self.app, self.card.id))), Button((315, 470, 170, 46), "MODIFY CARD", lambda: self.app.push(CardMakerScene(self.app, self.card.id))), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop())]

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CARD DETAIL", (34, 28), self.app.assets.font(28, True), COLORS["cyan"])
        draw_text(surface, "The engine generates a readable explanation from structured effect data.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        rounded(surface, (60, 122, 240, 280), (22, 35, 67), COLORS["gold"] if self.card.legendary and self.known else COLORS["line"], 12, 3)
        if not self.known:
            blit_aspect(surface, self.app.assets.image("placeholder/card_back"), pygame.Rect(75, 139, 210, 240))
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
        name = "Preset Deck " + str(len(self.app.store.decks) + 1)
        owner_id = self.app.store.role_config().get("player_character", "")
        deck_id = self.app.store.create_deck(name, owner_id, preferred_families=["warrior"])
        if not deck_id:
            self.app.notify("Preset deck could not be created under the ten-deck limit.")
            return
        self.app.notify("Preset deck created with a legal 40-card main deck and editable metadata.")
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
        self.description = None
        self.portrait = None
        self.query = None
        self.page = 0

    def enter(self):
        deck = self.app.store.decks.get(self.deck_id, {})
        self.name = TextInput((40, 76, 250, 32), deck.get("name", self.deck_id))
        self.description = TextInput((40, 114, 330, 28), deck.get("description", ""))
        self.portrait = TextInput((400, 76, 170, 32), "")
        self.query = TextInput((580, 76, 180, 32), "")
        self.card_buttons = []
        self.page = 0
        self.buttons = [Button((40, 530, 138, 38), "SAVE META", lambda: self.save_metadata(), COLORS["cyan"]), Button((186, 530, 120, 38), "DUPLICATE", lambda: self.duplicate(), COLORS["gold"]), Button((314, 530, 126, 38), "EXPORT .CBP", lambda: self.export(), COLORS["violet"]), Button((448, 530, 62, 38), "PREV", lambda: self.change_page(-1), COLORS["muted"]), Button((516, 530, 62, 38), "PAGE >", lambda: self.change_page(1), COLORS["muted"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def save_metadata(self):
        result = self.app.store.update_deck(self.deck_id, {"name": self.name.value, "description": self.description.value, "portrait": self.portrait.value})
        self.app.notify("Deck metadata saved." if result else "Deck metadata could not be saved.")
        self.enter()

    def duplicate(self):
        new_id = self.app.store.duplicate_deck(self.deck_id)
        self.app.notify("Deck duplicated as a separate editable preset." if new_id else "Deck duplication rejected by the ten-deck limit or legality rules.")
        if new_id: self.app.push(DeckEditorScene(self.app, new_id))

    def export(self):
        path = self.app.store.export_cbp("deck", self.deck_id, False, True)
        self.app.notify("Exported dependency-scoped deck package: " + path.name)

    def change_page(self, amount):
        self.page = max(0, self.page + amount)
        self.enter()

    def add_card(self, card_id):
        deck = self.app.store.decks[self.deck_id]
        main = list(deck.get("main_cards", []))
        fusion = list(deck.get("fusion_cards", []))
        card = self.app.store.cards.get(card_id)
        if not card: return
        (fusion if card.kind == "fusion" else main).append(card_id)
        errors = DeckRules.validate(main, fusion, self.app.store.cards)
        if any("exceeds" in error or "maximum" in error for error in errors):
            self.app.notify("That card would exceed the deck copy or collection limit.")
            return
        deck["main_cards"] = main
        deck["fusion_cards"] = fusion
        self.app.store.save()
        self.enter()

    def remove_card(self, card_id):
        deck = self.app.store.decks[self.deck_id]
        collection = deck.get("fusion_cards", []) if self.app.store.cards.get(card_id) and self.app.store.cards[card_id].kind == "fusion" else deck.get("main_cards", [])
        if card_id in collection:
            collection.remove(card_id)
            self.app.store.save()
            self.enter()

    def handle(self, event):
        self.name.handle(event)
        self.description.handle(event)
        self.portrait.handle(event)
        self.query.handle(event)
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, action, card_id in self.card_buttons:
                if rect.collidepoint(event.pos): action(card_id); return

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        deck = self.app.store.decks[self.deck_id]
        state = self.app.store.deck_editor_state(self.deck_id)
        draw_text(surface, "DECK EDITOR", (34, 28), self.app.assets.font(28, True), COLORS["gold"])
        draw_text(surface, "Edit a named deck through explicit card transactions; Fusion cards remain in the Extra Deck.", (36, 55), self.app.assets.font(12), COLORS["muted"])
        self.name.draw(surface, self.app.assets.font(10), "Deck name")
        self.description.draw(surface, self.app.assets.font(10), "Deck description")
        self.portrait.draw(surface, self.app.assets.font(10), "Portrait key")
        self.query.draw(surface, self.app.assets.font(10), "Search cards")
        main_count = len(state["main_cards"]) if state else 0
        extra_count = len(state["fusion_cards"]) if state else 0
        status = "LEGAL" if state and state["legal"] else "INCOMPLETE / INVALID"
        draw_text(surface, f"MAIN {main_count}/{DeckRules.maximum}  |  FUSION/EXTRA {extra_count}/{DeckRules.fusion_maximum}  |  {status}", (400, 137), self.app.assets.font(12, True), COLORS["green"] if status == "LEGAL" else COLORS["red"], "center")
        self.draw_panel(surface, (32, 155, 360, 330), "CURRENT CARDS", COLORS["gold"])
        self.draw_panel(surface, (410, 155, 358, 330), "CARD CATALOG", COLORS["cyan"])
        self.card_buttons = []
        counts = state["counts"] if state else {}
        current_ids = sorted(counts, key=lambda item: self.app.store.cards.get(item).name.lower() if self.app.store.cards.get(item) else item)[:11]
        for index, card_id in enumerate(current_ids):
            card = self.app.store.cards.get(card_id)
            if not card: continue
            y = 194 + index * 25
            draw_text(surface, f"{card.name[:18]} x{counts[card_id]}", (50, y), self.app.assets.font(10), COLORS["cream"])
            rect = pygame.Rect(324, y - 5, 45, 22)
            rounded(surface, rect, (22, 38, 77), COLORS["red"], 5, 1)
            draw_text(surface, "-1", rect.center, self.app.assets.font(10, True), COLORS["cream"], "center")
            self.card_buttons.append((rect, self.remove_card, card.id))
        query = self.query.value.strip().lower()
        cards = [card for card in self.app.store.cards.values() if not query or query in card.name.lower() or query in card.id.lower()]
        cards.sort(key=lambda item: item.name.lower())
        visible = cards[self.page * 12:self.page * 12 + 12]
        for index, card in enumerate(visible):
            x = 425 + (index % 2) * 166
            y = 190 + (index // 2) * 47
            rect = pygame.Rect(x, y, 154, 34)
            rounded(surface, rect, tuple(card.art_color), COLORS["line"], 5, 1)
            draw_text(surface, "+ " + card.name[:16], rect.center, self.app.assets.font(9, True), COLORS["ink"], "center")
            self.card_buttons.append((rect, self.add_card, card.id))
        if state and state["errors"]:
            draw_text(surface, state["errors"][0][:62], (400, 468), self.app.assets.font(9), COLORS["red"], "center")
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
        self.subtypes = TextInput((80, 315, 640, 34), ", ".join(getattr(card, "subtypes", [])) if card else "")
        self.stars = int(card.stars) if card else 4
        self.atk = int(card.atk) if card else 1500
        self.defense = int(card.defense) if card else 1200
        self.logic_graph = card.logic_graph if card else ""
        self.targets = list(card.targets) if card else ["none"]
        self.target_count = int(card.target_count) if card else 0
        self.timing = card.timing if card else "main"
        self.summon_method = card.summon_method if card else "normal"
        self.summon_procedure = dict(card.summon_procedure) if card else {}
        self.legendary_type = str(getattr(card, "legendary_type", "") or "") if card else ""
        self.non_removable = bool(getattr(card, "non_removable", False)) if card else False
        self.materials = list(card.materials) if card else []
        self.materials_text = TextInput((80, 365, 640, 34), ", ".join(self.materials))
        self.ritual_cost = int(card.ritual_cost) if card else 0
        self.effects = [dict(raw) for raw in card.effects] if card else []
        self.refresh_buttons()

    def refresh_buttons(self):
        self.buttons = [Button((420, 150, 150, 34), "TYPE: " + self.kind.upper(), lambda: self.cycle_kind(), COLORS["violet"]), Button((590, 150, 150, 34), "FAMILY: " + self.family.upper(), lambda: self.cycle_family(), COLORS["cyan"]), Button((420, 200, 150, 34), "LOGIC: " + (self.logic_graph or "NONE").upper(), lambda: self.cycle_logic(), COLORS["gold"]), Button((590, 200, 150, 34), "TARGET: " + self.targets[0].upper(), lambda: self.cycle_target(), COLORS["green"]), Button((420, 245, 150, 34), "EFFECTS: " + str(len(self.effects)), lambda: self.open_effects(), COLORS["orange"]), Button((80, 340, 110, 34), "STAR +", lambda: self.change("stars", 1)), Button((200, 340, 110, 34), "ATK +", lambda: self.change("atk", 100)), Button((320, 340, 110, 34), "DEF +", lambda: self.change("defense", 100)), Button((440, 340, 150, 34), "TIMING", lambda: self.cycle_timing()), Button((80, 410, 180, 34), "SUMMON MODE", lambda: self.cycle_summon()), Button((280, 410, 180, 34), "TARGET COUNT", lambda: self.cycle_target_count()), Button((80, 470, 240, 38), "SAVE MODIFIED" if self.card_id else "CREATE CARD", lambda: self.save_card(), COLORS["green"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def procedure_for_kind(self):
        if self.kind == "fusion": return {"kind": "fusion", "required_card_ids": list(self.materials), "material_selector": {"side": "self", "zone": ["hand", "monster"]}, "locations": ["hand", "monster"], "exact": True, "material_destination": "graveyard", "source_selector": {"zone": "extra", "card_kind": "fusion"}, "source_method": "fusion", "enabler": {"card_kinds": ["spell", "effect"]}}
        if self.kind == "ritual": return {"kind": "ritual", "min_stars": int(self.ritual_cost), "material_selector": {"side": "self", "zone": ["hand", "monster"]}, "locations": ["hand", "monster"], "exact": False, "material_destination": "graveyard", "source_selector": {"zone": "hand", "card_kind": "ritual"}, "source_method": "ritual", "enabler": {"card_kinds": ["spell", "effect"]}}
        if self.kind == "legendary": return {"kind": "legendary", "source_zones": ["hand", "graveyard"], "source_selector": {"zone": ["hand", "graveyard"], "card_kind": "legendary"}, "source_method": "legendary_special", "special": True, "enabler": {"card_kinds": ["spell", "effect"]}}
        return {}

    def cycle_kind(self):
        values = ["normal", "effect", "spell", "trap", "field", "fusion", "ritual", "legendary"]
        self.kind = values[(values.index(self.kind) + 1) % len(values)]
        if self.kind == "fusion": self.summon_method, self.materials, self.ritual_cost = "fusion", [], 0
        elif self.kind == "ritual": self.summon_method, self.materials, self.ritual_cost = "ritual", [], 7
        elif self.kind == "legendary": self.summon_method, self.materials, self.ritual_cost = "legendary", [], 0
        else: self.summon_method, self.materials, self.ritual_cost = "normal", [], 0
        self.summon_procedure = self.procedure_for_kind()
        self.legendary_type = self.family if self.kind == "legendary" else ""
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
        values = ["normal", "fusion", "ritual", "legendary"]
        self.summon_method = values[(values.index(self.summon_method) + 1) % len(values)] if self.summon_method in values else "normal"
        if self.summon_method == "fusion": self.kind, self.materials, self.ritual_cost = "fusion", [], 0
        elif self.summon_method == "ritual": self.kind, self.materials, self.ritual_cost = "ritual", [], 7
        elif self.summon_method == "legendary": self.kind, self.materials, self.ritual_cost = "legendary", [], 0
        else: self.materials, self.ritual_cost = [], 0
        self.summon_procedure = self.procedure_for_kind()
        self.legendary_type = self.family if self.kind == "legendary" else ""
        self.materials_text.value = ", ".join(self.materials)
        self.refresh_buttons()

    def cycle_target_count(self):
        self.target_count = 0 if self.targets == ["none"] else (self.target_count % 3) + 1
        self.refresh_buttons()

    def change(self, field_name, amount): setattr(self, field_name, clamp(getattr(self, field_name) + amount, 0, 10000)); self.refresh_buttons()

    def save_card(self):
        graph = self.logic_graph
        self.materials = [value.strip() for value in self.materials_text.value.split(",") if value.strip()]
        self.summon_procedure = self.procedure_for_kind() if self.kind in ["fusion", "ritual", "legendary"] else {}
        values = {"name": self.name.value, "kind": self.kind, "stars": 11 if self.kind == "legendary" else self.stars if self.kind in ["normal", "effect", "fusion", "ritual"] else 0, "atk": self.atk if self.kind in ["normal", "effect", "fusion", "ritual", "legendary"] else 0, "defense": self.defense if self.kind in ["normal", "effect", "fusion", "ritual", "legendary"] else 0, "family": self.family, "subtypes": [item.strip().lower() for item in self.subtypes.value.split(",") if item.strip()][:2], "description": self.description.value, "logic_graph": graph, "targets": self.targets, "target_count": self.target_count, "timing": self.timing, "field_effect": {"family": self.family, "atk": 300} if self.kind == "field" else {}, "materials": self.materials, "ritual_cost": 7 if self.kind == "ritual" else self.ritual_cost, "summon_method": self.summon_method, "summon_procedure": self.summon_procedure, "legendary_type": self.legendary_type or (self.family if self.kind == "legendary" else ""), "non_removable": self.non_removable, "effects": self.effects}
        errors = self.app.store.validate_card_definition(values["kind"], values["stars"], values["atk"], values["defense"], values["family"], values["description"], values["targets"], values["target_count"], values["timing"], values["materials"], values["ritual_cost"], values["summon_method"], values["effects"], values["summon_procedure"], values["legendary_type"])
        if errors: self.app.notify("Card rejected: " + "; ".join(errors[:2])); return
        if self.card_id:
            if not self.app.store.update_card(self.card_id, values): self.app.notify("Card update failed."); return
        else:
            created = self.app.store.create_card(values["name"], values["kind"], values["stars"], values["atk"], values["defense"], values["family"], values["description"], graph, values["targets"], values["target_count"], values["timing"], values["field_effect"], values["materials"], values["ritual_cost"], values["summon_method"], self.art_path.value, values["effects"], values["summon_procedure"], values["legendary_type"], values["non_removable"])
            if created:
                created.subtypes = values["subtypes"]
                self.app.store.save()

        self.app.store.load()
        self.app.notify("Card saved with its authored data and editable folder structure.")

    def handle(self, event):
        self.name.handle(event); self.art_path.handle(event); self.description.handle(event); self.subtypes.handle(event); self.materials_text.handle(event); super().handle(event)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CARD MAKER", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, "Create or modify a card definition; engine frame and metadata remain separate from user art.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (42, 112, 720, 390), "CARD DEFINITION", COLORS["violet"])
        self.name.draw(surface, self.app.assets.font(12), "Card name")
        self.art_path.draw(surface, self.app.assets.font(12), "User art path, optional")
        self.description.draw(surface, self.app.assets.font(12), "Description")
        self.subtypes.draw(surface, self.app.assets.font(12), "Monster subtypes, up to two, comma-separated")
        draw_text(surface, f"STARS {self.stars} | ATK {self.atk} | DEF {self.defense} | RITUAL COST {self.ritual_cost}", (80, 365), self.app.assets.font(13, True), COLORS["cream"])
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
        if not self.graph_key:
            owner_category, owner_id, owner_root = next(((category, entity_id, DATA / (entity.get("media_folder", "") if isinstance(entity, dict) else getattr(entity, "media_folder", "")) / "logic") for category, registry in [("cards", self.app.store.cards), ("characters", self.app.store.characters), ("teams", self.app.store.teams), ("places", self.app.store.places), ("decks", self.app.store.decks)] for entity_id, entity in registry.items() if (entity.get("media_folder", "") if isinstance(entity, dict) else getattr(entity, "media_folder", ""))), ("", "", DATA))
            self.graph_key = "editor_" + owner_category + "_" + str(owner_id)
            owner_root.mkdir(parents=True, exist_ok=True)
            self.app.store.logic_owners[self.graph_key] = owner_root
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
        owner = self.app.store.logic_owners.get(self.graph_key)
        if not owner or owner == DATA or not owner.is_relative_to(DATA):
            self.app.notify("Logic graph requires an entity-owned folder.")
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
            image = self.app.assets.character_portrait(char, (64, 64))
            if image: ui_blit(surface, image, (50, y + 9))
            draw_text(surface, char.name, (132, y + 14), self.app.assets.font(16, True), COLORS["cream"])
            draw_text(surface, f"{char.stars} stars  |  rank {char.rank}  |  smartness {char.smartness}/10  |  mood {char.mood}", (132, y + 41), self.app.assets.font(11), accent)
            active_battle = next((battle for battle in self.app.store.world.get("active_battles", []) if battle.get("status") == "active" and char.id in [battle.get("from"), battle.get("to")]), None)
            current_state = "OUT OF GAME" if char.world_status != "in_playground" else "IN DUEL" if active_battle else str(char.availability).upper() + " / " + str(char.activity).upper()
            draw_text(surface, current_state + "  |  place: " + (char.current_place or "none") + "  |  history: " + str(len(char.history)), (132, y + 62), self.app.assets.font(10), COLORS["muted"])
            button = Button((650, y + 23, 92, 34), "DETAIL", lambda char_id=char.id: self.app.push(EntityDetailScene(self.app, "characters", char_id)), COLORS["cyan"])
            self.row_buttons.append(button)
            button.draw(surface, self.app.assets.font(10, True))
        self.draw_buttons(surface, 11)


class EntityDetailScene(Scene):
    def __init__(self, app, entity_type, entity_id):
        super().__init__(app)
        self.entity_type = {"card": "cards", "deck": "decks", "character": "characters", "team": "teams", "place": "places"}.get(entity_type, entity_type)
        self.entity_id = entity_id
        self.about_scope = "about_" + str(id(self))
        self.about_selection = None
        self.about_elapsed = 0.0

    def enter(self):
        self.buttons = []
        if self.entity_type in ["characters", "teams", "places"]:
            self.buttons.append(Button((42, 530, 170, 38), "ABOUT / MEDIA", lambda: self.app.push(EntityAboutScene(self.app, self.entity_type, self.entity_id)), COLORS["cyan"]))
        if self.entity_type == "characters":
            self.buttons.append(Button((250, 530, 155, 38), "EDIT CHARACTER", lambda: self.app.push(CharacterMakerScene(self.app, self.entity_id)), COLORS["violet"]))
            self.buttons.append(Button((420, 530, 160, 38), "EDIT WEIGHTS", lambda: self.app.push(BehaviorWeightsScene(self.app, self.entity_id)), COLORS["gold"]))
        elif self.entity_type == "teams":
            self.buttons.append(Button((350, 530, 200, 38), "EDIT TEAM", lambda: self.app.push(TeamMakerScene(self.app, self.entity_id)), COLORS["gold"]))
        elif self.entity_type == "places":
            self.buttons.append(Button((350, 530, 200, 38), "EDIT PLACE", lambda: self.app.push(PlaceMakerScene(self.app, self.entity_id)), COLORS["green"]))
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
            image = self.app.assets.character_portrait(entity, (150, 150))
            if image: ui_blit(surface, image, (68, 165))
            weights = ", ".join(f"{key}={float(value):.1f}" for key, value in sorted(entity.behavior_weights.items()) if key != "movement_duration" and isinstance(value, (int, float)))
            active_battle = next((battle for battle in self.app.store.world.get("active_battles", []) if battle.get("status") == "active" and entity.id in [battle.get("from"), battle.get("to")]), None)
            current_state = "OUT OF GAME" if entity.world_status != "in_playground" else "IN DUEL" if active_battle else str(entity.availability).upper() + " / " + str(entity.activity).upper()
            lines = [f"Gender: {entity.gender}", f"Origin: {entity.origin}", f"Stars: {entity.stars}", f"Rank: {entity.rank}", f"Smartness: {entity.smartness}/10", f"Mood: {entity.mood}", f"Relationship: {entity.relationship}", "Runtime: " + current_state, "Current place: " + (entity.current_place or "none"), "Preferred: " + ", ".join(entity.preferred_families), "Best cards: " + ", ".join(entity.best_cards or ["not set"]), f"Learned opponents: {len(entity.learned_opponents)}  |  learned cards: {len(entity.learned_cards)}", "Weights: " + (weights or "default"), f"History events: {len(entity.history)}"]
        elif self.entity_type == "places":
            lines = [f"Capacity: {entity.capacity}", f"Active duels: {entity.current_duels}", f"Background: {entity.background}", f"Day/night: {'enabled' if entity.day_night else 'disabled'}", f"Media folder: {entity.media_folder or 'legacy/id folder'}"]
        else:
            effect = entity.team_effect.get("selected") if entity.team_effect else None
            lines = [f"Members: {len(entity.members)}", f"Leader: {entity.leader}", f"Rank: {entity.rank}", f"Relationship: {entity.relationship}", f"Effect: {effect.get('kind') if effect else 'not crafted'}", f"History events: {len(entity.history)}"]
        for index, line in enumerate(lines): draw_text(surface, line, (270 if self.entity_type == "characters" else 70, 170 + index * 28), self.app.assets.font(13), COLORS["cream"])
        self.draw_buttons(surface, 12)


class EntityAboutScene(Scene):
    def __init__(self, app, entity_type, entity_id):
        super().__init__(app)
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.scope = "entity_about_" + str(id(self))
        self.selection = None
        self.elapsed = 0.0
        self.frame = ""

    def enter(self):
        self.app.assets.media_scopes.setdefault(self.scope, set())
        entity = getattr(self.app.store, self.entity_type).get(self.entity_id)
        if not entity: return
        actor_id = self.app.store.role_config().get("player_character", "")
        place_id = self.app.store.role_config().get("default_place", "")
        relation = self.app.store.relationship_for(actor_id, self.entity_id) if self.entity_type == "characters" else "opponent"
        self.selection = self.app.store.media.resolve("about", actor_id, self.entity_id, relation, self.entity_type, self.entity_id, place_id, "loop")
        if self.selection and self.selection.audio and self.app.store.save_data.get("vocals", True): self.app.assets.play_reaction_audio(self.selection.audio, True, 0.8, self.scope)

    def leave(self):
        if pygame.mixer.get_init():
            try: pygame.mixer.stop()
            except pygame.error: pass
        self.app.assets.release_media_scope(self.scope)

    def update(self, dt):
        self.elapsed += dt
        if self.selection:
            frames = list(getattr(self.selection, "frames", []) or [])
            if frames:
                self.frame = frames[int(self.elapsed * FPS) % len(frames)]
            else: self.frame = getattr(self.selection, "image", "")

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: self.app.pop()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and pygame.Rect(650, 530, 110, 38).collidepoint(event.pos): self.app.pop()

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        entity = getattr(self.app.store, self.entity_type).get(self.entity_id)
        if not entity:
            draw_text(surface, "ENTITY NOT FOUND", (400, 280), self.app.assets.font(22, True), COLORS["red"], "center")
            return
        accent = COLORS["violet"] if self.entity_type == "characters" else COLORS["green"] if self.entity_type == "places" else COLORS["gold"]
        draw_text(surface, entity.name, (34, 28), self.app.assets.font(28, True), accent)
        draw_text(surface, "ABOUT / MEDIA", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (42, 105, 716, 380), "AUTHORED PRESENTATION", accent)
        image_path = self.frame or getattr(entity, "portrait", "") or getattr(entity, "background", "")
        image = self.app.assets.media_image(image_path, (320, 245), self.scope) if image_path else None
        if image: ui_blit(surface, image, image.get_rect(center=(400, 265)))
        else:
            draw_text(surface, "No about media authored yet", (400, 250), self.app.assets.font(18, True), COLORS["muted"], "center")
            draw_text(surface, "The entity remains fully usable through its structured data.", (400, 282), self.app.assets.font(11), COLORS["cream"], "center")
        description = str(getattr(entity, "description", "") or "")
        draw_text(surface, description[:92] if description else "Description pending", (400, 408), self.app.assets.font(12), COLORS["cream"], "center")
        media_state = "image/frame media" if self.selection and not getattr(self.selection, "placeholder", False) else "fallback"
        draw_text(surface, "Media: " + media_state + "  |  vocals: " + ("available" if self.selection and self.selection.audio else "optional / absent"), (400, 445), self.app.assets.font(10), COLORS["muted"], "center")
        Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"]).draw(surface, self.app.assets.font(12, True))


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

    def __init__(self, app, character_id=None):
        super().__init__(app)
        self.character_id = character_id

    def parse_list(self, value):
        return [item.strip().lower() for item in str(value).split(",") if item.strip()]

    def parse_map(self, value):
        result = {}
        for part in str(value).split(","):
            if "=" not in part: continue
            key, raw = part.split("=", 1)
            try: result[key.strip().lower()] = float(raw.strip())
            except (TypeError, ValueError): pass
        return result

    def enter(self):
        character = self.app.store.characters.get(self.character_id) if self.character_id else None
        self.name = TextInput((70, 122, 300, 30), character.name if character else "New Character")
        self.portrait = TextInput((400, 122, 300, 30), "")
        self.description = TextInput((70, 160, 630, 30), character.description if character else "")
        self.family = TextInput((70, 198, 300, 30), ", ".join(character.preferred_families) if character else "warrior")
        self.deck = TextInput((400, 198, 300, 30), character.deck_id if character else "")
        self.card_kinds = TextInput((70, 236, 300, 30), ", ".join(getattr(character, "preferred_card_kinds", [])) if character else "")
        self.subtypes = TextInput((400, 236, 300, 30), ", ".join(getattr(character, "preferred_subtypes", [])) if character else "")
        self.preferred_cards = TextInput((70, 274, 300, 30), ", ".join(getattr(character, "preferred_cards", [])) if character else "")
        self.preferred_places = TextInput((400, 274, 300, 30), ", ".join(getattr(character, "preferred_places", [])) if character else "")
        profile = getattr(character, "technique_profile", {}) if character else {}
        self.techniques = TextInput((70, 312, 630, 30), ", ".join(f"{key}={value:g}" for key, value in profile.items()) if profile else "aggression=5, control=5, combo=5, defense=5, adaptation=5")
        self.origin = TextInput((70, 350, 300, 30), character.origin if character else "community")
        self.logic = TextInput((400, 350, 300, 30), getattr(character, "logic_graph", "") if character else "")
        self.gender = character.gender if character else "other"
        self.stars = int(character.stars) if character else 5
        self.smartness = int(character.smartness) if character else 5
        label = "SAVE CHARACTER" if character else "CREATE CHARACTER"
        self.buttons = [Button((70, 390, 150, 32), "GENDER: " + self.gender.upper(), lambda: self.cycle_gender(), COLORS["violet"]), Button((236, 390, 140, 32), "EDIT WEIGHTS", lambda: self.open_weights(), COLORS["gold"]), Button((392, 390, 90, 32), "STARS +", lambda: self.change("stars", 1), COLORS["gold"]), Button((492, 390, 110, 32), "SMART +", lambda: self.change("smartness", 1), COLORS["cyan"]), Button((70, 430, 210, 36), label, lambda: self.save_character(), COLORS["green"]), Button((300, 430, 180, 36), "EXPORT CHARACTER", lambda: self.export(), COLORS["violet"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def change(self, field, amount): setattr(self, field, clamp(getattr(self, field) + amount, 1, 10))

    def cycle_gender(self):
        self.gender = self.genders[(self.genders.index(self.gender) + 1) % len(self.genders)]
        self.buttons[0].label = "GENDER: " + self.gender.upper()

    def open_weights(self):
        if self.character_id: self.app.push(BehaviorWeightsScene(self.app, self.character_id))
        else: self.app.notify("Save the character first to edit persistent behavior weights.")

    def export(self):
        if not self.character_id:
            self.app.notify("Save the character before exporting its dependency package.")
            return
        path = self.app.store.export_cbp("character", self.character_id, True, True)
        self.app.notify("Exported character package with dependencies and experience: " + path.name)

    def save_character(self):
        values = {"name": self.name.value, "portrait": self.portrait.value, "description": self.description.value, "preferred_families": self.parse_list(self.family.value), "deck_id": self.deck.value.strip(), "preferred_card_kinds": self.parse_list(self.card_kinds.value), "preferred_subtypes": self.parse_list(self.subtypes.value)[:2], "preferred_cards": self.parse_list(self.preferred_cards.value), "preferred_places": self.parse_list(self.preferred_places.value), "technique_profile": self.parse_map(self.techniques.value), "gender": self.gender, "origin": self.origin.value, "logic_graph": self.logic.value.strip(), "stars": self.stars, "smartness": self.smartness}
        if self.character_id:
            result = self.app.store.update_character(self.character_id, values)
        else:
            result = self.app.store.create_character(values["name"], values["stars"], values["smartness"], values["preferred_families"][0] if values["preferred_families"] else "warrior", values["portrait"], values["gender"], values["origin"], values["deck_id"], values["description"], values["preferred_card_kinds"], values["preferred_subtypes"], values["preferred_cards"], values["preferred_places"], values["technique_profile"], values["logic_graph"])
            if result: self.character_id = result.id
        self.app.store.load()
        self.app.notify("Character definition saved with preferences, cognition inputs, deck linkage, and media structure." if result else "Character definition could not be saved.")
        self.enter()

    def handle(self, event):
        for field in [self.name, self.portrait, self.description, self.family, self.deck, self.card_kinds, self.subtypes, self.preferred_cards, self.preferred_places, self.techniques, self.origin, self.logic]: field.handle(event)
        super().handle(event)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "CHARACTER MAKER / EDITOR", (34, 28), self.app.assets.font(27, True), COLORS["violet"])
        draw_text(surface, "Identity, deck preferences, relationships-ready fields, cognition inputs, technique weights, and media roots remain separately authored.", (36, 62), self.app.assets.font(11), COLORS["muted"])
        self.draw_panel(surface, (42, 100, 720, 370), "CHARACTER DEFINITION", COLORS["violet"])
        for field, label in [(self.name, "Name"), (self.portrait, "Portrait key"), (self.description, "Description"), (self.family, "Preferred families"), (self.deck, "Deck id"), (self.card_kinds, "Preferred card kinds"), (self.subtypes, "Preferred monster subtypes, max 2"), (self.preferred_cards, "Preferred / best cards"), (self.preferred_places, "Preferred places"), (self.techniques, "Technique weights key=value"), (self.origin, "Origin"), (self.logic, "Logic graph id")]: field.draw(surface, self.app.assets.font(10), label)
        draw_text(surface, f"STARS {self.stars}/10   SMARTNESS {self.smartness}/10   GENDER {self.gender.upper()}", (400, 415), self.app.assets.font(12, True), COLORS["cream"], "center")
        draw_text(surface, "Runtime learning, relationship history, knowledge, and duel experience stay outside authored fields.", (400, 470), self.app.assets.font(10), COLORS["gold"], "center")
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
        self.place_id = next(iter(self.team.preferred_places), self.app.store.role_config()["default_place"])
        self.place_candidates = self.app.store.world.setdefault("place_effects", {}).get(self.place_id, {}).get("candidates", [])
        self.card_rects = []
        self.buttons = [Button((48, 530, 170, 38), "CRAFT CANDIDATES", lambda: self.craft(), COLORS["gold"]), Button((228, 530, 190, 38), "CRAFT PLACE EFFECT", lambda: self.craft_place(), COLORS["green"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

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

    def craft_place(self):
        if len(self.selected) != 3:
            self.app.notify("Select three different member-owned cards first.")
            return
        result = self.app.store.craft_place_effect(self.team_id, self.place_id, self.selected)
        if result:
            self.place_candidates = result.get("candidates", [])
            self.buttons = [Button((48 + index * 200, 470, 180, 42), "PLACE CHOOSE " + str(index + 1), lambda index=index: self.choose_place(index), COLORS["green"]) for index in range(3)] + [Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]
            self.app.notify("Three place effects were generated. Choose one permanently.")
        else: self.app.notify("The place is not linked to this team or already has a locked effect.")

    def choose_place(self, index):
        if self.app.store.choose_place_effect(self.place_id, index): self.app.notify("Place effect locked permanently: " + self.place_candidates[index].get("kind", "effect"))
        else: self.app.notify("The place effect choice is invalid or already locked.")

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "TEAM EFFECT CRAFTING", (34, 28), self.app.assets.font(28, True), COLORS["gold"])
        draw_text(surface, "Sacrifice three different member-owned cards. The team and its linked place can each choose one generated effect forever.", (36, 65), self.app.assets.font(13), COLORS["muted"])
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
            draw_text(surface, "TEAM CANDIDATES", (260, 450), self.app.assets.font(11, True), COLORS["gold"], "center")
            for index, candidate in enumerate(self.candidates): draw_text(surface, f"{index + 1}. {candidate}", (260, 470 + index * 18), self.app.assets.font(9), COLORS["cream"], "center")
        if self.place_candidates:
            draw_text(surface, "PLACE CANDIDATES: " + self.place_id, (570, 450), self.app.assets.font(11, True), COLORS["green"], "center")
            for index, candidate in enumerate(self.place_candidates): draw_text(surface, f"{index + 1}. {candidate}", (570, 470 + index * 18), self.app.assets.font(9), COLORS["cream"], "center")
        if not self.candidates and not self.place_candidates: draw_text(surface, f"Selected sacrifices: {len(self.selected)} / 3", (400, 450), self.app.assets.font(13, True), COLORS["cyan"], "center")
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
    def __init__(self, app, team_id=None):
        super().__init__(app)
        self.team_id = team_id

    def parse_list(self, value):
        return [item.strip().lower() for item in str(value).split(",") if item.strip()]

    def enter(self):
        team = self.app.store.teams.get(self.team_id) if self.team_id else None
        self.name = TextInput((70, 122, 300, 30), team.name if team else "New Team")
        self.portrait = TextInput((400, 122, 300, 30), "")
        self.description = TextInput((70, 160, 630, 30), team.description if team else "")
        self.place = TextInput((70, 198, 300, 30), ", ".join(team.preferred_places) if team else self.app.store.role_config().get("default_place", ""))
        self.leader = TextInput((400, 198, 300, 30), team.leader if team else "")
        self.members = [TextInput((70, 236 + index * 32, 300, 28), team.members[index] if team and index < len(team.members) else "") for index in range(3)]
        self.families = TextInput((400, 236, 300, 28), ", ".join(getattr(team, "preferred_families", [])) if team else "")
        self.kinds = TextInput((400, 268, 300, 28), ", ".join(getattr(team, "preferred_card_kinds", [])) if team else "")
        self.cards = TextInput((400, 300, 300, 28), ", ".join(getattr(team, "preferred_cards", [])) if team else "")
        self.logic = TextInput((70, 332, 630, 28), getattr(team, "logic_graph", "") if team else "")
        label = "SAVE TEAM" if team else "CREATE TEAM"
        self.buttons = [Button((70, 390, 210, 38), label, lambda: self.save_team(), COLORS["green"]), Button((294, 390, 224, 38), "EXPORT TEAM", lambda: self.export(), COLORS["violet"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def export(self):
        if not self.team_id:
            self.app.notify("Save the team before exporting it.")
            return
        path = self.app.store.export_cbp("team", self.team_id, True, True)
        self.app.notify("Exported team package with member dependencies: " + path.name)

    def save_team(self):
        members = [field.value.strip() for field in self.members if field.value.strip()]
        values = {"name": self.name.value, "portrait": self.portrait.value, "description": self.description.value, "members": members, "leader": self.leader.value.strip(), "preferred_places": self.parse_list(self.place.value), "preferred_families": self.parse_list(self.families.value), "preferred_card_kinds": self.parse_list(self.kinds.value), "preferred_cards": self.parse_list(self.cards.value), "logic_graph": self.logic.value.strip()}
        if self.team_id:
            result = self.app.store.update_team(self.team_id, values)
        else:
            result = self.app.store.create_team(values["name"], values["members"], values["preferred_places"][0] if values["preferred_places"] else "", values["portrait"], values["description"], values["leader"], values["preferred_places"], values["preferred_families"], values["preferred_card_kinds"], values["preferred_cards"], values["logic_graph"])
            if result: self.team_id = result.id
        self.app.store.load()
        self.app.notify("Team definition saved with ordered members, leader, preferences, and media structure." if result else "Team requires at least one registered member and valid fields.")
        self.enter()

    def handle(self, event):
        for field in [self.name, self.portrait, self.description, self.place, self.leader, self.families, self.kinds, self.cards, self.logic] + self.members: field.handle(event)
        super().handle(event)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "TEAM MAKER / EDITOR", (34, 28), self.app.assets.font(27, True), COLORS["violet"])
        draw_text(surface, "Teams are three ordered characters with explicit leadership, identity, preferences, effects, and member media dependencies.", (36, 62), self.app.assets.font(11), COLORS["muted"])
        self.draw_panel(surface, (42, 100, 720, 390), "TEAM DEFINITION", COLORS["violet"])
        for field, label in [(self.name, "Team name"), (self.portrait, "Team portrait key"), (self.description, "Description"), (self.place, "Preferred places"), (self.leader, "Leader character id"), (self.families, "Preferred families"), (self.kinds, "Preferred card kinds"), (self.cards, "Preferred cards"), (self.logic, "Logic graph id")]: field.draw(surface, self.app.assets.font(10), label)
        for index, field in enumerate(self.members): field.draw(surface, self.app.assets.font(10), f"Ordered member {index + 1} id")
        draw_text(surface, "Member order is preserved for team duel rotation and team media staging. Use ids from the Characters list.", (400, 455), self.app.assets.font(10), COLORS["gold"], "center")
        self.draw_buttons(surface, 12)
        self.app.draw_notice(surface)


class PlaceDuelViewScene(Scene):
    def __init__(self, app, place_id=None):
        super().__init__(app)
        self.place_id = place_id or app.store.role_config()["default_place"]
        self.mode = "duels"
        self.battles = []
        self.media_scope = "place_view_" + str(id(self))

    def enter(self):
        self.refresh()
        self.buttons = [Button((40, 530, 130, 38), "DUELS", lambda: self.set_mode("duels"), COLORS["gold"]), Button((180, 530, 130, 38), "LANDSCAPE", lambda: self.set_mode("landscape"), COLORS["green"]), Button((322, 530, 128, 38), "ADVANCE 1 SEC", lambda: self.advance(1), COLORS["cyan"]), Button((460, 530, 128, 38), "ADVANCE 5 SEC", lambda: self.advance(5), COLORS["cyan"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def leave(self):
        self.app.assets.release_media_scope(self.media_scope)

    def set_mode(self, mode):
        self.mode = mode if mode in ["duels", "landscape"] else "duels"
        self.refresh()

    def refresh(self):
        self.battles = [item for item in self.app.store.world.setdefault("active_battles", []) if item.get("status") == "active" and item.get("place") == self.place_id][:3]
        if hasattr(self, "buttons"):
            self.buttons = self.buttons[:5]
            if self.mode == "duels":
                for index, battle in enumerate(self.battles): self.buttons.append(Button((650, 142 + index * 112, 92, 34), "WATCH LIVE", lambda battle=battle: self.open_watch(battle), COLORS["gold"]))

    def advance(self, seconds):
        self.app.store.advance_world(seconds)
        self.refresh()
        self.app.notify("Place simulation advanced by " + str(seconds) + " seconds.")

    def open_watch(self, battle):
        session = self.app.store._world_session(battle)
        if not session:
            self.app.notify("This active place duel has no valid checkpoint.")
            return
        house = battle.get("house") or battle.get("accepted_by") or battle.get("to") or battle.get("from")
        guest = battle.get("guest") or (battle.get("to") if house == battle.get("from") else battle.get("from"))
        battle["house"], battle["guest"] = house, guest
        self.app.push(DuelScene(self.app, guest, "player", battle.get("place"), False, battle, session))

    def participant(self, battle, key):
        identifier = battle.get(key, "")
        return self.app.store.characters.get(identifier)

    def draw_landscape(self, surface, place, night, now):
        image = self.app.assets.place_visual(self.place_id, "landscape", night, now, (W, H), self.media_scope) or self.app.assets.place_visual(self.place_id, "background", night, now, (W, H), self.media_scope) or (self.app.assets.image(place.background, (W, H)) if place and place.background else None)
        if image: ui_blit(surface, image, (0, 0))
        else: surface.fill(COLORS["deep"])
        veil = ui_surface((W, H), pygame.SRCALPHA); veil.fill((20, 28, 58, 78)); ui_blit(surface, veil, (0, 0))
        self.draw_panel(surface, (44, 46, 712, 420), "PLACE LANDSCAPE", COLORS["green"])
        draw_text(surface, place.name if place else self.place_id, (70, 106), self.app.assets.font(24, True), COLORS["cream"])
        draw_text(surface, "DAY" if not night else "NIGHT", (730, 112), self.app.assets.font(14, True), COLORS["gold"], "topright")
        draw_text(surface, "Capacity: " + str(place.capacity if place else 0) + "  |  Active duels: " + str(len(self.battles)), (70, 154), self.app.assets.font(14), COLORS["cyan"])
        draw_text(surface, "Occupancy and activity", (70, 204), self.app.assets.font(14, True), COLORS["green"])
        occupants = [item for item in self.app.store.characters.values() if item.current_place == self.place_id and item.activity in ["dueling", "watching"]]
        if not occupants: draw_text(surface, "No active occupants are currently registered.", (70, 242), self.app.assets.font(13), COLORS["muted"])
        for index, character in enumerate(occupants[:8]):
            role = "watching" if character.activity == "watching" else "dueling"
            draw_text(surface, character.name + "  |  " + role + "  |  " + character.relationship, (70, 242 + index * 28), self.app.assets.font(12), COLORS["cream"])
        draw_text(surface, "Landscape media is place-scoped and follows the deterministic world day/night clock.", (400, 432), self.app.assets.font(10), COLORS["gold"], "center")

    def draw_duels(self, surface, place, night, now):
        ground = self.app.assets.place_visual(self.place_id, "ground", night, now, (W, H), self.media_scope) or (self.app.assets.image(place.background, (W, H)) if place and place.background else None)
        if ground: ui_blit(surface, ground, (0, 0))
        else: surface.fill(COLORS["deep"])
        veil = ui_surface((W, H), pygame.SRCALPHA); veil.fill((20, 28, 58, 92)); ui_blit(surface, veil, (0, 0))
        draw_text(surface, "PLACE DUELS", (34, 28), self.app.assets.font(28, True), COLORS["gold"])
        draw_text(surface, (place.name if place else self.place_id) + "  |  " + ("NIGHT" if night else "DAY") + "  |  live engine tables", (36, 65), self.app.assets.font(13), COLORS["muted"])
        self.draw_panel(surface, (34, 96, 732, 390), "ACTIVE TABLES", COLORS["cyan"])
        if not self.battles: draw_text(surface, "No active duels are currently running at this place.", (400, 278), self.app.assets.font(15), COLORS["muted"], "center")
        for index, battle in enumerate(self.battles):
            y = 132 + index * 112
            session = self.app.store._world_session(battle)
            house = self.participant(battle, "house")
            guest = self.participant(battle, "guest")
            house_name = house.name if house else battle.get("house", "unknown")
            guest_name = guest.name if guest else battle.get("guest", "unknown")
            rounded(surface, (54, y, 570, 92), (132, 94, 73), COLORS["line"], 8, 1)
            draw_text(surface, "TABLE " + str(index + 1) + "   HOUSE  " + house_name + "  VS  " + guest_name, (72, y + 14), self.app.assets.font(14, True), COLORS["cream"])
            hp = session and (str(session.player.hp) + " LP  /  " + str(session.opponent.hp) + " LP") or "checkpoint loading"
            draw_text(surface, "Phase: " + str(battle.get("phase", "duel")) + "  |  Turn: " + str(battle.get("turn", 1)) + "  |  " + hp, (72, y + 42), self.app.assets.font(11), COLORS["cyan"])
            draw_text(surface, "Watchers: " + str(len(battle.get("watchers", []))) + "/6  |  Steps: " + str(len(battle.get("actions", []))) + "  |  House POV retained", (72, y + 66), self.app.assets.font(10), COLORS["muted"])

    def draw(self, surface):
        place = self.app.store.places.get(self.place_id)
        now = float(self.app.store.world.get("simulation_time", 0.0))
        night = self.app.store.clock.period(now) == "night"
        if self.mode == "landscape": self.draw_landscape(surface, place, night, now)
        else: self.draw_duels(surface, place, night, now)
        self.draw_buttons(surface, 10)
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
            snapshot = self.app.store.place_summary(place.id) or {}
            linked = len(snapshot.get("linked_teams", []))
            occupants = len(snapshot.get("occupants", []))
            selected_effect = snapshot.get("team_effect", {}).get("selected", {}) if isinstance(snapshot.get("team_effect", {}), dict) else {}
            effect_label = selected_effect.get("kind", "none") if isinstance(selected_effect, dict) else "none"
            draw_text(surface, "Day/night: " + ("enabled" if place.day_night else "disabled") + "  |  media: " + ("scaffolded" if place.media_folder else "legacy"), (238, y + 75), self.app.assets.font(10), COLORS["muted"])
            draw_text(surface, f"Linked teams: {linked}  |  occupants: {occupants}  |  effect: {effect_label}", (238, y + 91), self.app.assets.font(9), COLORS["gold"] if effect_label != "none" else COLORS["muted"])
            view_button = Button((548, y + 34, 92, 34), "VIEW", lambda place_id=place.id: self.app.push(PlaceDuelViewScene(self.app, place_id)), COLORS["cyan"])
            detail_button = Button((650, y + 34, 92, 34), "DETAIL", lambda place_id=place.id: self.app.push(EntityDetailScene(self.app, "places", place_id)), COLORS["green"])
            self.row_buttons.extend([view_button, detail_button])
            view_button.draw(surface, self.app.assets.font(10, True))
            detail_button.draw(surface, self.app.assets.font(10, True))
        self.draw_buttons(surface, 11)


class PlaceMakerScene(Scene):
    def __init__(self, app, place_id=None):
        super().__init__(app)
        self.place_id = place_id

    def parse_list(self, value):
        return [item.strip().lower() for item in str(value).split(",") if item.strip()]

    def parse_json(self, value):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}

    def enter(self):
        place = self.app.store.places.get(self.place_id) if self.place_id else None
        self.name = TextInput((70, 122, 300, 30), place.name if place else "New Place")
        self.capacity = TextInput((400, 122, 300, 30), str(place.capacity if place else 3))
        self.background = TextInput((70, 160, 630, 30), place.background if place else "")
        self.effects = TextInput((70, 198, 630, 30), ", ".join(place.effects if place else []))
        self.windows = TextInput((70, 236, 630, 30), json.dumps(place.event_window_policies if place else {}, separators=(",", ":")))
        self.logic = TextInput((70, 274, 630, 30), getattr(place, "logic_graph", "") if place else "")
        self.day_night = place.day_night if place else True
        label = "SAVE PLACE" if place else "CREATE PLACE"
        self.buttons = [Button((70, 330, 150, 36), "DAY/NIGHT: " + ("ON" if self.day_night else "OFF"), lambda: self.toggle_day_night(), COLORS["cyan"]), Button((236, 330, 210, 36), label, lambda: self.save_place(), COLORS["green"]), Button((462, 330, 210, 36), "EXPORT PLACE", lambda: self.export(), COLORS["violet"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def toggle_day_night(self):
        self.day_night = not self.day_night
        self.buttons[0].label = "DAY/NIGHT: " + ("ON" if self.day_night else "OFF")

    def export(self):
        if not self.place_id:
            self.app.notify("Save the place before exporting it.")
            return
        path = self.app.store.export_cbp("place", self.place_id, False, True)
        self.app.notify("Exported place package with media and logic dependencies: " + path.name)

    def save_place(self):
        try: capacity = int(self.capacity.value)
        except (TypeError, ValueError): capacity = 3
        values = {"name": self.name.value, "capacity": capacity, "background": self.background.value, "day_night": self.day_night, "effects": self.parse_list(self.effects.value), "event_window_policies": self.parse_json(self.windows.value), "logic_graph": self.logic.value.strip()}
        if self.place_id:
            result = self.app.store.update_place(self.place_id, values)
        else:
            result = self.app.store.create_place(values["name"], values["capacity"], values["background"], values["day_night"])
            if result:
                self.place_id = result.id
                result = self.app.store.update_place(self.place_id, values)
        self.app.store.load()
        self.app.notify("Place definition saved with capacity, effects, event windows, day/night, and media structure." if result else "Place definition could not be saved.")
        self.enter()

    def handle(self, event):
        for field in [self.name, self.capacity, self.background, self.effects, self.windows, self.logic]: field.handle(event)
        super().handle(event)

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "PLACE MAKER / EDITOR", (34, 28), self.app.assets.font(27, True), COLORS["green"])
        draw_text(surface, "Places bind field media, day/night presentation, capacity, event windows, effects, and live occupancy.", (36, 62), self.app.assets.font(11), COLORS["muted"])
        self.draw_panel(surface, (42, 100, 720, 340), "PLACE DEFINITION", COLORS["green"])
        for field, label in [(self.name, "Place name"), (self.capacity, "Capacity, 1 to 10"), (self.background, "Field/background asset key"), (self.effects, "Place effect ids, comma-separated"), (self.windows, "Event-window policy JSON"), (self.logic, "Logic graph id")]: field.draw(surface, self.app.assets.font(10), label)
        draw_text(surface, "The engine scaffolds day/night visuals, music, pre-duel, duel, post-duel, and landscape folders for this place.", (400, 470), self.app.assets.font(10), COLORS["gold"], "center")
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
        self.loans = self.app.store.borrow_list()
        self.rows = [("trade", item) for item in self.deals] + [("borrow", item) for item in self.loans]
        self.buttons = [Button((34, 530, 130, 38), "NEW OFFER", lambda: self.new_offer(), COLORS["orange"]), Button((172, 530, 130, 38), "NEW LOAN", lambda: self.new_borrow(), COLORS["cyan"]), Button((310, 530, 94, 38), "ACCEPT", lambda: self.accept(), COLORS["green"]), Button((412, 530, 94, 38), "COUNTER", lambda: self.counter(), COLORS["gold"]), Button((514, 530, 94, 38), "CANCEL", lambda: self.cancel(), COLORS["red"]), Button((616, 530, 138, 38), "ESCALATE", lambda: self.escalate(), COLORS["violet"]), Button((650, 575, 110, 24), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def selected(self):
        for kind, item in self.rows:
            if item.get("id") == self.selected_id: return item
        return None

    def selected_kind(self):
        for kind, item in self.rows:
            if item.get("id") == self.selected_id: return kind
        return ""

    def new_offer(self):
        roles = self.app.store.role_config()
        library = self.app.store.characters[roles["player_character"]].library_cards
        if not library:
            self.app.notify("The player library has no cards to offer.")
            return
        trade = self.app.store.create_trade(roles["player_character"], roles["default_opponent_character"], [library[0]], requested_family="aqua")
        self.selected_id = trade["id"] if trade else ""
        recipient_name = self.app.store.characters[roles["default_opponent_character"]].name
        self.app.notify(f"A three-hour type-based offer was created for {recipient_name}." if trade else "The recipient or offered card is currently unavailable.")
        self.refresh()

    def new_borrow(self):
        roles = self.app.store.role_config()
        borrower = roles["player_character"]
        candidates = [item for item in self.app.store.characters.values() if item.id != borrower and self.app.store.social_available(item.id) and (self.app.store.relationship_for(borrower, item.id) == "ally" or self.app.store.shared_team(borrower, item.id))]
        candidates.sort(key=lambda item: (self.app.store._relationship_score(self.app.store.characters[borrower], item), item.id), reverse=True)
        for lender in candidates:
            card_id = next((card for card in lender.library_cards if self.app.store.available_card_counts(lender.id).get(card, 0) > 0), "")
            if not card_id: continue
            record = self.app.store.create_borrow_request(lender.id, borrower, card_id, 3, self.app.store.characters[borrower].deck_id)
            if record:
                self.selected_id = record["id"]
                self.app.notify(f"A consent-based three-duel loan request was sent to {lender.name}.")
                self.refresh()
                return
        self.app.notify("No allied lender has an available card that fits the player deck.")

    def accept(self):
        item = self.selected()
        if not item:
            self.app.notify("Select an interaction first.")
        elif self.selected_kind() == "borrow":
            success = self.app.store.respond_borrow_request(item["id"], self.app.store.role_config()["player_character"], "accept")
            self.app.notify("Loan accepted and added to the borrower’s temporary deck source." if success else "This loan requires lender consent and current availability.")
        else:
            success = self.app.store.accept_trade(item["id"], self.app.store.role_config()["player_character"])
            self.app.notify("Trade accepted and card ownership transferred." if success else "This trade cannot be accepted: cards may be unavailable or the request is unsatisfied.")
        self.refresh()

    def counter(self):
        trade = self.selected()
        if not trade or self.selected_kind() != "trade": self.app.notify("Select an open trade first."); return
        library = self.app.store.characters[trade["recipient"]].library_cards
        if not library:
            self.app.notify("The recipient has no card available for a counteroffer.")
            return
        counter = self.app.store.counter_trade(trade["id"], trade["recipient"], [library[0]], requested_family="warrior")
        self.selected_id = counter["id"] if counter else self.selected_id
        self.app.notify("A persistent counteroffer was created." if counter else "Counteroffer rejected by the trade rules.")
        self.refresh()

    def cancel(self):
        item = self.selected()
        actor = self.app.store.role_config()["player_character"]
        if self.selected_kind() == "borrow": success = bool(item and self.app.store.respond_borrow_request(item["id"], actor, "cancel"))
        else: success = bool(item and self.app.store.cancel_trade(item["id"], actor))
        self.app.notify("Interaction canceled." if success else "Only an active interaction can be canceled.")
        self.refresh()

    def escalate(self):
        trade = self.selected()
        request_id = self.app.store.escalate_trade(trade["id"], self.app.store.role_config()["player_character"]) if trade and self.selected_kind() == "trade" else None
        if request_id and trade:
            self.app.notify(f"Trade escalated into duel request {request_id}.")
            self.app.push(PreDuelScene(self.app, trade["recipient"]))
        else:
            self.app.notify("This trade cannot be escalated.")
        self.refresh()

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, (kind, item) in enumerate(self.rows[-4:]):
                if pygame.Rect(46, 125 + index * 90, 708, 68).collidepoint(event.pos): self.selected_id = item["id"]

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "TRADING", (34, 28), self.app.assets.font(28, True), COLORS["orange"])
        draw_text(surface, "Real-time offers and consent-based loans use relationship, availability, and transactional card state.", (36, 65), self.app.assets.font(13), COLORS["muted"])
        visible = self.rows[-4:]
        for index, (kind, item) in enumerate(visible):
            y = 125 + index * 90
            accent = COLORS["gold"] if item["id"] == self.selected_id else COLORS["cyan"] if kind == "borrow" else COLORS["orange"]
            rounded(surface, (46, y, 708, 68), (15, 28, 58), accent, 8, 2 if item["id"] == self.selected_id else 1)
            if kind == "borrow":
                lender = self.app.store.characters.get(item.get("lender"))
                borrower = self.app.store.characters.get(item.get("borrower"))
                title = f"LOAN  {lender.name if lender else item.get('lender')} -> {borrower.name if borrower else item.get('borrower')}  |  {item.get('state', '').upper()}"
                detail = f"Card: {self.app.store.card_names([item.get('card_id', '')])}    Duels remaining: {item.get('remaining_duels', 0)}"
            else:
                creator = self.app.store.characters.get(item.get("creator"))
                recipient = self.app.store.characters.get(item.get("recipient"))
                title = f"TRADE  {creator.name if creator else item.get('creator')} -> {recipient.name if recipient else item.get('recipient')}  |  {item.get('state', '').upper()}"
                requested = self.app.store.card_names(item.get("requested_cards", [])) if item.get("requested_cards") else "family: " + (item.get("requested_family") or "any")
                detail = f"Gives: {self.app.store.card_names(item.get('offered_cards', []))}    Wants: {requested}"
            draw_text(surface, title, (64, y + 13), self.app.assets.font(13, True), COLORS["cream"])
            draw_text(surface, detail, (64, y + 39), self.app.assets.font(11), COLORS["muted"])
        selected = self.selected()
        if selected:
            history = selected.get("history", selected.get("events", []))[-2:]
            draw_text(surface, "NEGOTIATION: " + "  |  ".join(item.get("action", "event") for item in history), (400, 505), self.app.assets.font(11), COLORS["cyan"], "center")
        else:
            draw_text(surface, "Select a trade or loan row to negotiate.", (400, 505), self.app.assets.font(11), COLORS["muted"], "center")
        self.draw_buttons(surface, 11)
        self.app.draw_notice(surface)


class ImportExportScene(Scene):
    policies = ["replace", "skip", "reject"]

    def enter(self):
        self.files = sorted((DATA / "exports").glob("*.cbp"))
        self.selected_path = self.files[-1] if self.files else None
        self.preview = self.app.store.package_preview(self.selected_path) if self.selected_path else None
        self.policy = "replace"
        self.buttons = [Button((54, 145, 250, 40), "EXPORT WORLD .CBP", lambda: self.export_world(), COLORS["cyan"]), Button((54, 195, 250, 40), "SCAN / PREVIEW LATEST", lambda: self.scan(), COLORS["violet"]), Button((54, 245, 250, 40), "IMPORT SELECTED ALL", lambda: self.import_latest(), COLORS["green"]), Button((54, 295, 250, 40), "IMPORT CONTENT ONLY", lambda: self.import_latest(["cards", "characters", "decks", "places", "teams", "logic"]), COLORS["gold"]), Button((54, 345, 250, 40), "CONFLICT: REPLACE", lambda: self.cycle_policy(), COLORS["orange"]), Button((650, 530, 110, 38), "BACK", lambda: self.app.pop(), COLORS["muted"])]

    def scan(self):
        self.files = sorted((DATA / "exports").glob("*.cbp"))
        self.selected_path = self.files[-1] if self.files else None
        self.preview = self.app.store.package_preview(self.selected_path) if self.selected_path else None
        self.app.notify("Package preview loaded." if self.preview else "No .cbp package is available in data/exports/.")
        self.enter()

    def cycle_policy(self):
        self.policy = self.policies[(self.policies.index(self.policy) + 1) % len(self.policies)]
        self.buttons[4].label = "CONFLICT: " + self.policy.upper()

    def import_latest(self, include=None):
        if not self.selected_path or not self.preview:
            self.scan()
            return
        result = self.app.store.import_cbp(self.selected_path, include, False, self.policy)
        if result.get("rejected"):
            self.app.notify("Import rejected because existing ids conflict with the selected package.")
            return
        self.app.notify("Imported selected package categories: " + ", ".join(result.get("imported", [])) + " using " + self.policy + ".")
        self.enter()

    def export_world(self):
        path = self.app.store.export_cbp("world", "cbp_world")
        self.enter()
        self.app.notify(f"Exported {path.name} with manifest, registries, dependencies, and optional world state.")

    def draw(self, surface):
        surface.fill(COLORS["deep"])
        draw_text(surface, "IMPORT / EXPORT", (34, 28), self.app.assets.font(28, True), COLORS["violet"])
        draw_text(surface, "Preview a dependency-scoped .cbp package before selecting categories and conflict behavior.", (36, 65), self.app.assets.font(12), COLORS["muted"])
        self.draw_panel(surface, (36, 112, 280, 322), "PACKAGE FILES", COLORS["violet"])
        for index, path in enumerate(self.files[-5:]):
            color = COLORS["gold"] if path == self.selected_path else COLORS["muted"]
            draw_text(surface, path.name[:34], (54, 155 + index * 32), self.app.assets.font(10, True if path == self.selected_path else False), color)
        self.draw_panel(surface, (344, 112, 420, 322), "MANIFEST PREVIEW", COLORS["cyan"])
        if self.preview:
            manifest = self.preview["manifest"]
            draw_text(surface, f"Schema {manifest.get('schema', 0)}  |  {manifest.get('kind', 'unknown').upper()}", (372, 150), self.app.assets.font(14, True), COLORS["cream"])
            draw_text(surface, "Dependencies: " + ("included" if manifest.get("dependencies_included") else "excluded"), (372, 177), self.app.assets.font(11), COLORS["muted"])
            draw_text(surface, "Experience: " + ("included" if manifest.get("experience_included") else "excluded"), (372, 199), self.app.assets.font(11), COLORS["muted"])
            y = 235
            for category, count in self.preview["counts"].items():
                conflicts = len(self.preview["conflicts"].get(category, []))
                draw_text(surface, f"{category}: {count}  | conflicts: {conflicts}", (372, y), self.app.assets.font(11), COLORS["cyan"] if not conflicts else COLORS["orange"])
                y += 25
            draw_text(surface, "Import remains explicit; world state is never merged implicitly.", (554, 400), self.app.assets.font(9), COLORS["gold"], "center")
        else:
            draw_text(surface, "Scan a .cbp package to preview its manifest.", (554, 270), self.app.assets.font(15), COLORS["muted"], "center")
        self.draw_buttons(surface, 11)
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
        if self.scenes: self.scenes[-1].leave()
        self.scenes.append(scene)
        scene.enter()

    def pop(self):
        if len(self.scenes) > 1:
            old = self.scenes.pop()
            old.leave()
            self.scenes[-1].enter()

    def replace(self, scene):
        for old in self.scenes: old.leave()
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
                self.simulation_accumulator -= 1.0
                self.store.advance_world()
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
