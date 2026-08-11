from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectSlider
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    AntialiasAttrib,
    AudioSound,
    ClockObject,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    Shader,
    TextNode,
    TransparencyAttrib,
    Vec3,
    Vec4,
    loadPrcFileData,
)


loadPrcFileData(
    "",
    "\n".join(
        [
            "window-title Python 3.9 卡通俯视射击游戏原型",
            "win-size 1280 720",
            "sync-video true",
            "show-frame-rate-meter false",
            "textures-power-2 none",
            "framebuffer-multisample 1",
            "multisamples 4",
            "audio-library-name p3openal_audio",
        ]
    ),
)


BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "assets" / "audio"
SETTINGS_FILE = BASE_DIR / "settings.json"


@dataclass(frozen=True)
class AABB2:
    """二维轴对齐碰撞盒，仅用于地面移动和子弹碰撞。"""

    x: float
    y: float
    half_x: float
    half_y: float

    def intersects_circle(self, px: float, py: float, radius: float) -> bool:
        closest_x = max(self.x - self.half_x, min(px, self.x + self.half_x))
        closest_y = max(self.y - self.half_y, min(py, self.y + self.half_y))
        dx = px - closest_x
        dy = py - closest_y
        return dx * dx + dy * dy < radius * radius


@dataclass
class Collectible:
    node: NodePath
    base_z: float
    phase: float


@dataclass
class Enemy:
    node: NodePath
    start: Vec3
    end: Vec3
    speed: float
    progress: float = 0.0
    direction: float = 1.0
    hp: int = 3
    active: bool = True


@dataclass
class Bullet:
    node: NodePath
    velocity: Vec3
    life: float


@dataclass
class EffectParticle:
    node: NodePath
    velocity: Vec3
    age: float
    life: float
    gravity: float
    spin: float
    initial_scale: float


def make_cube(name: str, color: Vec4) -> NodePath:
    """创建一个中心位于原点、边长为 1 的硬边彩色立方体。"""

    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vertices = GeomVertexWriter(vdata, "vertex")
    normals = GeomVertexWriter(vdata, "normal")
    colors = GeomVertexWriter(vdata, "color")

    faces: List[Tuple[Vec3, Tuple[Vec3, Vec3, Vec3, Vec3]]] = [
        (Vec3(0, -1, 0), (Vec3(-0.5, -0.5, -0.5), Vec3(0.5, -0.5, -0.5), Vec3(0.5, -0.5, 0.5), Vec3(-0.5, -0.5, 0.5))),
        (Vec3(0, 1, 0), (Vec3(0.5, 0.5, -0.5), Vec3(-0.5, 0.5, -0.5), Vec3(-0.5, 0.5, 0.5), Vec3(0.5, 0.5, 0.5))),
        (Vec3(-1, 0, 0), (Vec3(-0.5, 0.5, -0.5), Vec3(-0.5, -0.5, -0.5), Vec3(-0.5, -0.5, 0.5), Vec3(-0.5, 0.5, 0.5))),
        (Vec3(1, 0, 0), (Vec3(0.5, -0.5, -0.5), Vec3(0.5, 0.5, -0.5), Vec3(0.5, 0.5, 0.5), Vec3(0.5, -0.5, 0.5))),
        (Vec3(0, 0, -1), (Vec3(-0.5, 0.5, -0.5), Vec3(0.5, 0.5, -0.5), Vec3(0.5, -0.5, -0.5), Vec3(-0.5, -0.5, -0.5))),
        (Vec3(0, 0, 1), (Vec3(-0.5, -0.5, 0.5), Vec3(0.5, -0.5, 0.5), Vec3(0.5, 0.5, 0.5), Vec3(-0.5, 0.5, 0.5))),
    ]

    triangles = GeomTriangles(Geom.UHStatic)
    index = 0
    for normal, points in faces:
        for point in points:
            vertices.addData3(point)
            normals.addData3(normal)
            colors.addData4(color)
        triangles.addVertices(index, index + 1, index + 2)
        triangles.addVertices(index, index + 2, index + 3)
        index += 4

    geom = Geom(vdata)
    geom.addPrimitive(triangles)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def attach_cube(
    parent: NodePath,
    name: str,
    position: Tuple[float, float, float],
    scale: Tuple[float, float, float],
    color: Vec4,
) -> NodePath:
    cube = make_cube(name, color)
    cube.reparentTo(parent)
    cube.setPos(*position)
    cube.setScale(*scale)
    return cube


