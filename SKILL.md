---
name: visual-effects
description: 给用户提供的图片、Logo 或视频本地渲染可重复的设计特效。适用于小红书「用好工具，设计像呼吸一样简单」帖子的封面工程图、扫描框、CRT、VHS、故障错位、网点、竖线点描、抖动、ASCII、渐变映射和发光轮廓。用户点名 visual-effects，或给素材并要求应用这些特效时使用。
---

# 视觉特效

用用户提供或明确指向的素材，执行 `scripts/render.py` 并交付渲染结果。用户只需说效果和想怎么改，参数由你转换。默认本地处理，保留源文件和构图比例。静态图默认以原尺寸导出 PNG，动图和视频导出 MP4，视频默认最长边 1080 像素、24 fps，并保留第一条音轨。

## 从描述选择预设

| 用户描述 | 预设 |
| --- | --- |
| 那篇小红书的封面、工程图、蓝图、坐标网格、几何连线 | `schematic` |
| 科技扫描、橙色追踪框、目标标记 | `tracker`，按局部反差找位置，做扫描框视觉 |
| 老电视、像素屏、扫描线／录像带、掉帧感、模拟噪点 | `crt`／`vhs` |
| 横向撕裂、数字损坏、画面错位 | `glitch` |
| 印刷网点、圆点半调／黑白竖线点描／像素抖动 | `halftone`／`stripes`／`dither` |
| 字符画、代码颗粒 | `ascii` |
| 热成像、酸绿色、双色或多色映射 | `recolor` |
| Logo 外发光、霓虹呼吸 | `logo-glow`，优先用带边距的透明 PNG |

用户描述了一个清楚的方向，就直接出一版。参数省略时用预设默认值。已有素材但没指定风格时，出三张便于选择的预览，通常选 `schematic`、`crt`、`stripes`，按素材调整。只有缺少素材且无法从当前上下文定位时，才请用户发素材。「像原帖」而没指定某张图时，优先做其封面工程图效果。

## 运行

从已加载的 Skill 目录定位 `scripts/render.py`。使用已能导入 Pillow 11+ 和 NumPy 的 Python。本机常用 `/usr/bin/python3`，常规 `python3` 可用时也可以使用。视频需要 PATH 上的 `ffmpeg` 与 `ffprobe`。先看 `--help` 可确认可用参数和输入输出要求。

```sh
/usr/bin/python3 /path/to/scripts/render.py "input.jpg" "output.png" --effect schematic --density 9 --color '#bbebff'
/usr/bin/python3 /path/to/scripts/render.py "input.mp4" "output.mp4" --effect crt:0.55 --effect glitch:0.18
/usr/bin/python3 /path/to/scripts/render.py "logo.png" "glow.mp4" --effect logo-glow --animate 4.8 --color '#517cff'
```

- 多个 `--effect` 按顺序叠加。后缀 `:0.35` 指该层与上一层的混合占比。减淡、高保真优先降混合占比。需要减少圆环标记、扫描框或网点时调低 `--density`。
- `--color` 用于网格、追踪框、网点、字符和发光。`--background` 可换纸色或发光底色。`recolor` 用 `--palette thermal|cobalt|violet|acid|mono`，或用从暗到亮的逗号分隔色值，例如 `'#130c2a,#8041f4,#d5fff1'`。
- 静态图片做动态时用 `--animate 秒数` 和 MP4 输出。`crt`、`vhs`、`glitch`、`logo-glow` 在时间轴上会变化。图片输出是有底色的成品，带透明通道的 Logo 做发光时将 `logo-glow` 放在第一层。
- 用户继续说「线再淡一点」或「换青色」时，从源素材重跑，沿用上一版的效果顺序、比例和种子，只改有关参数。默认保留上一版，给新文件起独立的名字。

核对成品是否可打开、主体是否清楚以及效果是否符合描述。静态图给预览及文件路径，视频给可播放的结果。告知实际使用的效果即可。
