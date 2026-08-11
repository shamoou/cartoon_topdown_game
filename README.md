# Python 3.9 卡通俯视第三人称射击游戏

这是一个使用 **Python 3.9 + Panda3D 1.10.16** 制作的可运行 3D 俯视第三人称射击原型。

## 新增功能

- 鼠标左键或空格连续射击
- 卡通枪械模型
- 枪口闪光和曳光弹
- 子弹与场景障碍物碰撞
- 敌人三点生命值、命中火花和击败爆炸
- 轻微射击与命中镜头震动
- 射击音效、命中音效、收集音效
- 可循环播放的原创占位背景音乐
- ESC 暂停菜单
- 继续游戏、设置和退出游戏选项
- 背景音乐音量滑块
- 射击与效果音量滑块
- 音量设置自动保存到 `settings.json`

## 运行环境

- Python 3.9
- Windows 10/11
- Panda3D 1.10.16

## 安装与运行

在项目目录打开 CMD 或 PowerShell：

```bat
py -3.9 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

也可以双击 `run.bat`。

## 操作方式

| 按键 | 功能 |
|---|---|
| W / A / S / D | 移动角色 |
| 鼠标左键 | 连续射击 |
| 空格 | 连续射击 |
| ESC | 打开或关闭暂停菜单 |
| R | 重新开始游戏 |

角色会朝最后一次移动的方向射击。敌人受到三次命中后被击败。

## 暂停菜单

按下 ESC 后，游戏逻辑会暂停，并显示：

- **继续游戏**：关闭菜单并继续
- **设置**：调节音乐和效果音量
- **退出游戏**：关闭程序

设置页再次按 ESC 会返回暂停主菜单。音量范围为 0% 至 100%。

## 音频文件

```text
assets/audio/
├─ cartoon_bgm.wav
├─ shoot.wav
├─ hit.wav
└─ pickup.wav
```

这些 WAV 文件由项目内的 Python 标准库脚本生成：

```bat
python tools\generate_audio.py
```

因此可以直接替换成自己的 WAV、OGG 音乐和音效，只需保留文件名，或修改 `main.py` 中的加载路径。

## 项目结构

```text
cartoon_topdown_game_py39/
├─ main.py
├─ requirements.txt
├─ run.bat
├─ README.md
├─ assets/
│  └─ audio/
│     ├─ cartoon_bgm.wav
│     ├─ shoot.wav
│     ├─ hit.wav
│     └─ pickup.wav
└─ tools/
   └─ generate_audio.py
```

## 常见问题

### 有画面但没有声音

先确认系统默认播放设备正常，并重新安装 Panda3D：

```bat
pip uninstall panda3d -y
pip install panda3d==1.10.16
```

项目在音频设备不可用时会自动静音运行，不会因为音频加载失败而终止。

### 点击设置按钮时角色仍然射击

暂停菜单打开后游戏更新会停止，恢复游戏时只有在鼠标仍处于按下状态时才可能继续射击；松开鼠标左键即可。
