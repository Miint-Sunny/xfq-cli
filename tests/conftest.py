# -*- coding: utf-8 -*-
"""测试共用的设置。"""
import os

import pytest

import xfq.cli as cli


@pytest.fixture(autouse=True)
def no_system_trash(tmp_path_factory, monkeypatch):
    """以临时目录代替系统废纸篓，防止测试向用户的废纸篓移入文件。

    各测试可再用自己的替身覆盖。验证系统废纸篓见 test_cli.py 中的 test_real_system_trash。
    """
    bin_dir = tmp_path_factory.mktemp('Trash')

    def move(path):
        target = bin_dir / os.path.basename(path)
        os.replace(path, target)
        return str(target)

    monkeypatch.setattr(cli, 'move_to_trash', move)
    return bin_dir
