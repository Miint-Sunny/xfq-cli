# xfq — 小番茄图片混淆的命令行

群里流传的「小番茄混淆图」，一条命令解回来；也能反过来把图混淆了再发。批量、跨平台、输出无损 PNG。

```bash
xfq a.jpg                  # 解混淆 → a_dec.png
xfq -e a.png               # 混淆   → a_enc.png
xfq -r ./收图 -d ./解好     # 整个目录（会先报数量问一句 y/N，-y 跳过）
xfq -e *.png --jpeg        # 混淆并输出 JPEG（网页版出来的就是 JPEG，发群时更像）
xfq a.jpg -n               # 只算不写，看粗糙度变化
```

解混淆前后会算一下相邻像素的平均差异（粗糙度）：解对了会明显变平滑（30 张真图实测降到 0.46–0.79 倍，过了 JPEG 也一样），
解错会更粗糙（1.4 倍以上）。没变平滑说明这图根本不是小番茄混淆过的（或者已经是原图），默认跳过并提示，`--force` 硬写。

## 安装

依赖 Pillow + numpy，纯 Python，用 uv 管理，不用自己建 venv：

```bash
uv tool install git+https://github.com/Miint-Sunny/xfq      # 或克隆后在仓库里 uv tool install .
```

Windows 一样：装 uv → `uv tool install …` → `uv tool update-shell`，重开终端。通配符工具自己展开，
老式 cmd 窗口符号自动降级（`XFQ_ASCII=1` / `0` 强制）。不想装就 `uvx --from git+https://github.com/Miint-Sunny/xfq xfq a.jpg`。

## 它到底是什么

小番茄不是某一个 app，是一个公开算法加一堆套壳网页（xiaofanqiehunxiao.com、tupianhunxiao.com、各种 GitHub Pages 镜像）
和安卓版 PicEncrypt，起源是百度贴吧「图片混淆吧」，最早的参考实现是奇点站的 hideImg1.html。

算法是像素置换，不是加密，没有密码：

1. 对 W×H 的图生成一条广义希尔伯特曲线（Gilbert 曲线），把所有像素按曲线顺序排成一维；
2. 整体循环移位 `round((√5 − 1) / 2 × W × H)` 个位置（黄金分割）；
3. 解混淆就是反向移位。

曲线保持局部性，所以混淆后是色块糊成一片而不是纯噪点，经得起平台二压，社区拿它过审核。
置换本身无损，但几乎所有网页版导出 JPEG，收到的图多半已经有损，解出来会有轻微色偏，这是源头的损失，不是解错。

「大番茄」是带数字密码的变种（前两位移位轮数，后两位补边），已经有别的工具管，这里不做。

## 兼容性

按算法自己写的，没有复制任何一方代码，对拍过三处：

- 页面原版 JS（iris10086/pic-scramble）在 node 里跑出的 15 个尺寸的曲线，逐点一致；
- sd-image-sorter（MIT）用参考站 JS 生成的字节级黄金向量，混淆结果逐字节一致（`tests/assets/`）；
- 混淆 → 解混淆恒等，含 1×N、N×1、2×2 这些边角尺寸和 RGBA。

偏移量的取整用的是 JS `Math.round` 的语义（`floor(x + 0.5)`），不是 Python 的银行家舍入。

## 性能

Gilbert 曲线是纯 Python 递归生成的，1 MP 约 0.4 s、2 MP 约 0.9 s，同尺寸的图只算一次；像素搬动是 numpy 一步到位。

## 同类

| 项目 | 形态 | 备注 |
|---|---|---|
| [iris10086/pic-scramble](https://github.com/iris10086/pic-scramble) | 单文件网页 | 算法参考，MIT |
| [jiarandiana0307/PicEncrypt](https://github.com/jiarandiana0307/PicEncrypt) | 安卓 app | 六种混淆之一，MIT |
| [Rinne414/sd-image-sorter](https://github.com/Rinne414/sd-image-sorter) | 大应用的后端模块 | 小番茄 + 大番茄，黄金向量出处，MIT |
| [2195517546/ObfuscationUtils](https://github.com/2195517546/ObfuscationUtils) | Java 库 | MIT |

之前没有独立的 Python 命令行。

## 许可

MIT。
