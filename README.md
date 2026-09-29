# xfq-cli

小番茄图片混淆的命令行工具：批量混淆与解混淆，输出无损 PNG。

## 背景

“小番茄混淆”是一种公开的图片混淆算法。它有多个网页实现（xiaofanqiehunxiao.com、tupianhunxiao.com 及各类 GitHub Pages 镜像），
还有一个安卓实现 PicEncrypt。该算法源自百度贴吧“图片混淆吧”，最早的参考实现是奇点站的 hideImg1.html。
在此之前，这个算法没有独立的 Python 命令行实现。

xfq-cli 的功能：

- 将混淆图还原（解混淆）。
- 混淆图片。
- 批量处理文件和目录。
- 支持 macOS、Linux 和 Windows。

不支持“大番茄”，即带数字密码的变种。

## 安装

需要 [uv](https://docs.astral.sh/uv/)。uv 会自动安装所需的 Python（3.10 或更高版本），并为本工具创建独立环境。

从 GitHub 安装：

```bash
uv tool install git+https://github.com/Miint-Sunny/xfq-cli
```

也可以克隆仓库后从本地源码安装：

```bash
git clone https://github.com/Miint-Sunny/xfq-cli.git
cd xfq-cli
uv tool install .
```

检查是否安装成功：

```bash
xfq --version
```

| 操作 | 命令 |
|---|---|
| 更新（从 GitHub 安装） | `uv tool install --reinstall git+https://github.com/Miint-Sunny/xfq-cli` |
| 更新（从本地源码安装） | 在仓库目录中执行 `git pull`，再执行 `uv tool install . --reinstall` |
| 不安装，直接运行一次 | `uvx --from git+https://github.com/Miint-Sunny/xfq-cli xfq a.jpg` |
| 卸载 | `uv tool uninstall xfq-cli` |

在 Windows 上，先在 PowerShell 中安装 uv，再执行上面的安装命令，然后执行 `uv tool update-shell`，把命令目录加入 PATH。之后需要重新打开终端。

## 用法

```bash
xfq a.jpg                  # 解混淆，输出 a_dec.png
xfq -e a.png               # 混淆，输出 a_enc.png
xfq -r ./in -d ./out       # 递归处理目录，结果写入 ./out
xfq -e *.png --jpeg        # 混淆并输出 JPEG（质量 95）
xfq a.jpg -n               # 试运行，只报告粗糙度变化，不写入文件
```

| 选项 | 说明 |
|---|---|
| `-e`, `--encode` | 混淆图片。默认为解混淆 |
| `-f`, `--force` | 解混淆结果未通过粗糙度校验时，仍写出文件 |
| `-o FILE` | 输出文件，只能用于单个输入文件 |
| `-d DIR` | 输出目录。输入为目录时，保留相对路径 |
| `--suffix SUFFIX` | 输出文件名后缀。默认值：解混淆为 `_dec`，混淆为 `_enc` |
| `--jpeg [QUALITY]` | 输出 JPEG 而不是 PNG。QUALITY 的取值为 1–100，默认为 95。网页实现通常导出 JPEG，因此混淆图输出为 JPEG 时与网页导出的结果更接近 |
| `--overwrite` | 覆盖已存在的输出文件。默认跳过 |
| `-r`, `--recursive` | 递归处理子目录 |
| `-n`, `--dry-run` | 试运行：计算并报告结果，不写入文件 |
| `-y`, `--yes` | 处理目录或通配符时，不请求确认 |

输入包含目录或通配符时，处理前会显示文件数量和输出位置，并请求确认：

```
$ xfq ./in -d ./out
./in：共 3 个文件（jpg 3），解混淆，输出到目录 ./out
是否继续？[y/N] y
✔ a.jpg → out/a_dec.png  已解混淆 832×1216；粗糙度 10.1 → 7.0；1.19 MiB
✔ b.jpg → out/b_dec.png  已解混淆 832×1216；粗糙度 8.8 → 6.0；1.39 MiB
· c.jpg  已跳过：解混淆后粗糙度未下降（6.2 → 9.5），输入可能不是小番茄混淆图（使用 -f 仍写出）
完成：共 3 个文件，成功 2 个，跳过 1 个，失败 0 个
```

### 解混淆校验

解混淆前后，分别计算相邻像素的平均差异，即“粗糙度”。

- 正确解混淆时，粗糙度明显下降。30 张实际图片的测试中，解混淆后的粗糙度是解混淆前的 0.46–0.79 倍，经过 JPEG 压缩的图片也在此范围内。
- 对原图执行解混淆时，粗糙度上升到原来的 1.41–2.17 倍。
- 粗糙度没有下降，说明输入不是小番茄混淆图，或者已经是原图。这种情况下，默认跳过该文件；使用 `-f` 时仍写出文件。

### 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 全部成功。跳过的文件不计为失败 |
| 1 | 至少有一个文件处理失败；未找到输入文件；用户取消 |
| 2 | 命令行参数错误 |

## 工作原理

该算法是像素置换，不是加密，没有密码：

1. 为 W×H 的图像生成一条广义希尔伯特曲线（Gilbert 曲线），按曲线顺序将全部像素排成一维序列。
2. 将序列整体循环移位 `round((√5 − 1) / 2 × W × H)` 个位置（黄金分割比）。
3. 解混淆时反向移位。

曲线具有局部性，因此混淆结果是成片的色块，而不是随机噪点，能够承受平台的有损压缩。

置换本身是无损的。但大多数网页实现导出 JPEG，收到的混淆图通常已经过有损压缩，解混淆结果会有轻微色差。
这是压缩造成的，不是解混淆错误。

## 兼容性

本工具依据算法独立实现，没有复制任何参考实现的代码。以下三项验证均已通过：

- 与网页原版 JS（iris10086/pic-scramble）在 Node.js 中生成的曲线比对，15 种尺寸逐点一致。
- 与 sd-image-sorter（MIT）提供的参考数据比对，混淆结果逐字节一致。这些数据由参考网页的原版 JS 生成，存放在 `tests/assets/`。
- 混淆后再解混淆，结果与原图相同。测试覆盖 1×N、N×1、2×2 等边界尺寸，以及 RGBA 图像。

循环移位量按 JS `Math.round` 的规则取整，即 `floor(x + 0.5)`。Python 的 `round()` 采用银行家舍入，结果可能差 1。

## 性能

Gilbert 曲线由纯 Python 递归生成：1 MP 约需 0.4 秒，2 MP 约需 0.9 秒。同一尺寸的曲线只计算一次，像素置换由 numpy 完成。

## 相关项目

| 项目 | 形式 | 说明 |
|---|---|---|
| [iris10086/pic-scramble](https://github.com/iris10086/pic-scramble) | 单文件网页 | 本工具的算法参考，MIT |
| [jiarandiana0307/PicEncrypt](https://github.com/jiarandiana0307/PicEncrypt) | 安卓应用 | 提供六种混淆方式，小番茄是其中之一，MIT |
| [Rinne414/sd-image-sorter](https://github.com/Rinne414/sd-image-sorter) | 应用的后端模块 | 支持小番茄与大番茄，本工具参考数据的来源，MIT |
| [2195517546/ObfuscationUtils](https://github.com/2195517546/ObfuscationUtils) | Java 库 | MIT |

## 开发

```bash
git clone https://github.com/Miint-Sunny/xfq-cli.git
cd xfq-cli
uv run xfq a.jpg       # 首次运行时自动创建 .venv
uv run pytest          # 运行测试
```

```
src/xfq/core.py         算法：Gilbert 曲线、置换、粗糙度
src/xfq/cli.py          命令行
src/xfq/argparse_zh.py  argparse 的中文界面与按显示宽度折行
tests/                  测试：与参考数据比对、混淆往返、命令行
```

## 许可证

[MIT](LICENSE)
