"""Launcher environment selection and missing-environment diagnostics."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from config import ROOT


@pytest.fixture
def launcher(tmp_path):
    project = tmp_path / 'project with spaces'
    project.mkdir()
    shutil.copy2(ROOT / 'start', project / 'start')
    (project / 'main.py').write_text('import sys; print(repr(sys.argv[1:]))\n')
    env = {k: v for k, v in os.environ.items() if k not in {'STEAM_CONDA_PREFIX', 'CONDA_PREFIX'}}
    return project, env


def invoke(project, env, *args):
    return subprocess.run([str(project / 'start'), *args], env=env, cwd='/tmp', capture_output=True, text=True, timeout=5)


def test_project_environment_precedes_unrelated_active_environment(launcher):
    project, env = launcher
    (project / '.conda').symlink_to(sys.prefix, target_is_directory=True)
    env['CONDA_PREFIX'] = '/nonexistent/unrelated-environment'
    query = 'A game with spaces; $(no-shell-evaluation)'
    result = invoke(project, env, 'game', query)
    assert result.returncode == 0 and repr(query) in result.stdout


def test_active_environment_is_used_when_project_environment_absent(launcher):
    project, env = launcher
    env['CONDA_PREFIX'] = sys.prefix
    result = invoke(project, env, '--help')
    assert result.returncode == 0 and '--help' in result.stdout


def test_explicit_override_precedes_project_environment(launcher):
    project, env = launcher
    (project / '.conda').symlink_to(sys.prefix, target_is_directory=True)
    env['STEAM_CONDA_PREFIX'] = '/nonexistent/explicit-environment'
    result = invoke(project, env, '--help')
    assert result.returncode == 1 and 'Conda' in result.stderr and result.stdout == ''


def test_legacy_venv_is_not_selected_and_missing_conda_explained(launcher):
    project, env = launcher
    (project / '.venv').symlink_to(sys.prefix, target_is_directory=True)
    result = invoke(project, env, '--help')
    assert result.returncode == 1 and 'conda env create' in result.stderr
    assert result.stdout == ''