class CartoonTopDownGame(ShowBase):
    PLAYER_SPEED = 7.0
    PLAYER_RADIUS = 0.55
    WORLD_LIMIT = 17.5

    BULLET_SPEED = 24.0
    BULLET_LIFETIME = 1.25
    FIRE_INTERVAL = 0.16

    def __init__(self) -> None:
        super().__init__()
        self.disableMouse()
        self.render.setAntialias(AntialiasAttrib.MAuto)
        self.setBackgroundColor(0.55, 0.78, 0.92, 1.0)
        self.camLens.setFov(48)
        self.camLens.setNearFar(0.1, 200.0)

        self.clock = ClockObject.getGlobalClock()
        self.keys: Dict[str, bool] = {key: False for key in ("w", "a", "s", "d")}
        self.shooting = False
        self.paused = False
        self.settings_open = False
        self.game_over = False

        self.obstacles: List[AABB2] = []
        self.collectibles: List[Collectible] = []
        self.enemies: List[Enemy] = []
        self.bullets: List[Bullet] = []
        self.effects: List[EffectParticle] = []

        self.score = 0
        self.enemies_defeated = 0
        self.fire_cooldown = 0.0
        self.camera_shake = 0.0

        self.music_volume = 0.45
        self.sfx_volume = 0.75
        self._load_settings()

        self.music: Optional[AudioSound] = None
        self.shoot_sounds: List[AudioSound] = []
        self.hit_sounds: List[AudioSound] = []
        self.pickup_sounds: List[AudioSound] = []
        self._shoot_sound_index = 0
        self._hit_sound_index = 0
        self._pickup_sound_index = 0

        self._install_toon_shader()
        self._bind_inputs()
        self._build_world()
        self._build_player()
        self._setup_audio()
        self._build_ui()
        self._build_pause_menu()

        self.camera.setPos(0, -17, 19)
        self.camera.lookAt(self.player.getPos() + Vec3(0, 0, 1.2))

        self.taskMgr.add(self.update, "game-update")

    # ------------------------------------------------------------------
    # 设置与音频
    # ------------------------------------------------------------------
    def _load_settings(self) -> None:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.music_volume = max(0.0, min(1.0, float(data.get("music_volume", self.music_volume))))
            self.sfx_volume = max(0.0, min(1.0, float(data.get("sfx_volume", self.sfx_volume))))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def _save_settings(self) -> None:
        data = {
            "music_volume": round(self.music_volume, 3),
            "sfx_volume": round(self.sfx_volume, 3),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"无法保存设置：{exc}")

    def _setup_audio(self) -> None:
        try:
            music_path = AUDIO_DIR / "cartoon_bgm.wav"
            shoot_path = AUDIO_DIR / "shoot.wav"
            hit_path = AUDIO_DIR / "hit.wav"
            pickup_path = AUDIO_DIR / "pickup.wav"

            if music_path.exists():
                self.music = self.loader.loadMusic(str(music_path))
                self.music.setLoop(True)
                self.music.setVolume(self.music_volume)
                self.music.play()

            if shoot_path.exists():
                self.shoot_sounds = [self.loader.loadSfx(str(shoot_path)) for _ in range(6)]
            if hit_path.exists():
                self.hit_sounds = [self.loader.loadSfx(str(hit_path)) for _ in range(4)]
            if pickup_path.exists():
                self.pickup_sounds = [self.loader.loadSfx(str(pickup_path)) for _ in range(3)]

            self._apply_sfx_volume()
        except Exception as exc:  # 音频设备不可用时，游戏仍可继续运行。
            print(f"音频初始化失败，游戏将静音运行：{exc}")
            self.music = None
            self.shoot_sounds = []
            self.hit_sounds = []
            self.pickup_sounds = []

    def _apply_sfx_volume(self) -> None:
        for sound in self.shoot_sounds + self.hit_sounds + self.pickup_sounds:
            sound.setVolume(self.sfx_volume)

    @staticmethod
    def _play_from_pool(pool: List[AudioSound], index: int) -> int:
        if not pool:
            return index
        sound = pool[index % len(pool)]
        sound.stop()
        sound.play()
        return (index + 1) % len(pool)

    def _play_shoot_sound(self) -> None:
        self._shoot_sound_index = self._play_from_pool(self.shoot_sounds, self._shoot_sound_index)

    def _play_hit_sound(self) -> None:
        self._hit_sound_index = self._play_from_pool(self.hit_sounds, self._hit_sound_index)

    def _play_pickup_sound(self) -> None:
        self._pickup_sound_index = self._play_from_pool(self.pickup_sounds, self._pickup_sound_index)

    # ------------------------------------------------------------------
    # 渲染与输入
    # ------------------------------------------------------------------
    def _install_toon_shader(self) -> None:
        vertex_shader = r"""
            #version 130
            uniform mat4 p3d_ModelViewProjectionMatrix;
            uniform mat4 p3d_ModelMatrix;
            in vec4 p3d_Vertex;
            in vec3 p3d_Normal;
            in vec4 p3d_Color;
            out vec3 world_normal;
            out vec4 vertex_color;

            void main() {
                gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
                world_normal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
                vertex_color = p3d_Color;
            }
        """
        fragment_shader = r"""
            #version 130
            uniform vec3 light_direction;
            in vec3 world_normal;
            in vec4 vertex_color;
            out vec4 frag_color;

            void main() {
                float diffuse = max(dot(normalize(world_normal), normalize(-light_direction)), 0.0);
                float band;
                if (diffuse < 0.25) {
                    band = 0.48;
                } else if (diffuse < 0.65) {
                    band = 0.76;
                } else {
                    band = 1.0;
                }
                vec3 ambient = vertex_color.rgb * 0.18;
                frag_color = vec4(ambient + vertex_color.rgb * band * 0.82, vertex_color.a);
            }
        """
        shader = Shader.make(Shader.SL_GLSL, vertex=vertex_shader, fragment=fragment_shader)
        self.render.setShader(shader)
        self.render.setShaderInput("light_direction", Vec3(-0.7, -1.0, -1.8))

    def _bind_inputs(self) -> None:
        for key in self.keys:
            self.accept(key, self._set_key, [key, True])
            self.accept(f"{key}-up", self._set_key, [key, False])

        self.accept("mouse1", self._set_shooting, [True])
        self.accept("mouse1-up", self._set_shooting, [False])
        self.accept("space", self._set_shooting, [True])
        self.accept("space-up", self._set_shooting, [False])

        self.accept("escape", self._handle_escape)
        self.accept("r", self.reset_game)

    def _set_key(self, key: str, value: bool) -> None:
        self.keys[key] = value

    def _set_shooting(self, value: bool) -> None:
        self.shooting = value

    def _handle_escape(self) -> None:
        if self.settings_open:
            self._show_pause_main()
        elif self.paused:
            self.resume_game()
        else:
            self.pause_game()

    # ------------------------------------------------------------------
    # 世界、角色和敌人
    # ------------------------------------------------------------------
    def _build_world(self) -> None:
        attach_cube(self.render, "ground", (0, 0, -0.45), (38, 38, 0.8), Vec4(0.34, 0.68, 0.34, 1))
        attach_cube(self.render, "road", (0, 0, 0.015), (7.0, 35.0, 0.06), Vec4(0.80, 0.72, 0.55, 1))

        self._add_obstacle(-9.5, 4.0, 4.0, 3.0, 3.5, Vec4(0.88, 0.50, 0.32, 1))
        self._add_obstacle(10.0, -3.5, 3.4, 4.2, 4.5, Vec4(0.45, 0.60, 0.90, 1))
        self._add_obstacle(-7.5, -10.0, 5.2, 1.0, 1.4, Vec4(0.93, 0.83, 0.48, 1))
        self._add_obstacle(8.0, 10.0, 4.8, 1.0, 1.4, Vec4(0.93, 0.83, 0.48, 1))

        random.seed(7)
        for index in range(16):
            while True:
                x = random.uniform(-15.5, 15.5)
                y = random.uniform(-15.5, 15.5)
                if abs(x) < 4.3 or math.hypot(x, y) < 4.0:
                    continue
                if any(box.intersects_circle(x, y, 1.6) for box in self.obstacles):
                    continue
                break
            self._add_tree(x, y, index)

        positions = [(-2, 7), (2, 12), (-1, -8), (4.5, -13), (0, 15), (-3, -14)]
        for index, (x, y) in enumerate(positions):
            self._add_collectible(x, y, index)

        self._add_enemy((-4.5, 3.0, 0.6), (4.5, 3.0, 0.6), 0)
        self._add_enemy((-3.5, -5.5, 0.6), (3.5, -5.5, 0.6), 1)
        self._add_enemy((-4.0, 10.0, 0.6), (3.0, 10.0, 0.6), 2)

    def _add_obstacle(
        self,
        x: float,
        y: float,
        size_x: float,
        size_y: float,
        height: float,
        color: Vec4,
    ) -> None:
        attach_cube(self.render, "obstacle", (x, y, height / 2), (size_x, size_y, height), color)
        self.obstacles.append(AABB2(x, y, size_x / 2 + 0.15, size_y / 2 + 0.15))

    def _add_tree(self, x: float, y: float, index: int) -> None:
        root = self.render.attachNewNode(f"tree-{index}")
        root.setPos(x, y, 0)
        attach_cube(root, "trunk", (0, 0, 0.9), (0.65, 0.65, 1.8), Vec4(0.48, 0.28, 0.13, 1))
        crown = attach_cube(root, "crown", (0, 0, 2.35), (2.0, 2.0, 1.7), Vec4(0.20, 0.56, 0.24, 1))
        crown.setH(random.uniform(-20, 20))
        self.obstacles.append(AABB2(x, y, 0.7, 0.7))

    def _add_collectible(self, x: float, y: float, index: int) -> None:
        root = self.render.attachNewNode(f"collectible-{index}")
        root.setPos(x, y, 1.0)
        crystal = attach_cube(root, "crystal", (0, 0, 0), (0.55, 0.55, 1.1), Vec4(0.35, 0.95, 1.0, 1))
        crystal.setHpr(45, 0, 45)
        self.collectibles.append(Collectible(root, 1.0, index * 0.9))

    def _add_enemy(self, start: Tuple[float, float, float], end: Tuple[float, float, float], index: int) -> None:
        root = self.render.attachNewNode(f"enemy-{index}")
        root.setPos(*start)
        attach_cube(root, "enemy-body", (0, 0, 0.55), (1.0, 0.85, 1.1), Vec4(0.88, 0.25, 0.28, 1))
        attach_cube(root, "enemy-head", (0, 0.05, 1.45), (0.75, 0.75, 0.7), Vec4(1.0, 0.62, 0.38, 1))
        attach_cube(root, "enemy-eye-left", (-0.20, 0.40, 1.52), (0.12, 0.08, 0.12), Vec4(0.08, 0.08, 0.10, 1))
        attach_cube(root, "enemy-eye-right", (0.20, 0.40, 1.52), (0.12, 0.08, 0.12), Vec4(0.08, 0.08, 0.10, 1))
        self.enemies.append(Enemy(root, Vec3(*start), Vec3(*end), speed=0.28 + index * 0.04))

    def _build_player(self) -> None:
        self.player = self.render.attachNewNode("player")
        self.player.setPos(0, 0, 0.05)

        shadow = attach_cube(self.player, "shadow", (0, 0, 0.02), (1.35, 1.0, 0.035), Vec4(0.02, 0.03, 0.04, 0.32))
        shadow.setTransparency(TransparencyAttrib.MAlpha)

        attach_cube(self.player, "body", (0, 0, 0.85), (0.9, 0.75, 1.25), Vec4(0.22, 0.48, 0.92, 1))
        attach_cube(self.player, "head", (0, 0.05, 1.75), (0.78, 0.78, 0.68), Vec4(1.0, 0.73, 0.52, 1))
        attach_cube(self.player, "backpack", (0, -0.44, 0.95), (0.62, 0.30, 0.75), Vec4(0.98, 0.68, 0.20, 1))

        # 简单卡通枪械，朝玩家局部 +Y 方向。
        attach_cube(self.player, "gun-body", (0.38, 0.47, 1.05), (0.24, 0.85, 0.22), Vec4(0.18, 0.20, 0.25, 1))
        attach_cube(self.player, "gun-accent", (0.38, 0.67, 1.05), (0.28, 0.22, 0.28), Vec4(0.98, 0.72, 0.18, 1))
        self.muzzle = self.player.attachNewNode("muzzle")
        self.muzzle.setPos(0.38, 0.95, 1.05)

    # ------------------------------------------------------------------
    # HUD 与暂停设置菜单
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.score_text = OnscreenText(
            text="水晶：0 / 6",
            pos=(-1.30, 0.90),
            scale=0.055,
            fg=(1, 1, 1, 1),
            align=TextNode.ALeft,
            shadow=(0, 0, 0, 0.55),
            mayChange=True,
        )
        self.enemy_text = OnscreenText(
            text="击败敌人：0 / 3",
            pos=(-1.30, 0.82),
            scale=0.050,
            fg=(1, 0.94, 0.82, 1),
            align=TextNode.ALeft,
            shadow=(0, 0, 0, 0.55),
            mayChange=True,
        )
        self.help_text = OnscreenText(
            text="WASD 移动  ·  鼠标左键/空格 射击  ·  R 重开  ·  ESC 菜单",
            pos=(0, -0.92),
            scale=0.040,
            fg=(1, 1, 1, 0.92),
            align=TextNode.ACenter,
            shadow=(0, 0, 0, 0.55),
        )
        self.message_text = OnscreenText(
            text="",
            pos=(0, 0.18),
            scale=0.078,
            fg=(1.0, 0.96, 0.58, 1),
            align=TextNode.ACenter,
            shadow=(0, 0, 0, 0.65),
            mayChange=True,
        )

    def _build_pause_menu(self) -> None:
        self.pause_overlay = DirectFrame(
            parent=self.aspect2d,
            frameColor=(0.015, 0.025, 0.045, 0.72),
            frameSize=(-1.85, 1.85, -1, 1),
            relief=DGG.FLAT,
            sortOrder=0,
        )
        self.pause_panel = DirectFrame(
            parent=self.aspect2d,
            frameColor=(0.08, 0.11, 0.17, 0.97),
            frameSize=(-0.58, 0.58, -0.68, 0.68),
            relief=DGG.FLAT,
            sortOrder=10,
        )

        self.pause_main = DirectFrame(parent=self.pause_panel, frameColor=(0, 0, 0, 0), frameSize=(-0.55, 0.55, -0.65, 0.65))
        OnscreenText(
            parent=self.pause_main,
            text="游戏暂停",
            pos=(0, 0.47),
            scale=0.085,
            fg=(1, 0.95, 0.78, 1),
            align=TextNode.ACenter,
        )
        OnscreenText(
            parent=self.pause_main,
            text="ESC 继续游戏",
            pos=(0, 0.34),
            scale=0.040,
            fg=(0.75, 0.82, 0.92, 1),
            align=TextNode.ACenter,
        )

        button_common = {
            "scale": 0.060,
            "frameSize": (-4.8, 4.8, -0.75, 0.95),
            "frameColor": (0.18, 0.32, 0.55, 1),
            "text_fg": (1, 1, 1, 1),
            "relief": DGG.RAISED,
            "pressEffect": True,
        }
        DirectButton(parent=self.pause_main, text="继续游戏", pos=(0, 0, 0.14), command=self.resume_game, **button_common)
        DirectButton(parent=self.pause_main, text="设置", pos=(0, 0, -0.06), command=self._show_settings, **button_common)
        DirectButton(
            parent=self.pause_main,
            text="退出游戏",
            pos=(0, 0, -0.26),
            command=self.userExit,
            scale=0.060,
            frameSize=(-4.8, 4.8, -0.75, 0.95),
            frameColor=(0.58, 0.20, 0.22, 1),
            text_fg=(1, 1, 1, 1),
            relief=DGG.RAISED,
            pressEffect=True,
        )

        self.settings_panel = DirectFrame(parent=self.pause_panel, frameColor=(0, 0, 0, 0), frameSize=(-0.55, 0.55, -0.65, 0.65))
        OnscreenText(
            parent=self.settings_panel,
            text="声音设置",
            pos=(0, 0.49),
            scale=0.078,
            fg=(1, 0.95, 0.78, 1),
            align=TextNode.ACenter,
        )

        OnscreenText(
            parent=self.settings_panel,
            text="背景音乐音量",
            pos=(-0.43, 0.29),
            scale=0.047,
            fg=(0.92, 0.95, 1, 1),
            align=TextNode.ALeft,
        )
        self.music_value_text = OnscreenText(
            parent=self.settings_panel,
            text=f"{round(self.music_volume * 100)}%",
            pos=(0.43, 0.29),
            scale=0.047,
            fg=(0.92, 0.95, 1, 1),
            align=TextNode.ARight,
            mayChange=True,
        )
        self.music_slider = DirectSlider(
            parent=self.settings_panel,
            range=(0.0, 1.0),
            value=self.music_volume,
            pageSize=0.05,
            pos=(0, 0, 0.18),
            scale=0.43,
            frameSize=(-1.0, 1.0, -0.10, 0.10),
            frameColor=(0.20, 0.25, 0.34, 1),
            thumb_frameColor=(0.98, 0.72, 0.18, 1),
            thumb_relief=DGG.RAISED,
        )
        self.music_slider["command"] = self._on_music_volume_changed

        OnscreenText(
            parent=self.settings_panel,
            text="射击与效果音量",
            pos=(-0.43, -0.01),
            scale=0.047,
            fg=(0.92, 0.95, 1, 1),
            align=TextNode.ALeft,
        )
        self.sfx_value_text = OnscreenText(
            parent=self.settings_panel,
            text=f"{round(self.sfx_volume * 100)}%",
            pos=(0.43, -0.01),
            scale=0.047,
            fg=(0.92, 0.95, 1, 1),
            align=TextNode.ARight,
            mayChange=True,
        )
        self.sfx_slider = DirectSlider(
            parent=self.settings_panel,
            range=(0.0, 1.0),
            value=self.sfx_volume,
            pageSize=0.05,
            pos=(0, 0, -0.12),
            scale=0.43,
            frameSize=(-1.0, 1.0, -0.10, 0.10),
            frameColor=(0.20, 0.25, 0.34, 1),
            thumb_frameColor=(0.98, 0.72, 0.18, 1),
            thumb_relief=DGG.RAISED,
        )
        self.sfx_slider["command"] = self._on_sfx_volume_changed

        DirectButton(
            parent=self.settings_panel,
            text="返回",
            pos=(0, 0, -0.40),
            command=self._show_pause_main,
            scale=0.058,
            frameSize=(-4.0, 4.0, -0.75, 0.95),
            frameColor=(0.18, 0.32, 0.55, 1),
            text_fg=(1, 1, 1, 1),
            relief=DGG.RAISED,
        )

        self.pause_overlay.hide()
        self.pause_panel.hide()
        self.settings_panel.hide()

    def _on_music_volume_changed(self) -> None:
        self.music_volume = float(self.music_slider["value"])
        self.music_value_text.setText(f"{round(self.music_volume * 100)}%")
        if self.music is not None:
            self.music.setVolume(self.music_volume)
        self._save_settings()

    def _on_sfx_volume_changed(self) -> None:
        self.sfx_volume = float(self.sfx_slider["value"])
        self.sfx_value_text.setText(f"{round(self.sfx_volume * 100)}%")
        self._apply_sfx_volume()
        self._save_settings()

    def pause_game(self) -> None:
        self.paused = True
        self.settings_open = False
        self.shooting = False
        for key in self.keys:
            self.keys[key] = False
        self.pause_overlay.show()
        self.pause_panel.show()
        self._show_pause_main()

    def resume_game(self) -> None:
        self.paused = False
        self.settings_open = False
        self.pause_overlay.hide()
        self.pause_panel.hide()

    def _show_settings(self) -> None:
        self.settings_open = True
        self.pause_main.hide()
        self.settings_panel.show()

    def _show_pause_main(self) -> None:
        self.settings_open = False
        self.settings_panel.hide()
        self.pause_main.show()

    # ------------------------------------------------------------------
    # 射击、命中和粒子特效
    # ------------------------------------------------------------------
    def _player_forward(self) -> Vec3:
        heading = math.radians(self.player.getH())
        return Vec3(-math.sin(heading), math.cos(heading), 0)

    def _fire_weapon(self) -> None:
        forward = self._player_forward()
        muzzle_pos = self.muzzle.getPos(self.render)

        bullet_node = attach_cube(
            self.render,
            "bullet",
            (muzzle_pos.x, muzzle_pos.y, muzzle_pos.z),
            (0.12, 0.48, 0.12),
            Vec4(1.0, 0.86, 0.20, 1),
        )
        bullet_node.setH(self.player.getH())
        self.bullets.append(Bullet(bullet_node, forward * self.BULLET_SPEED, self.BULLET_LIFETIME))

        # 枪口闪光：三个快速缩小的橙黄色粒子。
        for offset in (-0.14, 0.0, 0.14):
            flash_pos = muzzle_pos + Vec3(offset, 0, 0)
            flash = attach_cube(
                self.render,
                "muzzle-flash",
                (flash_pos.x, flash_pos.y, flash_pos.z),
                (0.24, 0.34, 0.24),
                Vec4(1.0, 0.55 + random.random() * 0.25, 0.08, 1),
            )
            flash.setH(self.player.getH() + random.uniform(-18, 18))
            self.effects.append(EffectParticle(flash, forward * random.uniform(1.0, 2.2), 0.0, 0.085, 0.0, 180.0, 1.0))

        self.camera_shake = max(self.camera_shake, 0.12)
        self._play_shoot_sound()

    def _spawn_hit_sparks(self, position: Vec3, strong: bool = False) -> None:
        count = 12 if strong else 7
        for _ in range(count):
            velocity = Vec3(
                random.uniform(-3.6, 3.6),
                random.uniform(-3.6, 3.6),
                random.uniform(1.2, 5.0),
            )
            color = Vec4(1.0, random.uniform(0.35, 0.85), 0.08, 1)
            spark = attach_cube(
                self.render,
                "hit-spark",
                (position.x, position.y, position.z),
                (0.10, 0.10, 0.10),
                color,
            )
            life = random.uniform(0.22, 0.45) if not strong else random.uniform(0.35, 0.65)
            self.effects.append(EffectParticle(spark, velocity, 0.0, life, 8.5, random.uniform(-420, 420), 1.0))

        if strong:
            burst = attach_cube(
                self.render,
                "enemy-burst",
                (position.x, position.y, position.z),
                (0.9, 0.9, 0.9),
                Vec4(1.0, 0.22, 0.12, 1),
            )
            self.effects.append(EffectParticle(burst, Vec3(0, 0, 0), 0.0, 0.22, 0.0, 100.0, 1.0))

    def _damage_enemy(self, enemy: Enemy, hit_position: Vec3) -> None:
        enemy.hp -= 1
        self._spawn_hit_sparks(hit_position, strong=enemy.hp <= 0)
        self._play_hit_sound()
        self.camera_shake = max(self.camera_shake, 0.17 if enemy.hp > 0 else 0.30)

        if enemy.hp <= 0:
            enemy.active = False
            enemy.node.hide()
            self.enemies_defeated += 1
            self.enemy_text.setText(f"击败敌人：{self.enemies_defeated} / {len(self.enemies)}")
            self.message_text.setText("敌人被击败！")
            self.taskMgr.remove("clear-hit-message")
            self.doMethodLater(0.75, self._clear_message, "clear-hit-message")

    def _update_shooting(self, dt: float) -> None:
        self.fire_cooldown = max(0.0, self.fire_cooldown - dt)
        if self.game_over or not self.shooting or self.fire_cooldown > 0.0:
            return
        self._fire_weapon()
        self.fire_cooldown = self.FIRE_INTERVAL

    def _update_bullets(self, dt: float) -> None:
        remaining: List[Bullet] = []

        for bullet in self.bullets:
            bullet.life -= dt
            old_pos = bullet.node.getPos()
            new_pos = old_pos + bullet.velocity * dt
            bullet.node.setPos(new_pos)

            collided = bullet.life <= 0.0 or abs(new_pos.x) > self.WORLD_LIMIT or abs(new_pos.y) > self.WORLD_LIMIT
            if not collided:
                collided = any(box.intersects_circle(new_pos.x, new_pos.y, 0.12) for box in self.obstacles)

            hit_enemy: Optional[Enemy] = None
            if not collided:
                for enemy in self.enemies:
                    if not enemy.active:
                        continue
                    enemy_pos = enemy.node.getPos()
                    dx = new_pos.x - enemy_pos.x
                    dy = new_pos.y - enemy_pos.y
                    if dx * dx + dy * dy < 0.80 * 0.80:
                        hit_enemy = enemy
                        collided = True
                        break

            if collided:
                if hit_enemy is not None:
                    self._damage_enemy(hit_enemy, Vec3(new_pos.x, new_pos.y, 1.15))
                elif bullet.life > 0.0:
                    self._spawn_hit_sparks(Vec3(new_pos.x, new_pos.y, max(0.18, new_pos.z)), strong=False)
                bullet.node.removeNode()
            else:
                remaining.append(bullet)

        self.bullets = remaining

    def _update_effects(self, dt: float) -> None:
        remaining: List[EffectParticle] = []
        for effect in self.effects:
            effect.age += dt
            if effect.age >= effect.life:
                effect.node.removeNode()
                continue

            effect.velocity.z -= effect.gravity * dt
            effect.node.setPos(effect.node.getPos() + effect.velocity * dt)
            effect.node.setH(effect.node.getH() + effect.spin * dt)
            effect.node.setP(effect.node.getP() + effect.spin * 0.65 * dt)

            progress = effect.age / effect.life
            scale = effect.initial_scale * max(0.05, 1.0 - progress)
            effect.node.setScale(effect.node.getScale() * (scale / max(0.001, effect.initial_scale)))
            effect.initial_scale = scale
            remaining.append(effect)

        self.effects = remaining

    # ------------------------------------------------------------------
    # 游戏更新
    # ------------------------------------------------------------------
    def _can_move_to(self, x: float, y: float) -> bool:
        if abs(x) > self.WORLD_LIMIT or abs(y) > self.WORLD_LIMIT:
            return False
        return not any(box.intersects_circle(x, y, self.PLAYER_RADIUS) for box in self.obstacles)

    def _update_player(self, dt: float) -> None:
        if self.game_over:
            return

        dx = float(self.keys["d"]) - float(self.keys["a"])
        dy = float(self.keys["w"]) - float(self.keys["s"])
        direction = Vec3(dx, dy, 0)
        if direction.lengthSquared() == 0:
            return

        direction.normalize()
        current = self.player.getPos()
        step = direction * self.PLAYER_SPEED * dt

        target_x = current.x + step.x
        if self._can_move_to(target_x, current.y):
            current.x = target_x
        target_y = current.y + step.y
        if self._can_move_to(current.x, target_y):
            current.y = target_y

        self.player.setPos(current)
        heading = math.degrees(math.atan2(-direction.x, direction.y))
        current_h = self.player.getH()
        delta_h = ((heading - current_h + 180) % 360) - 180
        self.player.setH(current_h + delta_h * min(1.0, dt * 12.0))

    def _update_camera(self, dt: float) -> None:
        desired = self.player.getPos() + Vec3(0, -17, 19)

        if self.camera_shake > 0.0:
            strength = self.camera_shake * 0.55
            desired += Vec3(random.uniform(-strength, strength), random.uniform(-strength, strength), random.uniform(-strength, strength))
            self.camera_shake = max(0.0, self.camera_shake - dt * 2.8)

        factor = 1.0 - math.exp(-6.0 * dt)
        self.camera.setPos(self.camera.getPos() + (desired - self.camera.getPos()) * factor)
        self.camera.lookAt(self.player.getPos() + Vec3(0, 0, 1.1))

    def _update_collectibles(self, dt: float) -> None:
        player_pos = self.player.getPos()
        elapsed = self.clock.getFrameTime()
        remaining: List[Collectible] = []

        for item in self.collectibles:
            item.node.setH(item.node.getH() + 90 * dt)
            item.node.setZ(item.base_z + math.sin(elapsed * 2.3 + item.phase) * 0.18)
            if (item.node.getPos() - player_pos).lengthSquared() < 1.25 * 1.25:
                self._spawn_hit_sparks(item.node.getPos(), strong=False)
                item.node.removeNode()
                self.score += 1
                self.score_text.setText(f"水晶：{self.score} / 6")
                self._play_pickup_sound()
            else:
                remaining.append(item)

        self.collectibles = remaining
        if self.score == 6 and self.enemies_defeated == len(self.enemies) and not self.game_over:
            self.game_over = True
            self.message_text.setText("任务完成！按 R 再玩一次")

    def _update_enemies(self, dt: float) -> None:
        if self.game_over:
            return

        player_pos = self.player.getPos()
        for enemy in self.enemies:
            if not enemy.active:
                continue

            enemy.progress += enemy.direction * enemy.speed * dt
            if enemy.progress >= 1.0:
                enemy.progress = 1.0
                enemy.direction = -1.0
            elif enemy.progress <= 0.0:
                enemy.progress = 0.0
                enemy.direction = 1.0

            pos = enemy.start + (enemy.end - enemy.start) * enemy.progress
            enemy.node.setPos(pos)
            move_dir = enemy.end - enemy.start
            if enemy.direction < 0:
                move_dir = -move_dir
            enemy.node.setH(math.degrees(math.atan2(-move_dir.x, move_dir.y)))

            if (enemy.node.getPos() - player_pos).lengthSquared() < 1.15 * 1.15:
                self.player.setPos(0, 0, 0.05)
                self.message_text.setText("被巡逻怪撞到了！")
                self.taskMgr.remove("clear-hit-message")
                self.doMethodLater(1.1, self._clear_message, "clear-hit-message")
                break

    def _clear_message(self, task: Task) -> int:
        if not self.game_over:
            self.message_text.setText("")
        return Task.done

    def reset_game(self) -> None:
        for item in self.collectibles:
            item.node.removeNode()
        self.collectibles.clear()

        for bullet in self.bullets:
            bullet.node.removeNode()
        self.bullets.clear()

        for effect in self.effects:
            effect.node.removeNode()
        self.effects.clear()

        self.player.setPos(0, 0, 0.05)
        self.player.setH(0)
        self.score = 0
        self.enemies_defeated = 0
        self.game_over = False
        self.fire_cooldown = 0.0
        self.camera_shake = 0.0
        self.score_text.setText("水晶：0 / 6")
        self.enemy_text.setText(f"击败敌人：0 / {len(self.enemies)}")
        self.message_text.setText("")

        positions = [(-2, 7), (2, 12), (-1, -8), (4.5, -13), (0, 15), (-3, -14)]
        for index, (x, y) in enumerate(positions):
            self._add_collectible(x, y, index)

        for enemy in self.enemies:
            enemy.progress = 0.0
            enemy.direction = 1.0
            enemy.hp = 3
            enemy.active = True
            enemy.node.setPos(enemy.start)
            enemy.node.show()

        if self.paused:
            self.resume_game()

    def update(self, task: Task) -> int:
        dt = min(self.clock.getDt(), 1.0 / 20.0)
        if self.paused:
            return Task.cont

        self._update_player(dt)
        self._update_shooting(dt)
        self._update_bullets(dt)
        self._update_effects(dt)
        self._update_camera(dt)
        self._update_collectibles(dt)
        self._update_enemies(dt)
        return Task.cont


if __name__ == "__main__":
    game = CartoonTopDownGame()
    game.run()
